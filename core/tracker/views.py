"""HRMWARE Tracker API Definitions

Last Revision Date: June 25 2025 22:39 PM
"""

from typing import Any
import warnings
import json
import ast
from copy import deepcopy
from datetime import datetime

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import FieldError
from rest_framework.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response

from core.helpers import get_traceback
from .models import ActivityLogs, TrackerApps, TrackerAppCategories
from .serializers import ActivityLogsSerializer


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
    def get_main_data(request: Request) -> dict[str, Any]:
        """Retrieves data from request safely.
        
        If data retrieval logic changes, please change this method.
        """

        data_rows: list[dict[str, Any]] = request.data.getlist("allWindows")

        # # Attempting to load json if data_rows is in string format
        # if isinstance(data_rows, str):
        #     original_data_rows = deepcopy(data_rows)
        #     try:
        #         data_rows_json = json.loads(data_rows)
        #         data_rows = data_rows_json
        #     except json.JSONDecodeError:
        #         data_rows = original_data_rows

        # Attempting to load json if data_rows elements are in string format
        original_data_rows = deepcopy(data_rows)
        # try:
        #     data_rows = [json.loads(data) for data in data_rows if isinstance(data, str)]
        # except json.JSONDecodeError:
        #     data_rows = [ast.literal_eval(data) for data in data_rows if isinstance(data, str)]
        #     data_rows = original_data_rows
        try:
            modified_data_rows = [ast.literal_eval(data) for data in data_rows]
            data_rows = modified_data_rows
        except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
            try:
                modified_data_rows = [json.loads(data) if isinstance(data_rows, str) else data for data in data_rows]
                data_rows = modified_data_rows
            except json.JSONDecodeError:
                data_rows = original_data_rows

        return data_rows


    @staticmethod
    def extract_data(data: dict[str, Any]) -> dict[str, Any | None]:
        """Extracts required data from provided dictionary safely.
        
        The returned dictionary would be suitable for use in
        creating a record in the ActivityLogs model.
        If data retrieval logic changes, or model definition 
        changes for which data has to be entered, please change this method.
        """

        data_dict = {
            "start_timestamp": datetime.strptime(data.get("firstUsed"), "%H:%M:%S %p"),
            "end_timestamp": datetime.strptime(data.get("lastUsed"), "%H:%M:%S %p"),
            "duration": data.get("totalUsage"),
            "is_active": data.get("isActive"),
            "window_title": data.get("title"),
            "app": data.get("name"),
            # This one is not expected to be sent
            "productivity_status": data.get("productivityStatus", "neutral"), 
        }

        if isinstance(data_dict["app"], str):
            data_dict["app"] = data_dict["app"].strip().lower()

        return data_dict


    def get_superuser(self):
        """This method is to be only used in development"""

        Users = get_user_model()
        try:
            user = Users.objects.filter(is_superuser=True).first()
        except FieldError:
            user = Users.objects.filter(is_admin=True).first()

        if user is None:
            user = Users.objects.create_superuser("test", "test@example.com", "password")

        return user


    def post(self, request: Request):
        """Main API intended to receive tracker response"""

        try:
            data_rows = self.get_main_data(request)

            activity_logs = []
            for data in data_rows:
                extracted_data = self.extract_data(data)

                tracker_app = TrackerApps.objects.filter(name=extracted_data["app"]).first()
                if tracker_app is None:
                    tracker_app = self.create_new_app(app_name=extracted_data["app"])

                extracted_data["category"] = tracker_app.category
                extracted_data["productivity_status"] = tracker_app.category.productivity_status_type
                extracted_data["app"] = tracker_app

                activity_log = None
                try:
                    activity_log = ActivityLogs.objects.create(
                        **extracted_data,
                        user=request.user,
                    )
                except ValueError:
                    # Can be raised due to anonymous user
                    if (isinstance(request.user, AnonymousUser)
                        # and settings.DEBUG == True
                        ):
                        activity_log = ActivityLogs.objects.create(
                            **extracted_data,
                            user=self.get_superuser(),
                        )

                activity_logs.append(activity_log)

            response = ActivityLogsSerializer(activity_logs, many=True).data
            return Response(status=200, data=response)
        except Exception as e:
            # print(json.dumps(get_traceback(), indent=4))
            # return Response(status=500, data=str(e))
            return Response(status=500, data=get_traceback())
