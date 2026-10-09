from django.urls import path

from .views import GeocodeView, TripView

urlpatterns = [
    path("geocode", GeocodeView.as_view()),
    path("trip", TripView.as_view()),
]
