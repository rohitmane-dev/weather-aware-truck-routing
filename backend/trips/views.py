from rest_framework.response import Response
from rest_framework.views import APIView

from .providers import ProviderError, geocode
from .serializers import TripRequestSerializer
from .services import plan_trip


class GeocodeView(APIView):
    throttle_scope = "geocode"

    def get(self, request):
        query = request.query_params.get("q", "").strip()[:120]
        if len(query) < 3:
            return Response([])
        try:
            return Response(geocode(query))
        except ProviderError as e:
            return Response({"detail": str(e)}, status=e.status)


class TripView(APIView):
    throttle_scope = "trip"

    def post(self, request):
        serializer = TripRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            return Response(plan_trip(**serializer.validated_data))
        except ProviderError as e:
            return Response({"detail": str(e)}, status=e.status)
