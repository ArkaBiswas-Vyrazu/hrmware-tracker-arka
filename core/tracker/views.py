"""HRMWARE Tracker API Definitions

Last Revision Date: June 30 2025 14:48 PM
"""

from typing import Any, TypedDict, Optional
import warnings
import json
from datetime import datetime, timedelta, timezone as std_timezone
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import FieldError
from django.utils import timezone
from django.db.models.query import QuerySet
from rest_framework.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from core.helpers import get_traceback, uniqid
from .typing import TimeTracker, TimeBarDataItem
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
    GetTimeSegmentsSerializer,
    GetWeeklyHoursSerializer
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

        all_windows = (
            [
                self.extract_data(data) | {"activity_log": data.get("activity_logs", {}).get(data.get("id"))}
                for data in main_data.get("allWindows", [])
            ]
        )
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
                activity_log=data.get("activity_log")
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
                activity_log=None
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

                activity_log = ActivityLogs.objects.create(
                    **extracted_data,
                    user=request_user,
                )

                activity_logs.append(activity_log)

                # Tracking created activity log in main data
                # for creating time segments later
                if "activity_logs" not in main_data:
                    main_data["activity_logs"] = {}

                # Assuming each id passed is unique
                main_data["activity_logs"][data.get("id")] = activity_log

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

    def convert_timezones(self,
                        time: str,
                        format="%H:%M:%S",
                        year=datetime.now().year,
                        timezone=settings.TIME_ZONE,
                        to_timezone="UTC") -> datetime:
        """Convert time to localtime
        
        By default, time is assumed to be settings.TIME_ZONE,
        format is assumed to be %H:%M:%S by default, and
        time will be converted to UTC time by default. Also,
        the current year is assumed by default, as this determines
        what timezone data to use. Please ensure this is accurately used,
        and you should refer to the [Official IANA Database](https://www.iana.org/time-zones)
        for more information.
        """

        return (
            datetime.strptime(time, format)
            .replace(year=year, tzinfo=ZoneInfo(timezone))
            .astimezone(ZoneInfo(to_timezone))
        )

    def fetch_time_bar_considering_overlaps(self, time_segments: QuerySet[TimeSegments]):
        """Get all time segments as groups with assigned productivity status
        
        In this method, productivity status is calculated on majority purpose,
        and is useful for an abstract view of productivity. This may, however,
        not be a completely accurate view of the time bar.
        """

        time_bar_data: list[TimeBarDataItem] = []

        for time_segment in time_segments:
            overlapped_insert = False
            
            for record in time_bar_data:
                overlap = self.check_overlap(
                    first_interval=(record["start_time"], record["end_time"]),
                    second_interval=(time_segment.start_time, time_segment.get_actual_end_time())
                )
                if overlap is True:
                    record["start_time"] = min(record["start_time"], time_segment.start_time)
                    record["end_time"] = max(record["end_time"], time_segment.get_actual_end_time())
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
                "end_time": time_segment.get_actual_end_time(),
                "productivity_status_map": {
                    time_segment.segment_type: 1
                },
            }
            time_bar_data.append(time_bar_data_record)

        return time_bar_data

    def fetch_time_bar_without_overlaps(self, time_segments: QuerySet[TimeSegments]):
        """Get all time segments as groups with assigned productivity status
        
        In this process, each and every time segment is treated as it's own. This means
        that any time segment that may be found to overlap will be divided into sub time
        segments that should accurately depict the time segments.

        This method is to be considered the default way to fetch the time bar as it
        provides more granularity.
        """

        time_bar_data = []

        for index, time_segment in enumerate(time_segments):
            overlapped_insert = False
            time_segments_to_check = time_segments.exclude(id=getattr(time_segment, "id"))

            for time_segment_record in time_segments_to_check:
                overlap = self.check_overlap(
                    first_interval=(time_segment_record.start_time, time_segment_record.get_actual_end_time()),
                    second_interval=(time_segment.start_time, time_segment.get_actual_end_time()),
                )

                if overlap is True:
                    overlapped_insert = True
                    break
            
            if overlapped_insert is not True:
                time_bar_data_record = {
                    "start_time": time_segment.start_time,
                    "end_time": time_segment.get_actual_end_time(),
                    "productivity_status": time_segment.segment_type,
                }
                time_bar_data.append(time_bar_data_record)
                continue

            change_behind = (index != 0)
            change_ahead = (index != len(time_segments) - 1)

            # For tracking original values if encountered
            # behind_time_segment_start_time: Optional[datetime] = None
            # ahead_time_segment_end_time: Optional[datetime] = None

            if change_behind is True:
                behind_time_segment = {
                    "start_time": time_segments[index-1].start_time,
                    "end_time": abs(time_segment.start_time - time_segments[index-1].get_actual_end_time()),
                    "productivity_status": time_segments[index-1].segment_type,
                }

                time_bar_data.append(behind_time_segment)
            
            current_time_segment = {
                "start_time": time_segment.start_time,
                "end_time": time_segment.get_actual_end_time(),
                "productivity_status": time_segment.segment_type,
            }
            time_bar_data.append(current_time_segment)

            if change_ahead is True:
                ahead_time_segment = {
                    "start_time": abs(time_segments[index+1].start_time - time_segment.get_actual_end_time()),
                    "end_time": time_segments[index+1].get_actual_end_time(),
                    "productivity_status": time_segments[index+1].segment_type,
                }

                time_bar_data.append(ahead_time_segment)

        return time_bar_data

    @extend_schema(parameters=[
        OpenApiParameter(
            name="date", location=OpenApiParameter.QUERY,
            required=True, type=OpenApiTypes.DATE,
            default=datetime.now().date()),
        OpenApiParameter(
            name="user", location=OpenApiParameter.QUERY,
            required=True, type=OpenApiTypes.STR),
        OpenApiParameter(
            name="time_start", location=OpenApiParameter.QUERY,
            required=False, type=OpenApiTypes.TIME,
            default=timezone.localtime(timezone.now()).time().strftime("%H:%M:%S")),
        OpenApiParameter(
            name="time_end", location=OpenApiParameter.QUERY,
            required=False, type=OpenApiTypes.TIME,
            default=timezone.localtime(timezone.now()).time().strftime("%H:%M:%S")),
        OpenApiParameter(
            name="fine_grained", location=OpenApiParameter.QUERY,
            required=False, type=OpenApiTypes.BOOL,
            default=True),
    ])
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

            fine_grained: bool = data.get("fine_grained", True)
            if fine_grained is True:
                time_bar_data = self.fetch_time_bar_without_overlaps(time_segments=time_segments)
            else:
                time_bar_data = self.fetch_time_bar_considering_overlaps(time_segments=time_segments)

            time_bar_data_response: list[TimeBarDataItem] = []
            for time_bar_record in time_bar_data:
                # Reference: https://stackoverflow.com/questions/268272/getting-key-with-maximum-value-in-dictionary
                time_bar_data_response_segment = {
                    "start_time": time_bar_record["start_time"].strftime("%H:%M:%S %p"),
                    "end_time": time_bar_record["end_time"].strftime("%H:%M:%S %p"),
                    "productivity_status": max(time_bar_record["productivity_status_map"], key=time_bar_record["productivity_status_map"].get)
                }

                time_bar_data_response.append(time_bar_data_response_segment)

            # Adding Away time data
            # Here, it is defined as any time that was not found in record
            # away_entries_not_created = False
            # check_away_time_segment_entry = TimeSegments.objects.filter(user=user, date=date, segment_type="away")
            # if check_away_time_segment_entry.count() != 0:
            #     return Response(status=200, data={"time_bar_data": time_bar_data_response})

            if time_start is not None and time_end is not None:
                # IMP NOTE: Following sets time_start and time_end to settings.TIME_ZONE time
                # If this is not intended please remove or modify this

                time_start = self.convert_timezones(time_start).strftime("%H:%M:%S")
                time_end = self.convert_timezones(time_end).strftime("%H:%M:%S")

                final_time_bar_response = []
                for index, time_bar_record in enumerate(time_bar_data_response):
                    if index == 0:
                        # start_timestamp = datetime.strptime(time_start, "%H:%M:%S")
                        # end_timestamp = datetime.strptime(time_bar_record["start_time"], "%H:%M:%S %p").replace(tzinfo=ZoneInfo("UTC"))
                        start_timestamp = self.convert_timezones(time_start, timezone="UTC", to_timezone="UTC")
                        end_timestamp = self.convert_timezones(time_bar_record["start_time"], format="%H:%M:%S %p", timezone="UTC", to_timezone="UTC")

                    elif index == len(time_bar_data_response) - 1:
                        # start_timestamp = datetime.strptime(time_bar_record["end_time"], "%H:%M:%S %p").replace(tzinfo=ZoneInfo("UTC"))
                        # end_timestamp = datetime.strptime(time_end, "%H:%M:%S").replace(tzinfo=ZoneInfo("UTC"))

                        start_timestamp = self.convert_timezones(time_bar_record["end_time"], format="%H:%M:%S %p", timezone="UTC", to_timezone="UTC")
                        end_timestamp = self.convert_timezones(time_end, timezone="UTC", to_timezone="UTC")

                    else:
                        # start_timestamp = datetime.strptime(time_bar_record["end_time"], "%H:%M:%S %p").replace(tzinfo=ZoneInfo("UTC"))
                        # end_timestamp = datetime.strptime(time_bar_data_response[index+1]["start_time"], "%H:%M:%S %p").replace(tzinfo=ZoneInfo("UTC"))

                        start_timestamp = self.convert_timezones(time_bar_record["end_time"], format="%H:%M:%S %p", timezone="UTC", to_timezone="UTC")
                        end_timestamp = self.convert_timezones(time_bar_data_response[index+1]["start_time"], format="%H:%M:%S %p", timezone="UTC", to_timezone="UTC")

                    if (start_timestamp < end_timestamp
                        and not end_timestamp - start_timestamp <= timedelta(seconds=settings.TIME_GAP_LIMIT)):
                        # Creating time segment entry for faster fetch
                        # time_segment = TimeSegments.objects.create(
                        #     date=date,
                        #     start_time=datetime.combine(date, start_timestamp.time())+timedelta(seconds=1),
                        #     end_time=datetime.combine(date, end_timestamp.time())-timedelta(seconds=1),
                        #     duration=((end_timestamp + timedelta(seconds=1)) - start_timestamp).total_seconds(),
                        #     segment_type="away",
                        #     user=user,
                        # )

                        # time_segment = {
                        #     "start_time": start_timestamp.strftime("%H:%M:%S %p"),
                        #     "end_time": end_timestamp.strftime("%H:%M:%S %p"),
                        #     "productivity_status": "away"
                        # }

                        # Creating time_segment and converting it to localtime
                        time_segment = {
                            "start_time": start_timestamp.astimezone(ZoneInfo(settings.TIME_ZONE)).strftime("%H:%M:%S"),
                            "end_time": end_timestamp.astimezone(ZoneInfo(settings.TIME_ZONE)).strftime("%H:%M:%S"),
                            "productivity_status": "away"
                        }

                        final_time_bar_response.append(time_segment)

                    if len(time_bar_data_response) != 1:
                        # Converting time_bar_record times to localtime
                        time_bar_record["start_time"] = (
                            self.convert_timezones(
                                time_bar_record["start_time"],
                                format="%H:%M:%S %p",
                                timezone="UTC",
                                to_timezone=settings.TIME_ZONE
                            )
                            .strftime("%H:%M:%S %p")
                        )
                        time_bar_record["end_time"] = (
                            self.convert_timezones(
                                time_bar_record["end_time"],
                                format="%H:%M:%S %p",
                                timezone="UTC",
                                to_timezone=settings.TIME_ZONE
                                )
                                .strftime("%H:%M:%S %p")
                            )

                        final_time_bar_response.append(time_bar_record)
                        continue

                    # In case there is only one time_bar_record
                    if len(time_bar_data_response) == 1:
                        start_timestamp = self.convert_timezones(time_bar_record["end_time"], format="%H:%M:%S %p", timezone="UTC", to_timezone="UTC")
                        end_timestamp = self.convert_timezones(time_end, timezone="UTC", to_timezone="UTC")

                        last_away_time_segment = None
                        if (start_timestamp < end_timestamp
                            and not end_timestamp - start_timestamp <= timedelta(seconds=settings.TIME_GAP_LIMIT)):
                            last_away_time_segment = {
                                "start_time": start_timestamp.astimezone(ZoneInfo(settings.TIME_ZONE)).strftime("%H:%M:%S"),
                                "end_time": end_timestamp.astimezone(ZoneInfo(settings.TIME_ZONE)).strftime("%H:%M:%S"),
                                "productivity_status": "away"
                            }

                        time_bar_record["start_time"] = (
                            self.convert_timezones(
                                time_bar_record["start_time"],
                                format="%H:%M:%S %p",
                                timezone="UTC",
                                to_timezone=settings.TIME_ZONE
                            )
                            .strftime("%H:%M:%S %p")
                        )
                        time_bar_record["end_time"] = (
                            self.convert_timezones(
                                time_bar_record["end_time"],
                                format="%H:%M:%S %p",
                                timezone="UTC",
                                to_timezone=settings.TIME_ZONE
                                )
                                .strftime("%H:%M:%S %p")
                            )

                        final_time_bar_response.append(time_bar_record)
                        if last_away_time_segment is not None:
                            final_time_bar_response.append(last_away_time_segment)

                final_time_bar_response.sort(key=lambda x: x.get("start_time"))
                time_bar_data_response = final_time_bar_response
            # else:
            #     away_entries_not_created = True
            #     warnings.warn("To get away time data, please pass a valid start_time and end_time")

            # away_msg = "To get away time data, please pass a valid start_time and end_time"
            return Response(
                status=200,
                data={
                    # **({"msg": away_msg} if away_entries_not_created is True else {}),
                    "time_bar_data": time_bar_data_response
                },
            )

        except Exception as e:
            print(json.dumps(get_traceback(), indent=4))

            with open("errors.log", "a") as file:
                file.write("Time recorded: " + timezone.now().strftime("%Y-%m-%d %H:%M:%S %p") + "\n")
                file.write(json.dumps(get_traceback(), indent=4))
                file.write("\n\n")

            return Response(status=500, data=get_traceback())


class TrackerProductivityStatusView(APIView):
    @staticmethod
    def format_time(time_tracker: TimeTracker) -> dict[str, str]:
        formatted_time_tracker = {}
        for key, value in time_tracker.items():
            time_object = timedelta(seconds=value)
            mins, seconds = divmod(value, 60)
            hours, minutes = divmod(mins, 60)

            result = ""

            if time_object.days is not None and time_object.days != 0:
                result += f"{time_object.days} day{abs(time_object.days) != 1 and "s" or ""} "
            if hours is not None and hours != 0:
                result += f"{hours}h "
            if minutes is not None and minutes != 0:
                result += f"{minutes}m "
            if seconds is not None and seconds != 0:
                result += f"{seconds}s "

            if result == "":
                result = "0s"

            formatted_time_tracker[key] = result.strip()
        
        return formatted_time_tracker

    @extend_schema(parameters=[
        OpenApiParameter(
            name="date", location=OpenApiParameter.QUERY,
            required=True, type=OpenApiTypes.DATE,
            default=datetime.now().date()),
        OpenApiParameter(
            name="user", location=OpenApiParameter.QUERY,
            required=True, type=OpenApiTypes.STR),
    ])
    def get(self, request: Request):
        try:
            serializer = GetTimeSegmentsSerializer(data=request.query_params)
            if not serializer.is_valid():
                return Response(status=400, data=serializer.errors)
            
            data = serializer.validated_data
            date: datetime.date = data.get("date")
            user = data.get("user")

            activity_logs = ActivityLogs.objects.filter(
                user=user,
                start_timestamp__date=date,
                end_timestamp__date=date,
            )

            time_tracker = {
                "productive_time": 0,
                "non_productive_time": 0,
                "neutral_time": 0
            }

            for activity_log in activity_logs:
                time_tracker[f"{activity_log.productivity_status}_time"] += activity_log.duration

            time_tracker = self.format_time(time_tracker)
            return Response(status=200, data={"productivity_tracker": time_tracker})

        except Exception as e:
            print(json.dumps(get_traceback(), indent=4))

            with open("errors.log", "a") as file:
                file.write("Time recorded: " + timezone.now().strftime("%Y-%m-%d %H:%M:%S %p" + "\n"))
                file.write(json.dumps(get_traceback(), indent=4))
                file.write("\n\n")

            return Response(status=500, data=get_traceback())


class TrackerBasicTimeDetailsView(APIView):
    @staticmethod
    def format_time(time: float) -> str:
        time_object = timedelta(seconds=time)
        mins, seconds = divmod(time, 60)
        hours, minutes = divmod(mins, 60)

        result = ""

        if time_object.days is not None and time_object.days != 0:
            result += f"{time_object.days} day{abs(time_object.days) != 1 and "s" or ""} "
        if hours is not None and hours != 0:
            result += f"{int(hours)}h "
        if minutes is not None and minutes != 0:
            result += f"{int(minutes)}m "
        if seconds is not None and seconds != 0:
            result += f"{int(seconds)}s "

        if result == "":
            result = "0s"
        
        return result

    @extend_schema(parameters=[
        OpenApiParameter(
            name="date", location=OpenApiParameter.QUERY,
            required=True, type=OpenApiTypes.DATE,
            default=datetime.now().date()),
        OpenApiParameter(
            name="user", location=OpenApiParameter.QUERY,
            required=True, type=OpenApiTypes.STR),
        OpenApiParameter(
            name="time_start", location=OpenApiParameter.QUERY,
            required=True, type=OpenApiTypes.TIME,
            default=timezone.localtime(timezone.now()).time().strftime("%H:%M:%S")),
        OpenApiParameter(
            name="time_end", location=OpenApiParameter.QUERY,
            required=True, type=OpenApiTypes.TIME,
            default=timezone.localtime(timezone.now()).time().strftime("%H:%M:%S")),
    ])
    def get(self, request: Request):
        """API to get Basic Time Details"""

        try:
            serializer = GetTimeSegmentsSerializer(data=request.query_params)
            if not serializer.is_valid():
                return Response(status=400, data=serializer.errors)
            
            data = serializer.validated_data
            date: datetime.date = data.get("date")
            user = data.get("user")
            time_start= data.get("time_start")
            time_end = data.get("time_end")

            activity_logs = (
                ActivityLogs.objects
                .filter(
                    user=user,
                    start_timestamp__date=date
                )
                .order_by("start_timestamp")
            )

            start_time = activity_logs.first().start_timestamp
            last_seen = activity_logs.last().end_timestamp
            working_time = 0
            away_time = 0

            time_start_datetime = datetime.combine(
                date,
                datetime.strptime(time_start, "%H:%M:%S").time(),
                tzinfo=std_timezone.utc
            )
            if time_start_datetime < start_time:
                away_time += (start_time - time_start_datetime).total_seconds()

            time_end_datetime = datetime.combine(
                date,
                datetime.strptime(time_end, "%H:%M:%S").time(),
                tzinfo=std_timezone.utc
            )
            if time_end_datetime > last_seen:
                away_time += (time_end_datetime - last_seen).total_seconds()

            time_segments = TimeSegments.objects.filter(user=user, date=date)
            for index, time_segment in enumerate(time_segments):
                if time_segment.segment_type == "productive":
                    working_time += (time_segment.end_time - time_segment.start_time).total_seconds()
                
                if index == len(time_segments) - 1:
                    continue

                if (time_segment.end_time < time_segments[index+1].start_time): 
                    duration = time_segments[index+1].start_time - time_segment.end_time
                    if not duration <= timedelta(seconds=settings.TIME_GAP_LIMIT):
                        away_time += duration.total_seconds()

            response = {
                "start_time": start_time.strftime("%H:%M %p"),
                "working_time": self.format_time(working_time).strip(),
                "last_seen": last_seen.strftime("%H:%M %p"),
                "away_time": self.format_time(away_time).strip(),
            }
            return Response(status=200, data=response)

        except Exception as e:
            print(json.dumps(get_traceback(), indent=4))

            with open("errors.log", "a") as file:
                file.write("Time recorded: " + timezone.now().strftime("%Y-%m-%d %H:%M:%S %p" + "\n"))
                file.write(json.dumps(get_traceback(), indent=4))
                file.write("\n\n")

            return Response(status=500, data=get_traceback())


class TrackerWeeklySummary(APIView):
    @staticmethod
    def get_closest_start_date(date: datetime, week_start_index: int = 0) -> datetime:
        """Get the closest starting date. By default, the starting date is considered Monday.

        The week_start_index follows the same indexing that is followed by the [weekday
        method](https://docs.python.org/3/library/datetime.html#datetime.date.weekday) provided by the datetime module.
        Reference: https://stackoverflow.com/questions/6558535/find-the-date-for-the-first-monday-after-a-given-date/79092349#79092349
        """

        if date.weekday() == week_start_index:
            return date

        days_ahead = week_start_index - date.weekday()
        if days_ahead <= 0:
            days_ahead += 7

        days_behind = date.weekday() - week_start_index
        if days_behind <= 0:
            days_behind += 7

        closest_day = (
            days_ahead if days_ahead < days_behind
            else - days_behind
        )
        return date + timedelta(days=closest_day)

    @staticmethod
    def format_time(time: float) -> str:
        time_object = timedelta(seconds=time)
        mins, seconds = divmod(time, 60)
        hours, minutes = divmod(mins, 60)

        result = ""

        if time_object.days is not None and time_object.days != 0:
            result += f"{time_object.days} day{abs(time_object.days) != 1 and "s" or ""} "
        if hours is not None and hours != 0:
            result += f"{int(hours)}h "
        if minutes is not None and minutes != 0:
            result += f"{int(minutes)}m "
        if seconds is not None and seconds != 0:
            result += f"{int(seconds)}s "

        if result == "":
            result = "0s"
        
        return result

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="user", location=OpenApiParameter.QUERY,
                required=True, type=OpenApiTypes.STR
            ),
            OpenApiParameter(
                name="date", location=OpenApiParameter.QUERY,
                required=False, type=OpenApiTypes.DATE
            ),
            OpenApiParameter(
                name="week_start", location=OpenApiParameter.QUERY,
                required=False, type=OpenApiTypes.STR,
                description=f"Allowed Values: {list(GetWeeklyHoursSerializer().shortcut_names.keys())}",
            ),
            OpenApiParameter(
                name="time_start", location=OpenApiParameter.QUERY,
                required=True, type=OpenApiTypes.TIME,
            ),
            OpenApiParameter(
                name="time_end", location=OpenApiParameter.QUERY,
                required=True, type=OpenApiTypes.TIME,
            )
        ]
    )
    def get(self, request: Request):
        """API to fetch Weekly Summary.

        By default, the start date will be the closest monday to the requested date.
        If no date is requested, today's date is taken by default.
        """

        try:
            serializer = GetWeeklyHoursSerializer(data=request.query_params)
            if not serializer.is_valid():
                return Response(status=400, data=serializer.errors)

            data = serializer.validated_data
            user = data.get("user")

            date = timezone.now()
            date_: Optional[datetime.date] = data.get("date")
            if date_ is not None:
                date = date_

            time_start = data.get("time_start")
            time_end = data.get("time_end")

            # Following list relies on specific index placement
            # so that the datetime.weekday method can work properly
            weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
            week_start_index = weekdays.index(data.get("week_start", "monday"))
            closest_start_date = self.get_closest_start_date(date, week_start_index)
            last_date = closest_start_date + timedelta(days=7)

            response = {
                "working_time": {},
                "away_time": {}
            }
            working_date = closest_start_date
            while working_date != last_date:
                working_time = away_time = 0

                # time_start_datetime = datetime.combine(
                #     date,
                #     datetime.strptime(time_start, "%H:%M:%S").time(),
                #     tzinfo=std_timezone.utc
                # )
                # if time_start_datetime < start_time:
                #     away_time += (start_time - time_start_datetime).total_seconds()

                # time_end_datetime = datetime.combine(
                #     date,
                #     datetime.strptime(time_end, "%H:%M:%S").time(),
                #     tzinfo=std_timezone.utc
                # )
                # if time_end_datetime > last_seen:
                #     away_time += (time_end_datetime - last_seen).total_seconds()

                activity_logs = ActivityLogs.objects.filter(
                    start_timestamp__date=working_date.date(),
                    user=user,
                ).order_by("start_timestamp")

                if activity_logs.count() == 0:
                    response["working_time"][weekdays[working_date.weekday()]] = "0s"
                    response["away_time"][weekdays[working_date.weekday()]] = "0s"
                    working_date += timedelta(days=1)
                    continue

                start_time = activity_logs.first().start_timestamp
                last_seen = activity_logs.last().end_timestamp

                time_start_datetime = datetime.combine(
                    date,
                    datetime.strptime(time_start, "%H:%M:%S").time(),
                    tzinfo=std_timezone.utc
                )
                if time_start_datetime < start_time:
                    away_time += (start_time - time_start_datetime).total_seconds()

                time_end_datetime = datetime.combine(
                    date,
                    datetime.strptime(time_end, "%H:%M:%S").time(),
                    tzinfo=std_timezone.utc
                )
                if time_end_datetime > last_seen:
                    away_time += (time_end_datetime - last_seen).total_seconds()

                time_segments = TimeSegments.objects.filter(user=user, date=working_date)
                for index, time_segment in enumerate(time_segments):
                    if time_segment.segment_type == "productive":
                        working_time += (time_segment.end_time - time_segment.start_time).total_seconds()
                
                    if index == len(time_segments) - 1:
                        continue

                    if (time_segment.end_time < time_segments[index+1].start_time): 
                        duration = time_segments[index+1].start_time - time_segment.end_time
                        if not duration <= timedelta(seconds=settings.TIME_GAP_LIMIT):
                            away_time += duration.total_seconds()

                response["working_time"][weekdays[working_date.weekday()]] = self.format_time(working_time).strip()
                response["away_time"][weekdays[working_date.weekday()]] = self.format_time(away_time).strip()

                working_date += timedelta(days=1)

            return Response(status=200, data=response)
        except Exception as e:
            print(json.dumps(get_traceback(), indent=4))

            with open("errors.log", "a") as file:
                file.write("Time recorded: " + timezone.now().strftime("%Y-%m-%d %H:%M:%S %p" + "\n"))
                file.write(json.dumps(get_traceback(), indent=4))
                file.write("\n\n")

            return Response(status=500, data=get_traceback())


class TrackerSetAppCategory(APIView):
    def post(self, request: Request):
        """API to set App Category"""