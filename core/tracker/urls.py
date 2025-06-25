from django.urls import path

from .views import BasicAPI

urlpatterns = [
    path("", BasicAPI.as_view(), name="basic-api"),
]
