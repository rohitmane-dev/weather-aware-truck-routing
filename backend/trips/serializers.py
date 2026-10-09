from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from .geo import haversine_mi


class PlaceSerializer(serializers.Serializer):
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)
    label = serializers.CharField(max_length=200, required=False, allow_blank=True)


class TripRequestSerializer(serializers.Serializer):
    origin = PlaceSerializer()
    destination = PlaceSerializer()
    departure = serializers.DateTimeField()
    load_lbs = serializers.IntegerField(min_value=0, max_value=80_000)
    interval_miles = serializers.ChoiceField(choices=[10, 25, 50])

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
