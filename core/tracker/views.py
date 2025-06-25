"""HRMWARE Tracker API Definitions

Last Revision Date: June 25 2025 22:39 PM
"""

from typing import Any
import warnings
import json
from copy import deepcopy

from django.conf import settings
from rest_framework.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response

from core.helpers import get_traceback
from .models import ActivityLogs, TrackerApps, TrackerAppCategories
from .serializers import ActivityLogsDataSerializer, ActivityLogsSerializer


class TrackerAPIView(APIView):
    @staticmethod
    def get_default_category() -> TrackerAppCategories:
        default_category: str = settings.DEFAULT_TRACKER_CATEGORY
        if default_category is None:
            msg = f"No default category found, setting category " \
                  f"as {settings.TRACKER_CATEGORY_PLACEHOLDER}"
            warnings.warn(msg)
            default_category: str = settings.TRACKER_CATEGORY_PLACEHOLDER

        tracker_app_category, _ = (
            TrackerAppCategories.objects
            .get_or_create(name=default_category)
        )

        return tracker_app_category

    def create_new_app(self, app_name: str) -> TrackerApps:
        default_category = self.get_default_category()
        tracker_app = TrackerApps.objects.create(
            name=app_name,
            category=default_category,
        )
        return tracker_app

    @staticmethod
    def get_main_data(request: Request) -> tuple[dict[str, Any] | Any, bool]:
        """Retrieves data from request safely.
        
        If data retrieval logic changes, please change this method.
        """

        # data_rows: list[dict[str, Any]] = request.data.getlist("allWindows")

        # # Attempting to load json if data_rows is in string format
        # if isinstance(data_rows, str):
        #     original_data_rows = deepcopy(data_rows)
        #     try:
        #         data_rows = json.loads(data_rows)
        #     except json.JSONDecodeError:
        #         data_rows = original_data_rows

        # # Attempting to load json if data_rows elements are in string format
        # original_data_rows = data_rows
        # try:
        #     data_rows = [json.loads(data) for data in data_rows if isinstance(data, str)]
        # except json.JSONDecodeError:
        #     data_rows = original_data_rows

        serializer = ActivityLogsDataSerializer(data=request.data)
        if not serializer.is_valid():
            return serializer.errors, False
        
        data_rows = serializer.validated_data.get("allWindows")
        print("Data rows: ", data_rows)
        # Attempting to load json if data_rows elements are in string format
        original_data_rows = data_rows
        try:
            data_rows = [json.loads(data) for data in data_rows if isinstance(data, str)]
        except json.JSONDecodeError:
            data_rows = original_data_rows

        return data_rows, True

    @staticmethod
    def extract_data(data: dict[str, Any]) -> dict[str, Any | None]:
        """Extracts required data from provided dictionary safely.
        
        The returned dictionary would be suitable for use in
        creating a record in the ActivityLogs model.
        If data retrieval logic changes, or model definition 
        changes for which data has to be entered, please change this method.
        """

        data_dict = {
            "start_timestamp": data.get("firstUsed"),
            "end_timestamp": data.get("lastUsed"),
            "duration": data.get("totalUsage"),
            "is_active": data.get("isActive"),
            "window_title": data.get("title"),
            "app": data.get("name"),
            # This one is not expected to be sent
            "productivity_status": data.get("productivityStatus", "neutral"), 
        }

        if isinstance(data["app"], str):
            data["app"] = data["app"].strip().lower()

        return data_dict

    def post(self, request: Request):
        """Main API intended to receive tracker response"""

        try:
            data_rows, status = self.get_main_data(request)
            if status is not True:
                return Response(status=400, data=data_rows)

            activity_logs = []
            for data in data_rows:
                extracted_data = self.extract_data(data)

                tracker_app = TrackerApps.objects.filter(name=extracted_data["app"]).first()
                if tracker_app is None:
                    self.create_new_app(app_name=extracted_data["app"])

                extracted_data["productivity_status"] = tracker_app.category.productivity_status
                activity_log = ActivityLogs.objects.create(
                    **extracted_data,
                    user=request.user,
                )
                activity_logs.append(activity_log)

            response = ActivityLogsSerializer(activity_logs, many=True).data
            return Response(status=200, data=response)
        except Exception as e:
            print(json.dumps(get_traceback(), indent=4))
            return Response(status=500, data=str(e))
