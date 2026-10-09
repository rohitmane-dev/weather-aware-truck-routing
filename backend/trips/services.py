import math
from datetime import datetime, timedelta

from django.utils import timezone

from . import providers
from .geo import checkpoint_miles, corridor_grid, cumulative_miles, interpolate, owned_miles, point_at, risk_segments, simplify, snap
from .risk import NO_TRAVEL, classify, recommend, score, summarize

HEATMAP_HOURS = 49  # forecast slider 0..48 h from departure


def _lonlat(point: tuple) -> list[float]:
    return [round(point[1], 5), round(point[0], 5)]


def plan_trip(
    origin: dict, destination: dict, departure: datetime, load_lbs: int, interval_miles: int, weather: list[dict] | None = None
) -> dict:
    """Routes, checkpoints, risk, ranking and heatmap. `weather` is browser-fetched Open-Meteo data (see WeatherUnavailable)."""
    depart = max(departure, timezone.now()).replace(microsecond=0)  # a trip cannot start in the past
    raw_routes = providers.routes((origin["lat"], origin["lon"]), (destination["lat"], destination["lon"]), depart, load_lbs)

    routes = []
    for route_id, raw in enumerate(raw_routes):
        coords = raw["coords"]
        cum = cumulative_miles(coords)
        scale = raw["length_mi"] / cum[-1] if cum[-1] else 1.0  # align geometry miles with TomTom's distance
        cum = [c * scale for c in cum]
        checkpoints = [
            {
                "mile": mile,
                "point": point_at(coords, cum, mile),
                "eta": depart + timedelta(seconds=round(interpolate(raw["profile_mi"], raw["profile_s"], mile))),
            }
            for mile in checkpoint_miles(cum[-1], interval_miles)
        ]
        routes.append({"id": route_id, "raw": raw, "coords": coords, "cum": cum, "checkpoints": checkpoints})

    grid, grid_step = corridor_grid([(r["coords"], r["cum"]) for r in routes])
    checkpoint_points = {snap(cp["point"]) for r in routes for cp in r["checkpoints"]}
    # Open-Meteo bills per location: a grid node reuses any checkpoint forecast within half a grid step.
    nearest_node = {(round(lat / grid_step), round(lon / grid_step)): (lat, lon) for lat, lon in checkpoint_points}
    grid_source = {p: nearest_node.get((round(p[0] / grid_step), round(p[1] / grid_step)), p) for p in grid}

    start = depart.replace(minute=0, second=0, microsecond=0)
    hours_needed = max(HEATMAP_HOURS, math.ceil(max(r["raw"]["duration_s"] for r in routes) / 3600) + 2)
    end = start + timedelta(hours=math.ceil(hours_needed / 24) * 24)  # whole days so the cache window repeats
    heat_only = set(grid_source.values()) - checkpoint_points
    browser_weather = {snap((w["lat"], w["lon"])): w["hourly"] for w in weather or []}
    weather = providers.forecast([*checkpoint_points, *heat_only], start, end, browser_weather)
    missing = [p for p in [*checkpoint_points, *heat_only] if p not in weather]
    if (missing and not browser_weather) or not checkpoint_points <= weather.keys():
        raise providers.WeatherUnavailable(missing, start, end)
    grid = [p for p in grid if grid_source[p] in weather]  # after a browser attempt, the heatmap degrades instead

    results = []
    for r in routes:
        checkpoints = []
        for cp in r["checkpoints"]:
            wx = providers.at(weather[snap(cp["point"])], cp["eta"])
            level, reasons = classify(wx["wind_mph"], wx["rain_in"], wx["snow_in"], load_lbs)
            lat, lon = cp["point"]
            checkpoints.append({
                "mile": round(cp["mile"], 1), "lat": round(lat, 5), "lon": round(lon, 5), "eta": cp["eta"],
                **wx, "level": level, "reasons": reasons,
            })
        positions = [cp["mile"] for cp in r["checkpoints"]]
        levels = [cp["level"] for cp in checkpoints]
        raw = r["raw"]
        results.append({
            "id": r["id"],
            "distance_mi": round(raw["length_mi"], 1),
            "duration_s": raw["duration_s"],
            "traffic_delay_s": raw["traffic_delay_s"],
            "arrival": depart + timedelta(seconds=raw["duration_s"]),
            "segments": [
                {"level": s["level"], "coords": [_lonlat(p) for p in simplify(s["coords"])]}
                for s in risk_segments(r["coords"], r["cum"], positions, levels)
            ],
            "checkpoints": checkpoints,
            "summary": summarize(owned_miles(positions), levels),
        })

    ranked = recommend(results)
    hours = [start + timedelta(hours=h) for h in range(HEATMAP_HOURS)]
    return {
        "departure": depart,
        "routes": ranked,
        "recommended_id": ranked[0]["id"],
        "all_routes_unsafe": all(r["summary"]["miles_by_level"][NO_TRAVEL] > 0 for r in ranked),
        "heatmap": {
            "start": start,
            "step_deg": grid_step,
            "points": [_lonlat(p) for p in grid],
            "scores": [
                [round(score(wx["wind_mph"], wx["rain_in"], wx["snow_in"], load_lbs), 1)
                 for wx in (providers.at(weather[grid_source[p]], t) for t in hours)]
                for p in grid
            ],
        },
    }
