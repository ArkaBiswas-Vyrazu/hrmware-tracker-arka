from django.urls import path
from .views import TrackerAPIView, TrackerTimeBarView

urlpatterns = [
    path("", TrackerAPIView.as_view(), name="tracker-api-view"),
    path("time-bar", TrackerTimeBarView.as_view(), name="tracker-time-bar-view"),
]
