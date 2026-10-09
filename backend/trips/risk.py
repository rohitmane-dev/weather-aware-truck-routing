"""Weather risk classification and route recommendation, per the assessment's risk/load rules."""

LOW, MODERATE, HIGH, SEVERE, NO_TRAVEL = range(5)
LEVEL_NAMES = ("Low", "Moderate", "High", "Severe", "No Travel")

# Lower bounds of Moderate, High, Severe, No Travel. Bands include their lower bound
# (wind 35 is High), except rain/snow No Travel which starts strictly above its bound (rain >1.00).
WIND_MPH = (25, 35, 45, 55)
RAIN_IN_HR = (0.10, 0.25, 0.50, 1.00)
SNOW_IN_HR = (0.5, 1.0, 2.0, 3.0)


def _band(value: float, bounds: tuple, no_travel_inclusive: bool) -> int:
    *lower, no_travel = bounds
    if value > no_travel or (no_travel_inclusive and value == no_travel):
        return NO_TRAVEL
    return sum(value >= b for b in lower)  # count of lower bounds reached -> LOW..SEVERE


def wind_level(mph: float, load_lbs: float) -> int:
    level = _band(mph, WIND_MPH, no_travel_inclusive=True)
    if level == SEVERE and load_lbs > 30_000:  # 45-54 mph + >30,000 lb
        return NO_TRAVEL
    if level == HIGH and load_lbs > 40_000:  # 35-44 mph + >40,000 lb
        return SEVERE
    return level


def rain_level(in_hr: float) -> int:
    return _band(in_hr, RAIN_IN_HR, no_travel_inclusive=False)


def snow_level(in_hr: float) -> int:
    return _band(in_hr, SNOW_IN_HR, no_travel_inclusive=False)


def classify(wind_mph: float, rain_in: float, snow_in: float, load_lbs: float) -> tuple[int, list[str]]:
    """Checkpoint level is the worst of wind (load-adjusted), rain and snow; reasons name the drivers."""
    wind = wind_level(wind_mph, load_lbs)
    load_note = f" with {load_lbs:,.0f} lb load" if wind != _band(wind_mph, WIND_MPH, True) else ""
    factors = [
        (wind, f"Wind {wind_mph:.0f} mph{load_note}"),
        (rain_level(rain_in), f"Rain {rain_in:.2f} in/hr"),
        (snow_level(snow_in), f"Snow {snow_in:.2f} in/hr"),
    ]
    level = max(f[0] for f in factors)
    reasons = [f"{text} → {LEVEL_NAMES[level]}" for lvl, text in factors if lvl == level and level > LOW]
    return level, reasons


def _ramp(value: float, bounds: tuple) -> float:
    """Piecewise-linear 0..4 through the band bounds, so floor(ramp) matches the band."""
    points = (0, *bounds)
    for i in range(4):
        if value < points[i + 1]:
            return i + max(0.0, value - points[i]) / (points[i + 1] - points[i])
    return 4.0


def score(wind_mph: float, rain_in: float, snow_in: float, load_lbs: float) -> float:
    """Continuous 0-4 risk for the heatmap, consistent with classify() including load escalation."""
    wind = max(_ramp(wind_mph, WIND_MPH), wind_level(wind_mph, load_lbs))
    return min(4.0, max(wind, _ramp(rain_in, RAIN_IN_HR), _ramp(snow_in, SNOW_IN_HR)))


def summarize(owned_miles: list[float], levels: list[int]) -> dict:
    miles_by_level = [0.0] * 5
    for miles, level in zip(owned_miles, levels):
        miles_by_level[level] += miles
    total = sum(miles_by_level)
    avg = sum(level * miles for level, miles in enumerate(miles_by_level)) / total if total else 0.0
    return {
        "miles_by_level": [round(m, 1) for m in miles_by_level],
        "avg_risk": round(avg, 2),
        "max_level": max(levels),
    }


CRITERIA = ("No Travel miles", "Severe miles", "High miles", "average risk", "travel time")


def rank_key(summary: dict, duration_s: float) -> tuple:
    """Fewest No Travel, then Severe, then High miles, then lowest avg risk, then shortest time.

    No Travel ranks ahead of Severe (a No Travel mile is strictly worse than a Severe one).
    Avg risk is compared at 0.1 resolution so near-identical routes fall through to travel time.
    """
    m = summary["miles_by_level"]
    return (m[NO_TRAVEL], m[SEVERE], m[HIGH], round(summary["avg_risk"], 1), duration_s)


def _fmt(criterion: int, value: float) -> str:
    if criterion == 4:
        return f"{int(value // 3600)}h {int(value % 3600 // 60):02d}m"
    return f"{value:g}" if criterion == 3 else f"{value:g} mi"


def _first_difference(a: tuple, b: tuple) -> int | None:
    return next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), None)


def recommend(routes: list[dict]) -> list[dict]:
    """Rank routes (each needs 'summary' and 'duration_s'); sets 'rank' and a human 'why'."""
    keyed = sorted(routes, key=lambda r: rank_key(r["summary"], r["duration_s"]))
    keys = [rank_key(r["summary"], r["duration_s"]) for r in keyed]
    for rank, (route, key) in enumerate(zip(keyed, keys), start=1):
        route["rank"] = rank
        if len(keyed) == 1:
            route["why"] = "Only route option"
            continue
        other, other_name = (keys[1], "the next best route") if rank == 1 else (keys[0], "the recommended route")
        i = _first_difference(key, other)
        if i is None:
            route["why"] = f"Ties with {other_name}"
        else:
            verdict = "Best" if rank == 1 else "Worse"
            route["why"] = f"{verdict} on {CRITERIA[i]}: {_fmt(i, key[i])} vs {_fmt(i, other[i])} on {other_name}"
    return keyed
