"""Third-party clients: TomTom (truck routing, geocoding) and Open-Meteo (hourly forecasts)."""

import logging
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from urllib.parse import quote

import requests
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from django.core.cache import cache
from django.utils import timezone

from .geo import bearing_deg, cumulative_miles, haversine_mi, offset_point, point_at

logger = logging.getLogger(__name__)

TOMTOM_URL = "https://api.tomtom.com"
METERS_PER_MILE = 1609.344
TARE_LBS = 35_000  # typical empty tractor-trailer; TomTom's vehicleWeight is gross weight
KG_PER_LB = 0.45359237


class ProviderError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


# One retry for timeouts, dropped connections and 5xx; 429 is surfaced immediately.
session = requests.Session()
session.mount("https://", HTTPAdapter(max_retries=Retry(total=1, backoff_factor=1, status_forcelist=[502, 503, 504], raise_on_status=False)))


def _get(name: str, url: str, params: dict, timeout: float = 25):
    try:
        resp = session.get(url, params=params, timeout=(5, timeout))
    except requests.RequestException:
        raise ProviderError(f"{name} is unreachable, try again shortly") from None  # message would leak the API key
    if resp.status_code == 429:
        reason = resp.json().get("reason", "") if "json" in resp.headers.get("content-type", "") else ""
        raise ProviderError(f"{name} rate limit reached, try again in a minute ({reason or 'HTTP 429'})", 503)
    if resp.status_code == 400:
        body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        detail = body.get("detailedError", {}).get("message") or body.get("reason") or "invalid request"
        raise ProviderError(f"{name}: {detail}", 422)
    if not resp.ok:
        raise ProviderError(f"{name} error (HTTP {resp.status_code})")
    return resp.json()


# --- TomTom -------------------------------------------------------------------------------------


def geocode(query: str) -> list[dict]:
    cache_key = f"geo:{quote(query.lower())}"
    if (hit := cache.get(cache_key)) is not None:
        return hit
    data = _get("Geocoding", f"{TOMTOM_URL}/search/2/search/{quote(query, safe='')}.json", {
        "key": settings.TOMTOM_API_KEY, "typeahead": "true", "limit": 6, "countrySet": "US,CA",
    })
    places = [
        {
            "label": f"{r['poi']['name']}, {r['address']['freeformAddress']}" if "poi" in r else r["address"]["freeformAddress"],
            "lat": r["position"]["lat"],
            "lon": r["position"]["lon"],
        }
        for r in data.get("results", [])
    ]
    cache.set(cache_key, places, 24 * 3600)
    return places


def _calculate(points: list[tuple], depart: datetime, load_lbs: float, alternatives: int) -> list[dict]:
    path = ":".join(f"{lat:.6f},{lon:.6f}" for lat, lon in points)
    data = _get("Routing", f"{TOMTOM_URL}/routing/1/calculateRoute/{path}/json", {
        "key": settings.TOMTOM_API_KEY,
        "travelMode": "truck",
        "vehicleCommercial": "true",
        "vehicleWeight": round((load_lbs + TARE_LBS) * KG_PER_LB),
        "departAt": "now" if depart <= timezone.now() + timedelta(minutes=1) else depart.isoformat(timespec="seconds"),
        "traffic": "true",
        "instructionsType": "coded",
        "maxAlternatives": alternatives,
        "alternativeType": "anyRoute" if alternatives else None,
    }, timeout=40)
    return [_parse_route(r) for r in data["routes"]]


def _parse_route(route: dict) -> dict:
    """Geometry plus a distance->time profile from guidance instructions (cumulative offsets and times)."""
    summary = route["summary"]
    steps = [(0, 0)]
    for ins in route.get("guidance", {}).get("instructions", []):
        steps.append((ins["routeOffsetInMeters"], ins["travelTimeInSeconds"]))
    steps.append((summary["lengthInMeters"], summary["travelTimeInSeconds"]))
    steps = sorted(set(steps))
    return {
        "coords": [(p["latitude"], p["longitude"]) for leg in route["legs"] for p in leg["points"]],
        "length_mi": summary["lengthInMeters"] / METERS_PER_MILE,
        "duration_s": summary["travelTimeInSeconds"],
        "traffic_delay_s": summary.get("trafficDelayInSeconds", 0),
        "profile_mi": [m / METERS_PER_MILE for m, _ in steps],
        "profile_s": [s for _, s in steps],
    }


def _overlap(a: dict, b: dict) -> float:
    cells = {(round(lat, 2), round(lon, 2)) for lat, lon in b["coords"]}
    return sum((round(lat, 2), round(lon, 2)) in cells for lat, lon in a["coords"]) / len(a["coords"])


def routes(origin: tuple, destination: tuple, depart: datetime, load_lbs: float) -> list[dict]:
    """Up to 3 distinct truck routes, cached 10 min per departure 5-minute slot (re-plans at another interval are instant)."""
    cache_key = f"route:{origin}:{destination}:{load_lbs}:{depart:%Y%m%d%H}:{depart.minute // 5}"
    if (hit := cache.get(cache_key)) is not None:
        return hit
    found = _routes(origin, destination, depart, load_lbs)
    cache.set(cache_key, found, 10 * 60)
    return found


def _routes(origin: tuple, destination: tuple, depart: datetime, load_lbs: float) -> list[dict]:
    """TomTom's best route plus its alternatives, topped up with via-point detours."""
    found = _calculate([origin, destination], depart, load_lbs, alternatives=2)
    if len(found) >= 3:
        return found[:3]
    # ponytail: TomTom sometimes returns <3 alternatives; force detours through points offset sideways from the
    # main route's midpoint. A via point can add a small loop; a proper fix is a provider with more alternatives.
    main = found[0]
    cum = cumulative_miles(main["coords"])
    mid = point_at(main["coords"], cum, cum[-1] / 2)
    heading = bearing_deg(point_at(main["coords"], cum, cum[-1] * 0.45), point_at(main["coords"], cum, cum[-1] * 0.55))
    span = max(haversine_mi(origin, destination), 20)
    for fraction in (0.15, 0.3):
        for side in (90, -90):
            if len(found) >= 3:
                return found
            via = offset_point(mid, heading + side, span * fraction)
            try:
                candidate = _calculate([origin, via, destination], depart, load_lbs, alternatives=0)[0]
            except ProviderError:
                continue  # via point not routable (water, no roads)
            if all(_overlap(candidate, r) < 0.9 for r in found):
                found.append(candidate)
    return found


# --- Open-Meteo ---------------------------------------------------------------------------------

HOURLY_VARS = "wind_speed_10m,wind_gusts_10m,rain,showers,snowfall"
BATCH_SIZE = 100


def _fetch_batch(points: list[tuple], start: datetime, end: datetime) -> list[dict]:
    base = "https://customer-api.open-meteo.com" if settings.OPEN_METEO_API_KEY else "https://api.open-meteo.com"
    data = _get("Weather", f"{base}/v1/forecast", {
        "latitude": ",".join(str(lat) for lat, _ in points),
        "longitude": ",".join(str(lon) for _, lon in points),
        "hourly": HOURLY_VARS,
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",  # also makes snowfall inches
        "timezone": "GMT",
        "timeformat": "unixtime",
        "start_hour": start.strftime("%Y-%m-%dT%H:%M"),
        "end_hour": end.strftime("%Y-%m-%dT%H:%M"),
        "apikey": settings.OPEN_METEO_API_KEY or None,
    })
    results = data if isinstance(data, list) else [data]

    def values(hourly: dict, name: str) -> list[float]:
        return [v or 0.0 for v in hourly[name]]

    return [
        {
            "t0": r["hourly"]["time"][0],
            "wind": values(r["hourly"], "wind_speed_10m"),
            "gust": values(r["hourly"], "wind_gusts_10m"),
            # Open-Meteo splits liquid precipitation into large-scale rain and convective showers.
            "rain": [a + b for a, b in zip(values(r["hourly"], "rain"), values(r["hourly"], "showers"))],
            "snow": values(r["hourly"], "snowfall"),
        }
        for r in results
    ]


def forecast(points: list[tuple], start: datetime, end: datetime) -> dict[tuple, dict]:
    """Hourly series (UTC hours from `start` to `end`) per point, cached 30 min per lattice point.

    Points are fetched in the given order, so callers put essential points first. A batch that fails is
    left out of the result; the caller decides whether the missing points matter.
    """
    window = f"{start:%Y%m%d%H}-{end:%Y%m%d%H}"
    keys = {p: f"wx:{p[0]}:{p[1]}:{window}" for p in points}
    cached = cache.get_many(keys.values())
    series = {p: cached[k] for p, k in keys.items() if k in cached}
    missing = [p for p in points if p not in series]
    batches = [missing[i:i + BATCH_SIZE] for i in range(0, len(missing), BATCH_SIZE)]
    def fetch(batch: list[tuple]) -> list[dict] | None:
        try:
            return _fetch_batch(batch, start, end)
        except ProviderError as e:
            logger.warning("Weather batch of %d points failed: %s", len(batch), e)
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        for batch, result in zip(batches, pool.map(fetch, batches)):
            if result is None:
                continue
            series.update(zip(batch, result))
            cache.set_many({keys[p]: s for p, s in zip(batch, result)}, 30 * 60)
    return series


def at(series: dict, when: datetime) -> dict:
    """Wind at the nearest hour; rain/snow from the hour ending after `when` (Open-Meteo sums the preceding hour)."""
    h = (when.timestamp() - series["t0"]) / 3600
    last = len(series["wind"]) - 1
    near = min(max(math.floor(h + 0.5), 0), last)
    after = min(max(math.ceil(h), 0), last)
    return {
        "wind_mph": series["wind"][near],
        "gust_mph": series["gust"][near],
        "rain_in": round(series["rain"][after], 3),
        "snow_in": round(series["snow"][after], 3),
    }
