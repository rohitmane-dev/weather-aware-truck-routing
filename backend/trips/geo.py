"""Geometry helpers. Coordinates are (lat, lon) tuples; distances are miles."""

import math
from bisect import bisect_left, bisect_right

EARTH_RADIUS_MI = 3958.8
MI_PER_DEG_LAT = 69.0


def haversine_mi(a: tuple, b: tuple) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(math.sqrt(h))


def cumulative_miles(coords: list[tuple]) -> list[float]:
    cum = [0.0]
    for a, b in zip(coords, coords[1:]):
        cum.append(cum[-1] + haversine_mi(a, b))
    return cum


def interpolate(xs: list[float], ys: list[float], x: float) -> float:
    """Linear interpolation over sorted xs, clamped at the ends."""
    i = bisect_right(xs, x)
    if i == 0:
        return ys[0]
    if i == len(xs):
        return ys[-1]
    x0, x1, y0, y1 = xs[i - 1], xs[i], ys[i - 1], ys[i]
    return y0 if x1 == x0 else y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def point_at(coords: list[tuple], cum: list[float], mile: float) -> tuple:
    i = bisect_right(cum, mile)
    if i == 0:
        return coords[0]
    if i == len(cum):
        return coords[-1]
    (lat0, lon0), (lat1, lon1) = coords[i - 1], coords[i]
    span = cum[i] - cum[i - 1]
    t = (mile - cum[i - 1]) / span if span else 0.0
    return (lat0 + (lat1 - lat0) * t, lon0 + (lon1 - lon0) * t)


def checkpoint_miles(total: float, interval: float) -> list[float]:
    """Origin, every `interval` miles, and the destination."""
    miles = [i * interval for i in range(int(total // interval) + 1)]
    if total - miles[-1] > 1e-6:
        miles.append(total)
    return miles


def _ownership_bounds(positions: list[float]) -> list[float]:
    return [positions[0], *((a + b) / 2 for a, b in zip(positions, positions[1:])), positions[-1]]


def owned_miles(positions: list[float]) -> list[float]:
    """Each checkpoint owns the stretch between the midpoints to its neighbours; sums to the route length."""
    bounds = _ownership_bounds(positions)
    return [hi - lo for lo, hi in zip(bounds, bounds[1:])]


def slice_line(coords: list[tuple], cum: list[float], start: float, end: float) -> list[tuple]:
    i, j = bisect_right(cum, start), bisect_left(cum, end)
    return [point_at(coords, cum, start), *coords[i:j], point_at(coords, cum, end)]


def risk_segments(coords: list[tuple], cum: list[float], positions: list[float], levels: list[int]) -> list[dict]:
    """Split the route into runs of equal checkpoint level, using the same ownership bounds as owned_miles."""
    bounds = _ownership_bounds(positions)
    segments = []
    start = 0
    for k in range(1, len(levels) + 1):
        if k == len(levels) or levels[k] != levels[start]:
            segments.append({"level": levels[start], "coords": slice_line(coords, cum, bounds[start], bounds[k])})
            start = k
    return segments


def snap(point: tuple) -> tuple:
    """Snap to the global 0.1 degree lattice (~7 mi) so nearby requests share cached weather."""
    return (round(point[0], 1), round(point[1], 1))


def corridor_grid(lines: list[tuple[list, list]], buffer_mi: float = 30, max_points: int = 220) -> tuple[list[tuple], float]:
    """Lattice points within `buffer_mi` of any route and the lattice step in degrees.

    Spacing grows until at most `max_points` remain. `lines` are (coords, cum) pairs. Grid nodes are
    multiples of 0.1 degree so they share the weather cache with snapped checkpoints.
    """
    longest = max(cum[-1] for _, cum in lines)
    area = longest * 2 * buffer_mi * 1.3  # alternatives widen the corridor a little
    step = max(1, math.ceil(math.sqrt(area / max_points) / MI_PER_DEG_LAT * 10))  # tenths of a degree
    while True:
        nodes = set()
        for coords, cum in lines:
            for mile in _frange(0, cum[-1], step * MI_PER_DEG_LAT / 10 / 2):
                lat, lon = point_at(coords, cum, mile)
                lon_buffer = buffer_mi / (MI_PER_DEG_LAT * max(0.2, math.cos(math.radians(lat))))
                for i in range(math.floor((lat - buffer_mi / MI_PER_DEG_LAT) * 10 / step), math.ceil((lat + buffer_mi / MI_PER_DEG_LAT) * 10 / step) + 1):
                    for j in range(math.floor((lon - lon_buffer) * 10 / step), math.ceil((lon + lon_buffer) * 10 / step) + 1):
                        if (i, j) not in nodes and haversine_mi((lat, lon), (i * step / 10, j * step / 10)) <= buffer_mi:
                            nodes.add((i, j))
        if len(nodes) <= max_points:
            return [(round(i * step / 10, 1), round(j * step / 10, 1)) for i, j in sorted(nodes)], step / 10
        step += 1


def _frange(start: float, stop: float, step: float):
    x = start
    while x < stop:
        yield x
        x += step
    yield stop


def offset_point(origin: tuple, bearing_deg: float, distance_mi: float) -> tuple:
    """Flat-earth offset; fine for the tens-of-miles detours used to force alternative routes."""
    lat, lon = origin
    b = math.radians(bearing_deg)
    return (
        lat + distance_mi * math.cos(b) / MI_PER_DEG_LAT,
        lon + distance_mi * math.sin(b) / (MI_PER_DEG_LAT * math.cos(math.radians(lat))),
    )


def bearing_deg(a: tuple, b: tuple) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    y = math.sin(lon2 - lon1) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
    return math.degrees(math.atan2(y, x))
