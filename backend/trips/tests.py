from datetime import datetime, timedelta, timezone

from django.test import SimpleTestCase

from . import geo, providers
from .risk import HIGH, LOW, MODERATE, NO_TRAVEL, SEVERE, classify, rain_level, recommend, score, snow_level, summarize, wind_level


class RiskBandTests(SimpleTestCase):
    def test_wind_bands(self):
        cases = [(0, LOW), (24.9, LOW), (25, MODERATE), (34.9, MODERATE), (35, HIGH), (44.9, HIGH),
                 (45, SEVERE), (54.9, SEVERE), (55, NO_TRAVEL), (80, NO_TRAVEL)]
        for mph, level in cases:
            self.assertEqual(wind_level(mph, 0), level, mph)

    def test_rain_bands(self):
        cases = [(0, LOW), (0.099, LOW), (0.10, MODERATE), (0.249, MODERATE), (0.25, HIGH), (0.499, HIGH),
                 (0.50, SEVERE), (1.00, SEVERE), (1.001, NO_TRAVEL)]
        for inches, level in cases:
            self.assertEqual(rain_level(inches), level, inches)

    def test_snow_bands(self):
        cases = [(0, LOW), (0.49, LOW), (0.5, MODERATE), (0.99, MODERATE), (1.0, HIGH), (1.99, HIGH),
                 (2.0, SEVERE), (3.0, SEVERE), (3.01, NO_TRAVEL)]
        for inches, level in cases:
            self.assertEqual(snow_level(inches), level, inches)


class LoadRuleTests(SimpleTestCase):
    def test_55_mph_is_no_travel_for_any_load(self):
        self.assertEqual(wind_level(55, 0), NO_TRAVEL)

    def test_45_to_54_mph_over_30k_is_no_travel(self):
        self.assertEqual(wind_level(45, 30_000), SEVERE)
        self.assertEqual(wind_level(45, 30_001), NO_TRAVEL)
        self.assertEqual(wind_level(54.9, 30_001), NO_TRAVEL)

    def test_35_to_44_mph_over_40k_is_severe(self):
        self.assertEqual(wind_level(35, 40_000), HIGH)
        self.assertEqual(wind_level(35, 40_001), SEVERE)
        self.assertEqual(wind_level(44.9, 40_001), SEVERE)

    def test_load_does_not_affect_lower_winds(self):
        self.assertEqual(wind_level(34.9, 80_000), MODERATE)


class ClassifyTests(SimpleTestCase):
    def test_worst_factor_wins_with_reasons(self):
        level, reasons = classify(wind_mph=47, rain_in=0.3, snow_in=0, load_lbs=35_000)
        self.assertEqual(level, NO_TRAVEL)
        self.assertEqual(reasons, ["Wind 47 mph with 35,000 lb load → No Travel"])

    def test_calm_weather_has_no_reasons(self):
        self.assertEqual(classify(10, 0, 0, 20_000), (LOW, []))

    def test_ties_list_every_driver(self):
        level, reasons = classify(wind_mph=36, rain_in=0.3, snow_in=0, load_lbs=0)
        self.assertEqual(level, HIGH)
        self.assertEqual(len(reasons), 2)

    def test_continuous_score_agrees_with_levels(self):
        for wind, rain, snow, load in [(30, 0, 0, 0), (36, 0, 0, 45_000), (46, 0, 0, 35_000), (0, 0.3, 0, 0), (0, 0, 2.5, 0)]:
            level, _ = classify(wind, rain, snow, load)
            self.assertEqual(int(score(wind, rain, snow, load)), level, (wind, rain, snow, load))


class SummaryAndRecommendationTests(SimpleTestCase):
    def test_summary_mile_weighted(self):
        s = summarize([5, 10, 5], [LOW, HIGH, SEVERE])
        self.assertEqual(s["miles_by_level"], [5, 0, 10, 5, 0])
        self.assertEqual(s["avg_risk"], round((0 * 5 + 2 * 10 + 3 * 5) / 20, 2))
        self.assertEqual(s["max_level"], SEVERE)

    @staticmethod
    def route(rid, miles_by_level, avg, duration):
        return {"id": rid, "duration_s": duration, "summary": {"miles_by_level": miles_by_level, "avg_risk": avg}}

    def test_fewest_severe_miles_beats_faster_route(self):
        ranked = recommend([self.route(0, [90, 0, 0, 10, 0], 0.3, 3600), self.route(1, [100, 0, 0, 0, 0], 0.5, 7200)])
        self.assertEqual(ranked[0]["id"], 1)
        self.assertIn("Severe miles", ranked[0]["why"])

    def test_no_travel_ranks_before_severe(self):
        ranked = recommend([self.route(0, [80, 0, 0, 0, 10], 0.4, 3600), self.route(1, [50, 0, 0, 50, 0], 1.5, 3600)])
        self.assertEqual(ranked[0]["id"], 1)

    def test_high_then_avg_risk(self):
        ranked = recommend([self.route(0, [80, 0, 20, 0, 0], 0.4, 3600), self.route(1, [90, 0, 10, 0, 0], 0.9, 9000)])
        self.assertEqual(ranked[0]["id"], 1)
        ranked = recommend([self.route(0, [100, 0, 0, 0, 0], 0.62, 3600), self.route(1, [100, 0, 0, 0, 0], 0.3, 9000)])
        self.assertEqual(ranked[0]["id"], 1)

    def test_similar_avg_risk_falls_through_to_travel_time(self):
        ranked = recommend([self.route(0, [100, 0, 0, 0, 0], 0.32, 5000), self.route(1, [100, 0, 0, 0, 0], 0.28, 4000)])
        self.assertEqual([r["id"] for r in ranked], [1, 0])
        self.assertEqual([r["rank"] for r in ranked], [1, 2])
        self.assertIn("travel time", ranked[0]["why"])


class GeoTests(SimpleTestCase):
    def test_checkpoint_miles(self):
        self.assertEqual(geo.checkpoint_miles(25, 10), [0, 10, 20, 25])
        self.assertEqual(geo.checkpoint_miles(20, 10), [0, 10, 20])

    def test_owned_miles_sum_to_route_length(self):
        owned = geo.owned_miles([0, 10, 20, 25])
        self.assertEqual(owned, [5, 10, 7.5, 2.5])
        self.assertAlmostEqual(sum(owned), 25)

    def test_point_and_time_interpolation(self):
        coords = [(0.0, 0.0), (0.0, 1.0)]
        cum = geo.cumulative_miles(coords)
        lat, lon = geo.point_at(coords, cum, cum[-1] / 2)
        self.assertAlmostEqual(lon, 0.5)
        self.assertEqual(geo.interpolate([0, 10, 20], [0, 600, 900], 15), 750)
        self.assertEqual(geo.interpolate([0, 10], [0, 600], 99), 600)

    def test_risk_segments_cover_route_and_merge_levels(self):
        coords = [(0.0, i / 10) for i in range(11)]
        cum = geo.cumulative_miles(coords)
        positions = geo.checkpoint_miles(cum[-1], 10)
        levels = [LOW, LOW] + [HIGH] * (len(positions) - 2)
        segments = geo.risk_segments(coords, cum, positions, levels)
        self.assertEqual([s["level"] for s in segments], [LOW, HIGH])
        self.assertEqual(segments[0]["coords"][0], coords[0])
        self.assertEqual(segments[-1]["coords"][-1], coords[-1])
        self.assertEqual(segments[0]["coords"][-1], segments[1]["coords"][0])

    def test_corridor_grid_bounded_and_near_route(self):
        coords = [(41.88, -87.63), (39.74, -104.99)]  # Chicago -> Denver, ~920 mi
        cum = geo.cumulative_miles(coords)
        grid, step = geo.corridor_grid([(coords, cum)], buffer_mi=30, max_points=220)
        self.assertGreaterEqual(step, 0.1)
        self.assertTrue(50 < len(grid) <= 220)
        for p in grid:
            self.assertEqual(p, geo.snap(p))
            self.assertLessEqual(min(geo.haversine_mi(p, geo.point_at(coords, cum, m)) for m in range(0, int(cum[-1]), 2)), 31)


class ForecastHourTests(SimpleTestCase):
    def test_wind_nearest_hour_precip_hour_ending_after(self):
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        series = {"t0": t0.timestamp(), "wind": [10, 20, 30], "gust": [0, 0, 0], "rain": [0.0, 0.1, 0.2], "snow": [0, 0, 0]}
        wx = providers.at(series, t0 + timedelta(minutes=20))
        self.assertEqual((wx["wind_mph"], wx["rain_in"]), (10, 0.1))
        wx = providers.at(series, t0 + timedelta(minutes=40))
        self.assertEqual((wx["wind_mph"], wx["rain_in"]), (20, 0.1))
        wx = providers.at(series, t0 + timedelta(hours=9))
        self.assertEqual(wx["wind_mph"], 30)


class TomTomParseTests(SimpleTestCase):
    def test_parse_route_builds_cumulative_time_profile(self):
        raw = {
            "summary": {"lengthInMeters": 32186.88, "travelTimeInSeconds": 1800, "trafficDelayInSeconds": 60},
            "legs": [{"points": [{"latitude": 1, "longitude": 2}, {"latitude": 1.1, "longitude": 2}]},
                     {"points": [{"latitude": 1.1, "longitude": 2}, {"latitude": 1.2, "longitude": 2}]}],
            "guidance": {"instructions": [{"routeOffsetInMeters": 0, "travelTimeInSeconds": 0},
                                          {"routeOffsetInMeters": 16093.44, "travelTimeInSeconds": 600}]},
        }
        route = providers._parse_route(raw)
        self.assertEqual(len(route["coords"]), 4)
        self.assertAlmostEqual(route["length_mi"], 20)
        self.assertEqual(route["profile_s"], [0, 600, 1800])
        self.assertEqual(geo.interpolate(route["profile_mi"], route["profile_s"], 15), 1200)
