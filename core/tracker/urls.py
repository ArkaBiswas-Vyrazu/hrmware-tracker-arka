from django.urls import path
from .views import TrackerAPIView

urlpatterns = [
    path("", TrackerAPIView.as_view(), name="tracker-api-view"),
]
