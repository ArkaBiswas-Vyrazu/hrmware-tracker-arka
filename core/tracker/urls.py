from django.urls import path
from .views import (
    TrackerAPIView,
    TrackerTimeBarView,
    TrackerProductivityStatusView,
    TrackerBasicTimeDetailsView,
    TrackerWeeklySummary,    
)

urlpatterns = [
    path("", TrackerAPIView.as_view(), name="tracker-api-view"),
    path("time-bar", TrackerTimeBarView.as_view(), name="tracker-time-bar-view"),
    path("productivity-status", TrackerProductivityStatusView.as_view(), name="tracker-productivity-status-view"),
    path("basic-details", TrackerBasicTimeDetailsView.as_view(), name="tracker-basic-time-details-view"),
    path("weekly-summary", TrackerWeeklySummary.as_view(), name="tracker-weekly-summary-view"),
]
