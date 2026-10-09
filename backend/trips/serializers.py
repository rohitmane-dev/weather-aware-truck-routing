from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from .geo import haversine_mi
from .providers import HOURLY_VARS

MAX_FORECAST_HOURS = 24 * 10


class PlaceSerializer(serializers.Serializer):
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)
    label = serializers.CharField(max_length=200, required=False, allow_blank=True)


class WeatherPointSerializer(serializers.Serializer):
    """Raw Open-Meteo hourly data the browser fetched for one point (fallback when the server is rate-limited)."""

    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)
    hourly = serializers.DictField()

    def validate_hourly(self, value):
        names = ("time", *HOURLY_VARS)
        if not all(isinstance(value.get(n), list) for n in names):
            raise serializers.ValidationError("Missing hourly series.")
        length = len(value["time"])
        if not 0 < length <= MAX_FORECAST_HOURS or any(len(value[n]) != length for n in names):
            raise serializers.ValidationError("Hourly series have invalid lengths.")
        if not all(v is None or (isinstance(v, (int, float)) and not isinstance(v, bool)) for n in names for v in value[n]):
            raise serializers.ValidationError("Hourly values must be numbers.")
        return {n: value[n] for n in names}


class TripRequestSerializer(serializers.Serializer):
    origin = PlaceSerializer()
    destination = PlaceSerializer()
    departure = serializers.DateTimeField()
    load_lbs = serializers.IntegerField(min_value=0, max_value=80_000)
    interval_miles = serializers.ChoiceField(choices=[10, 25, 50])
    weather = WeatherPointSerializer(many=True, required=False, max_length=1500)

    def validate_departure(self, value):
        now = timezone.now()
        if value < now - timedelta(minutes=10):
            raise serializers.ValidationError("Departure cannot be in the past.")
        if value > now + timedelta(days=7):
            raise serializers.ValidationError("Departure must be within 7 days (forecast horizon).")
        return value

    def validate(self, data):
        o, d = data["origin"], data["destination"]
        if haversine_mi((o["lat"], o["lon"]), (d["lat"], d["lon"])) < 1:
            raise serializers.ValidationError("Origin and destination must be at least 1 mile apart.")
        return data
