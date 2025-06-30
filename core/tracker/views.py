"""HRMWARE Tracker API Definitions

Last Revision Date: June 30 2025 14:48 PM
"""

from typing import Any, TypedDict, Optional
import warnings
import json
from datetime import datetime, timedelta, timezone as std_timezone

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import FieldError
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response

from core.helpers import get_traceback, uniqid
from .models import (
    ActivityLogs,
    TrackerApps,
    TrackerAppCategories,
    TimeSegments
)
from .serializers import (
    ActivityLogsSerializer,
    ActivityLogsDataSerializer,
    TimeSegmentsSerializer,
    GetTimeSegmentsSerializer
)


class TrackerAPIView(APIView):
    serializer_class = ActivityLogsDataSerializer

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
    def get_main_data(request: Request) -> tuple[dict[str, Any], bool]:
        """Retrieves data from request safely.
        
        If data retrieval logic changes, please change this method.
        """

        serializer = ActivityLogsDataSerializer(data=request.data)
        if not serializer.is_valid():
            return serializer.errors, False
        data = serializer.validated_data
        return data, True

    @staticmethod
    def add_now_date_to_time(time: str, format="%I:%M:%S %p") -> datetime:
        time_object = datetime.strptime(time, format).time()
        date = datetime.combine(timezone.now().date(), time_object, tzinfo=None)
        return date

    def extract_data(self, data: dict[str, Any]) -> dict[str, Any | None]:
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

        data_dict["start_timestamp"] = self.add_now_date_to_time(data_dict["start_timestamp"])
        data_dict["end_timestamp"] = self.add_now_date_to_time(data_dict["end_timestamp"])

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
            user = Users.objects.create_superuser("test", "test@example.com", "password", employee_id=uniqid())

        return user

    def create_time_segments(self, main_data: dict, user):
        """Create time segment data for received activity logs"""

        all_windows = [self.extract_data(data) for data in main_data.get("allWindows", [])]
        idle_states = main_data.get("idleStates", [])

        time_segments = []
        for data in all_windows:
            app_category = (
                TrackerApps.objects
                .filter(name=data["app"])
                .first()
                .category
            )

            time_segment = TimeSegments.objects.create(
                date=timezone.now().date(),
                start_time=data.get("start_timestamp"),
                end_time=data.get("end_timestamp"),
                duration=data.get("duration"),
                segment_type=app_category.productivity_status_type,
                user=user,
            )

            time_segments.append(time_segment)

        for data in idle_states:
            time_segment = TimeSegments.objects.create(
                date=timezone.now().date(),
                start_time=self.add_now_date_to_time(data.get("startTime")),
                end_time=self.add_now_date_to_time(data.get("endTime")),
                duration=data.get("duration"),
                segment_type="idle",
                user=user,
            )

            time_segments.append(time_segment)

        return time_segments

    def post(self, request: Request):
        """Main API intended to receive tracker response"""

        try:
            main_data, status = self.get_main_data(request)
            if status is False:
                return Response(status=400, data=main_data.errors)

            file_name = "hrmware-tracker-sample-response.json"
            with open(file_name, "a") as file:
                file.write("\n")
                file.write(json.dumps(main_data, indent=4))
                file.write("\n")

            activity_logs = []
            request_user = request.user
            if isinstance(request_user, AnonymousUser) and settings.DEBUG is True:
                warnings.warn("No request user found, using default superuser")
                request_user = self.get_superuser()

            for data in main_data.get("allWindows"):
                extracted_data = self.extract_data(data)

                tracker_app = TrackerApps.objects.filter(name=extracted_data["app"]).first()
                if tracker_app is None:
                    tracker_app = self.create_new_app(app_name=extracted_data["app"])

                extracted_data["category"] = tracker_app.category
                extracted_data["productivity_status"] = tracker_app.category.productivity_status_type
                extracted_data["app"] = tracker_app

                activity_log = None
                activity_log = ActivityLogs.objects.create(
                    **extracted_data,
                    user=request_user,
                )

                activity_logs.append(activity_log)

            activity_logs = ActivityLogsSerializer(activity_logs, many=True).data
            time_segments = self.create_time_segments(main_data, request_user)

            time_segments = TimeSegmentsSerializer(time_segments, many=True).data

            response_data = {
                "activity_logs": activity_logs,
                "time_segments": time_segments,
            }

            return Response(status=200, data=response_data)

        except Exception as e:
            print(json.dumps(get_traceback(), indent=4))

            with open("errors.log", "a") as file:
                file.write("Time recorded: " + timezone.now().strftime("%Y-%m-%d %H:%M:%S %p") + "\n")
                file.write(json.dumps(get_traceback(), indent=4))
                file.write("\n\n")

            return Response(status=500, data=get_traceback())


class TrackerTimeBarView(APIView):
    def check_overlap(self,
                      first_interval: tuple[datetime, datetime],
                      second_interval: tuple[datetime, datetime]) -> bool:
        """Reference: https://www.youtube.com/watch?v=daLeQLFtLLI"""

        max_start_time = max(first_interval[0].timestamp(), second_interval[0].timestamp())
        min_end_time = min(first_interval[1].timestamp(), second_interval[1].timestamp())
    
        return max_start_time <= min_end_time

    def get(self, request: Request):
        """Main API to receive time bar data"""

        try:
            serializer = GetTimeSegmentsSerializer(data=request.query_params)
            if not serializer.is_valid():
                return Response(status=400, data=serializer.errors)

            data = serializer.validated_data

            date: datetime.date = data.get("date")
            user = data.get("user")
            time_start: Optional[datetime.time] = data.get("time_start")
            time_end: Optional[datetime.time] = data.get("time_end")

            time_segments = (
                TimeSegments.objects
                .filter(
                    user=user,
                    date=date
                )
                .order_by("start_time")
            )

            class TimeBarDataItem(TypedDict):
                """Type Definition for Time Bar Data Items"""

                start_time: datetime
                end_time: datetime
                productivity_status_map: dict[str, int]

            time_bar_data: list[TimeBarDataItem] = []

            for time_segment in time_segments:
                overlapped_insert = False
                
                for record in time_bar_data:
                    overlap = self.check_overlap(
                        first_interval=(record["start_time"], record["end_time"]),
                        second_interval=(time_segment.start_time, time_segment.end_time)
                    )
                    if overlap is True:
                        record["start_time"] = min(record["start_time"], time_segment.start_time)
                        record["end_time"] = max(record["end_time"], time_segment.end_time)
                        if time_segment.segment_type in record["productivity_status_map"]:
                            record["productivity_status_map"][time_segment.segment_type] += 1
                        else:
                            record["productivity_status_map"][time_segment.segment_type] = 1
                        overlapped_insert = True
                        break
                
                if overlapped_insert is True:
                    continue

                time_bar_data_record: TimeBarDataItem = {
                    "start_time": time_segment.start_time,
                    "end_time": time_segment.end_time,
                    "productivity_status_map": {
                        time_segment.segment_type: 1
                    },
                }
                time_bar_data.append(time_bar_data_record)

            time_bar_data_response: list[TimeBarDataItem] = []
            for time_bar_record in time_bar_data:
                # Reference: https://stackoverflow.com/questions/268272/getting-key-with-maximum-value-in-dictionary
                time_bar_data_response_segment = {
                    "start_time": time_bar_record["start_time"].strftime("%I:%M:%S %p"),
                    "end_time": time_bar_record["end_time"].strftime("%I:%M:%S %p"),
                    "productivity_status": max(time_bar_record["productivity_status_map"], key=time_bar_record["productivity_status_map"].get)
                }

                time_bar_data_response.append(time_bar_data_response_segment)

            # Adding Away time data
            # Here, it is defined as any time that was not found in record
            if time_start is not None and time_end is not None:
                final_time_bar_response = []
                for index, time_bar_record in enumerate(time_bar_data_response):
                    if index == 0:
                        start_timestamp = datetime.strptime(time_start, "%H:%M:%S")
                        end_timestamp = datetime.strptime(time_bar_record["start_time"], "%I:%M:%S %p")

                    elif index == len(time_bar_data_response) - 1:
                        start_timestamp = datetime.strptime(time_bar_record["end_time"], "%I:%M:%S %p")
                        end_timestamp = datetime.strptime(time_end, "%H:%M:%S")

                    else:
                        start_timestamp = datetime.strptime(time_bar_data_record["end_time"], "%I:%M:%S %p")
                        end_timestamp = datetime.strptime(time_bar_data_response[index+1]["start_time"], "%I:%M:%S %p")

                    if start_timestamp < end_timestamp and end_timestamp - start_timestamp != timedelta(seconds=settings.TIME_GAP_LIMIT):
                        time_segment = {
                            "start_time": start_timestamp.strftime("%I:%M:%S %p"),
                            "end_time": end_timestamp.strftime("%I:%M:%S %p"),
                            "productivity_status": "away"
                        }
                        final_time_bar_response.append(time_segment)
                    
                    final_time_bar_response.append(time_bar_record)

                final_time_bar_response.sort(key=lambda x: x.get("start_time"))
                time_bar_data_response = final_time_bar_response

            return Response(status=200, data={"time_bar_data": time_bar_data_response})

        except Exception as e:
            print(json.dumps(get_traceback(), indent=4))

            with open("errors.log", "a") as file:
                file.write("Time recorded: " + timezone.now().strftime("%Y-%m-%d %H:%M:%S %p") + "\n")
                file.write(json.dumps(get_traceback(), indent=4))
                file.write("\n\n")

            return Response(status=500, data=get_traceback())


class TrackerProductivityStatusView(APIView):
    def get(self, request: Request):
        try:
            pass

        except Exception as e:
            print(json.dumps(get_traceback(), indent=4))

            with open("errors.log", "a") as file:
                file.write("Time recorded: " + timezone.now().strftime("%Y-%m-%d %H:%M:%S %p" + "\n"))
                file.write(json.dumps(get_traceback(), indent=4))
                file.write("\n\n")
            
            return Response(status=500, data=get_traceback())
