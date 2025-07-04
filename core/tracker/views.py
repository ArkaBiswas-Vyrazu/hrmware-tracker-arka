"""HRMWARE Tracker API Definitions

Last Revision Date: June 30 2025 14:48 PM
"""

from typing import Any, Optional, Literal
import warnings
import json
from zoneinfo import ZoneInfo
from datetime import (
    datetime,
    timedelta,
    date as std_date,
    time as std_time,
    timezone as std_timezone
)

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import FieldError
from django.utils import timezone
from django.db.models import Sum, F
from django.db.models.query import QuerySet
from rest_framework.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from core.helpers import get_traceback, uniqid
from .typing import TimeTracker, TimeBarDataItem, Weekday
from .exceptions import NoActivityLogFound
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
    GetWeeklyHoursSerializer,
    TrackerAppCategoriesSerializer,
    TrackerAppCategoryPatchSerializer,
    TrackerSetAppCategorySerializer,
    TrackerAppsSerializer,
    TrackerAppCategoryPostSerializer,
    TrackerProductiveBreakDownSerializer,
    TrackerCategoryBreakDownSerializer,
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
                self.extract_data(data) | {"activity_log": main_data.get("activity_logs", {}).get(data.get("id"))}
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

            print(json.dumps(main_data, indent=4))
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
            print("----------------------------------------- Afterwards ------------------------------------------ ")
            print(main_data)

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
        provides more granularity. However, this can be process intensive as proper
        division of the time bar takes time.
        """

        msg = "This work is under progress. Please use the fine_grained flag and set it to false"
        raise NotImplementedError(msg)

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

            fine_grained: bool = data.get("fine_grained", False)
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
    def get_closest_start_date(date: datetime | std_date, week_start_index: int = 0) -> datetime | std_date:
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
                description=f"Allowed Values: {", ".join(tuple(GetWeeklyHoursSerializer.SHORTCUT_NAMES.keys()))}",
            ),
            OpenApiParameter(
                name="time_start", location=OpenApiParameter.QUERY,
                required=True, type=OpenApiTypes.TIME,
            ),
            OpenApiParameter(
                name="time_end", location=OpenApiParameter.QUERY,
                required=True, type=OpenApiTypes.TIME,
            ),
            OpenApiParameter(
                name="progression", location=OpenApiParameter.QUERY,
                required=False, type=OpenApiTypes.STR,
                description=f"Allowed Values: {", ".join(tuple(GetWeeklyHoursSerializer.PROGRESSION_VALUES))}",
                default="forward",
            ),
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
            if isinstance(closest_start_date, std_date):
                closest_start_date = datetime.combine(closest_start_date, datetime.min.time())

            progression: Literal["forward"] | Literal["backward"] = data.get("progression")
            last_date = (
                closest_start_date + timedelta(days=7)
                if progression == "forward"
                else closest_start_date - timedelta(days=7)
            )

            response = {
                "working_time": {},
                "away_time": {}
            }
            working_date = closest_start_date
            while working_date != last_date:
                print("Working Date: ", working_date)
                print("Last Date: ", last_date)

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
                    
                    if progression == "forward":
                        working_date += timedelta(days=1)
                    else:
                        working_date -= timedelta(days=1)
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

                if progression == "forward":
                    working_date += timedelta(days=1)
                else:
                    working_date -= timedelta(days=1)

            return Response(status=200, data=response)
        except Exception as e:
            print(json.dumps(get_traceback(), indent=4))

            with open("errors.log", "a") as file:
                file.write("Time recorded: " + timezone.now().strftime("%Y-%m-%d %H:%M:%S %p" + "\n"))
                file.write(json.dumps(get_traceback(), indent=4))
                file.write("\n\n")

            return Response(status=500, data=get_traceback())


class TrackerAppCategoryView(APIView):
    def get(self, request: Request):
        """Get a list of all app categories defined."""

        try:
            tracker_categories = TrackerAppCategories.objects.all()
            response = {
                "app_categories": TrackerAppCategoriesSerializer(tracker_categories, many=True).data
            }
            return Response(status=200, data=response)
        except Exception as e:
            print(json.dumps(get_traceback(), indent=4))

            with open("errors.log", "a") as file:
                file.write("Time recorded: " + timezone.now().strftime("%Y-%m-%d %H:%M:%S %p") + "\n")
                file.write(json.dumps(get_traceback()))
                file.write("\n\n")

            return Response(status=500, data=get_traceback())

    @extend_schema(request=TrackerAppCategoryPatchSerializer)
    def patch(self, request: Request):
        """Update Category details.
        
        Note that updating category details would also update subsequent
        records in activity_logs and time_segments.
        """

        try:
            serializer = TrackerAppCategoryPatchSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(status=400, data=serializer.errors)

            data = serializer.validated_data
            app_category: TrackerAppCategories = serializer.validated_data["app_category"]

            if app_category.name != data.get("name"):
                app_category.name = data.get("name") or app_category.name
            if app_category.productivity_status_type != data.get("productivity_status_type"):
                app_category.productivity_status_type = data.get("productivity_status_type") or app_category.productivity_status_type

            app_category.save()
            return Response(status=200, data={"app_category": TrackerAppCategoriesSerializer(app_category).data})
        except Exception as e:
            print(json.dumps(get_traceback(), indent=4))

            with open("errors.log", "a") as file:
                file.write("Time recorded: " + timezone.now().strftime("%Y-%m-%d %H:%M:%S %p") + "\n")
                file.write(json.dumps(get_traceback()))
                file.write("\n\n")
            
            return Response(status=500, data=get_traceback())

    @extend_schema(request=TrackerAppCategoryPostSerializer)
    def post(self, request: Request):
        """Create a new category"""

        try:
            serializer = TrackerAppCategoryPostSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(status=400, data=serializer.errors)
    
            tracker_app_category = TrackerAppCategories.objects.create(
                name=serializer.validated_data.get("name"),
                productivity_status_type=serializer.validated_data.get("productivity_status_type"),
            )
            return Response(status=200, data=TrackerAppCategoriesSerializer(tracker_app_category).data)
        except Exception as e:
            print(json.dumps(get_traceback(), indent=4))

            with open("errors.log", "a") as file:
                file.write("Time recorded: " + timezone.now().strftime("%Y-%m-%d %H:%M:%S %p") + "\n")
                file.write(json.dumps(get_traceback()))
                file.write("\n\n")
            
            return Response(status=500, data=get_traceback())


class TrackerAppsView(APIView):
    def get(self, request: Request):
        """List all apps found through the tracker."""

        try:
            apps = TrackerApps.objects.all()
            return Response(status=200, data=TrackerAppsSerializer(apps, many=True).data)
        except Exception as e:
            print(json.dumps(get_traceback(), indent=4))

            with open("errors.log", "a") as file:
                file.write("Time recorded: " + timezone.now().strftime("%Y-%m-%d %H:%M:%S %p") + "\n")
                file.write(json.dumps(get_traceback()))
                file.write("\n\n")
            
            return Response(status=500, data=get_traceback())


class TrackerSetAppCategoryView(APIView):
    serializer_class = TrackerSetAppCategorySerializer

    def patch(self, request: Request):
        """Update the category of an app.
        
        Note that on a successful update,
        related activity logs and time segments will be updated
        """

        try:
            serializer = TrackerSetAppCategorySerializer(data=request.data)
            if not serializer.is_valid():
                return Response(status=400, data=serializer.errors)

            app, category = serializer.validated_data.values()
            app.category = category
            app.update()

            return Response(status=200, data={"app": TrackerAppsSerializer(app).data})
        except Exception as e:
            print(json.dumps(get_traceback(), indent=4))

            with open("errors.log", "a") as file:
                file.write("Time recorded: " + timezone.now().strftime("%Y-%m-%d %H:%M:%S %p") + "\n")
                file.write(json.dumps(get_traceback()))
                file.write("\n\n")
            
            return Response(status=500, data=get_traceback())


class TrackerProductiveBreakDownView(APIView):
    @staticmethod
    def format_time(seconds: int | float | None) -> str | None:
        if seconds is None:
            return None

        time_object = timedelta(seconds=seconds)
        mins, seconds = divmod(seconds, 60)
        hours, minutes = divmod(mins, 60)

        result = ""

        if time_object.days is not None and time_object.days != 0:
            result += f"{time_object.days} day{abs(time_object.days) != 1 and "s" or ""} "
        if hours is not None and hours != 0:
            result += f"{int(hours)}h "
        if minutes is not None and minutes != 0:
            result += f"{int(minutes)}m "
        if seconds is not None and seconds != 0:
            result += f"{int(seconds)}s"

        if result == "":
            result = "0s"

        return result.strip()

    @staticmethod
    def get_closest_start_date(date: datetime | std_date, week_start_index: int = 0) -> datetime | std_date:
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
    def get_default_start_time(user, date: datetime | std_date) -> std_time:
        """Get the default start time for the provided date in case no start time is provided
        
        Here, we assume that the start_timestamp of the first activity log entry for the
        requested user on the request date as the default start time.
        """

        activity_logs = ActivityLogs.objects.filter(user=user)
            
        if isinstance(date, datetime):
            activity_logs = activity_logs.filter(start_timestamp__date=date.date())
        else:
            activity_logs = activity_logs.filter(start_timestamp__date=date)

        first_entry = activity_logs.order_by("start_timestamp").first()
        if first_entry is None:
            raise NoActivityLogFound(f"No entry found for user on date {date.strftime("%Y-%m-%d")}")

        start_time = first_entry.start_timestamp.time()
        return start_time

    @staticmethod
    def get_default_end_time(user, date: datetime | std_date) -> std_time:
        """Get the default end time for the provided date in case no end time is provided

        Here, we assume that the end_timestamp of the last activity log entry for the
        requested user on the request date as the default end time.
        """

        activity_logs = ActivityLogs.objects.filter(user=user)

        if isinstance(date, datetime):
            activity_logs = activity_logs.filter(start_timestamp__date=date.date())
        else:
            activity_logs = activity_logs.filter(start_timestamp__date=date)

        last_entry = activity_logs.order_by("start_timestamp").last()
        if last_entry is None:
            raise NoActivityLogFound(f"No entry found for user on date {date.strftime("%Y-%m-%d")}")

        end_time = last_entry.end_timestamp.time()
        return end_time

    @staticmethod
    def get_total_working_time(date: std_date, start_time: std_time, end_time: std_time) -> int:
        return (
            (datetime.combine(date, end_time, tzinfo=ZoneInfo("UTC"))
            - datetime.combine(date, start_time, tzinfo=ZoneInfo("UTC")))
            .total_seconds()
        )

    def calculate_working_time_with_percentage(self,
                               user,
                               date: datetime | std_date,
                               start_time: Optional[std_time] = None,
                               end_time: Optional[std_time] = None) -> dict[str, float]:
        try:
            if start_time is None:
                start_time = self.get_default_start_time(user, date)
            if end_time is None:
                end_time = self.get_default_end_time(user, date)

            # By definition, the first and last activity log entries for the requested user
            # for the requested date serve as proof of working. So, we can use that for calculation.
            # Otherwise, if this is to be integrated with the Hrmware application, we could
            # use the attendance data for more accuracy
            work_start_time = datetime.combine(date, self.get_default_start_time(user, date), tzinfo=ZoneInfo("UTC"))
            work_end_time = datetime.combine(date, self.get_default_end_time(user, date), tzinfo=ZoneInfo("UTC"))

            total_working_time = (work_end_time - work_start_time).total_seconds()

            total_defined_work_duration = self.get_total_working_time(date, start_time, end_time)
            working_time_percentage = round((total_working_time / total_defined_work_duration) * 100, 2)

            return {"working_time": total_working_time, "working_time_percentage": working_time_percentage}

        except NoActivityLogFound:
            return {"working_time": None, "working_time_percentage": None}

    def calculate_productive_time_with_percentage(self,
                                  user,
                                  date: datetime | std_date,
                                  start_time: Optional[std_time] = None,
                                  end_time: Optional[std_time] = None) -> dict[str, float]:
        try:
            if start_time is None:
                start_time = self.get_default_start_time(user, date)
            if end_time is None:
                end_time = self.get_default_end_time(user, date)
        except NoActivityLogFound:
            return {"productive_time": None, "productive_time_percentage": None}

        total_productive_time = 0
        activity_logs = ActivityLogs.objects.filter(user=user, start_timestamp__date=date)        
        for activity_log in activity_logs:
            if activity_log.productivity_status == "productive":
                total_productive_time += (activity_log.get_actual_end_time() - activity_log.start_timestamp).total_seconds()

        total_defined_work_duration = self.get_total_working_time(date=date, start_time=start_time, end_time=end_time)
        productive_time_percentage = round((total_productive_time / total_defined_work_duration) * 100, 2)

        return {"productive_time": total_productive_time, "productive_time_percentage": productive_time_percentage}

    def calculate_non_productive_time_with_percentage(self,
                                                      user,
                                                      date: datetime | std_date,
                                                      start_time: Optional[std_time] = None,
                                                      end_time: Optional[std_time] = None) -> dict[str, float]:
        try:
            if start_time is None:
                start_time = self.get_default_start_time(user, date)
            if end_time is None:
                end_time = self.get_default_end_time(user, date)
        except NoActivityLogFound:
            return {"non_productive_time": None, "non_productive_time_percentage": None}

        total_non_productive_time = 0
        activity_logs = ActivityLogs.objects.filter(user=user, start_timestamp__date=date)
        for activity_log in activity_logs:
            if activity_log.productivity_status not in ["productive", "neutral"]:
                total_non_productive_time += (activity_log.get_actual_end_time() - activity_log.start_timestamp).total_seconds()
        
        total_defined_work_duration = self.get_total_working_time(date=date, start_time=start_time, end_time=end_time)
        non_productive_time_percentage = round((total_non_productive_time / total_defined_work_duration) * 100, 2)

        return {"non_productive_time": total_non_productive_time, "non_productive_time_percentage": non_productive_time_percentage}

    def calculate_neutral_time_with_percentage(self,
                                               user,
                                               date: datetime | std_date,
                                               start_time: Optional[std_time] = None,
                                               end_time: Optional[std_time] = None) -> dict[str, float]:
        try:
            if start_time is None:
                start_time = self.get_default_start_time(user, date)
            if end_time is None:
                end_time = self.get_default_end_time(user, date)
        except NoActivityLogFound:
            return {"neutral_time": None, "neutral_time_percentage": None}

        total_neutral_time = 0
        activity_logs = ActivityLogs.objects.filter(user=user, start_timestamp__date=date)
        for activity_log in activity_logs:
            if activity_log.productivity_status == "neutral":
                total_neutral_time += (activity_log.get_actual_end_time() - activity_log.start_timestamp).total_seconds()

        total_defined_work_duration = self.get_total_working_time(date=date, start_time=start_time, end_time=end_time)
        neutral_time_percentage = round((total_neutral_time / total_defined_work_duration) * 100, 2)

        return {"neutral_time": total_neutral_time, "neutral_time_percentage": neutral_time_percentage}

    def calculate_away_time_with_percentage(self,
                                            user,
                                            date: datetime | std_date,
                                            start_time: Optional[std_time] = None,
                                            end_time: Optional[std_time] = None) -> dict[str, float]:
        try:
            if start_time is None:
                start_time = self.get_default_start_time(user, date)
            if end_time is None:
                end_time = self.get_default_end_time(user, date)
        except NoActivityLogFound:
            return {
                "away_time": self.get_total_working_time(date, start_time, end_time),
                "away_time_percentage": 100 # Because then we consider that the user was away the entire day
            }

        total_away_time = 0
        activity_logs = ActivityLogs.objects.filter(user=user, start_timestamp__date=date)
        for index, activity_log in enumerate(activity_logs):
            if index == 0:
                start_timestamp = start_time
                end_timestamp = activity_log.start_timestamp

            elif index == len(activity_logs) - 1:
                start_timestamp = activity_log.get_actual_end_time()
                end_timestamp = end_time
            
            else:
                start_timestamp = activity_log.get_actual_end_time()
                end_timestamp = activity_logs[index+1].start_timestamp

            if isinstance(start_timestamp, std_time):
                start_timestamp = datetime.combine(date, start_timestamp, tzinfo=ZoneInfo("UTC"))
            if isinstance(end_timestamp, std_time):
                end_timestamp = datetime.combine(date, end_timestamp, tzinfo=ZoneInfo("UTC"))

            if start_timestamp < end_timestamp:
                duration = end_timestamp - start_timestamp
                if duration >= timedelta(seconds=settings.TIME_GAP_LIMIT):
                    total_away_time += duration.total_seconds()

        if total_away_time == 0:
            total_away_time = self.get_total_working_time(date, start_time, end_time)

        total_defined_work_duration = self.get_total_working_time(date=date, start_time=start_time, end_time=end_time)
        away_time_percentage = round((total_away_time / total_defined_work_duration) * 100, 2)

        return {"away_time": total_away_time, "away_time_percentage": away_time_percentage}

    def get_days_to_work_on(self,
                            date: datetime | std_date,
                            week_start: Weekday = "monday",
                            number_of_days_in_work_week = 5,
                            work_days_to_ignore: list[Weekday] = []) -> list[datetime | std_date]:
        """Get a list of dates to get result from"""

        # Weekdays arranged according to the
        # weekday method provided by the datetime module
        weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        closest_date = self.get_closest_start_date(date, weekdays.index(week_start))
        work_days_to_ignore_formatted = [
            weekdays.index(weekday)
            for weekday in work_days_to_ignore
        ]

        days_list: list[datetime | std_date] = []
        working_date = closest_date
        final_date_to_avoid = working_date + timedelta(days=number_of_days_in_work_week)

        while working_date != final_date_to_avoid:
            if working_date.weekday() not in work_days_to_ignore_formatted:
                days_list.append(working_date)
            
            working_date += timedelta(days=1)

        return days_list

    def get_week_calculations(self,
                              response_key: (Literal["working"] |
                                             Literal["productive"] |
                                             Literal["non_productive"] |
                                             Literal["neutral"] |
                                             Literal["away"]),
                              user,
                              valid_week_days: list[datetime | std_date],
                              start_time: std_time,
                              end_time: std_time) -> dict[str, float]:
        this_week_calculations = 0
        total_working_time = 0
        for week_day in valid_week_days:
            function_to_call = getattr(self, f"calculate_{response_key}_time_with_percentage")
            function_result = function_to_call(user, week_day, start_time, end_time)

            print(f"Total {response_key} time on {week_day.strftime("%Y-%m-%d")}: ", function_result)
            if function_result[f"{response_key}_time"] is not None:
                this_week_calculations += function_result[f"{response_key}_time"]

            total_working_time += self.get_total_working_time(week_day, start_time, end_time)

        this_week_calculations_percentage = round((this_week_calculations / total_working_time) * 100, 2)

        return {f"{response_key}_time": this_week_calculations, f"{response_key}_time_percentage": this_week_calculations_percentage}

    def get_response(self,
                     user,
                     date: datetime | std_date,
                     start_time: Optional[std_time],
                     end_time: Optional[std_time],
                     week_start: Weekday,
                     number_of_days_in_work_week: int,
                     work_days_to_ignore: list[Weekday],
                     output_format: Literal["activity"] | Literal["day"]):
        """Get response in either activity or day key format"""

        response = {}
        response_keys = (
            "working", "productive",
            "non_productive", "neutral", "away"
        )
        valid_week_days = self.get_days_to_work_on(
            date,
            week_start,
            number_of_days_in_work_week,
            work_days_to_ignore
        )

        if output_format == "activity":
            for response_key in response_keys:
                this_day_calculations = getattr(self, f"calculate_{response_key}_time_with_percentage")(user, date, start_time, end_time)
                yesterday_calculations = getattr(self, f"calculate_{response_key}_time_with_percentage")(user, date - timedelta(days=1), start_time, end_time)
                this_week_calculations = self.get_week_calculations(response_key, user, valid_week_days, start_time, end_time)

                response[f"{response_key}_time"] = {
                    "this_day": self.format_time(this_day_calculations[f"{response_key}_time"]),
                    "this_day_percentage": f"{this_day_calculations[f"{response_key}_time_percentage"]}%",
                    "yesterday": self.format_time(yesterday_calculations[f"{response_key}_time"]),
                    "yesterday_percentage": f"{yesterday_calculations[f"{response_key}_time_percentage"]}%",
                    "this_week": self.format_time(this_week_calculations[f"{response_key}_time"]),
                    "this_week_percentage": f"{this_week_calculations[f"{response_key}_time_percentage"]}%"
                }

        elif output_format == "day":
            calculations_to_make = {
                "this_day": date,
                "yesterday": date - timedelta(days=1),
                "this_week": valid_week_days
            }

            for key, value in calculations_to_make.items():
                for response_key in response_keys:
                    if key == "this_week":
                        result = self.get_week_calculations(
                            response_key,
                            user,
                            valid_week_days,
                            start_time,
                            end_time
                        )
                    else:
                        function = getattr(self, f"calculate_{response_key}_time_with_percentage")
                        result = function(user, value, start_time, end_time)

                    if key not in response:
                        response[key] = {}

                    response[key][f"{response_key}_time"] = self.format_time(result[f"{response_key}_time"])
                    response[key][f"{response_key}_time_percentage"] = f"{result[f"{response_key}_time_percentage"]}%"
        else:
            raise ValueError("Invalid Output Format provided")

        return response

    @extend_schema(parameters=[
        OpenApiParameter(
           name="date", location=OpenApiParameter.QUERY,
           required=False, type=OpenApiTypes.STR,
           default=datetime.now().date().strftime("%Y-%m-%d"),
        ),
        OpenApiParameter(
            name="user", location=OpenApiParameter.QUERY,
            required=True, type=OpenApiTypes.STR,
        ),
        OpenApiParameter(
            name="start_time", location=OpenApiParameter.QUERY,
            required=False, type=OpenApiTypes.TIME,
            default=datetime.now().time().strftime("%H:%M:%S"),
        ),
        OpenApiParameter(
            name="end_time", location=OpenApiParameter.QUERY,
            required=False, type=OpenApiTypes.TIME,
            default=(datetime.now() + timedelta(hours=1)).time().strftime("%H:%M:%S"),
        ),
        OpenApiParameter(
            name="output_format", location=OpenApiParameter.QUERY,
            required=False, type=OpenApiTypes.STR,
            description=f"Allowed Values: {", ".join(TrackerProductiveBreakDownSerializer.OUTPUT_FORMAT_CHOICES)}",
            default="activity",
        ),
        OpenApiParameter(
            name="week_start", location=OpenApiParameter.QUERY,
            required=False, type=OpenApiTypes.STR,
            description=f"Allowed Values: {", ".join(TrackerProductiveBreakDownSerializer.SHORTCUT_NAMES)
                                            + ", "
                                            + ", ".join(TrackerProductiveBreakDownSerializer.VALID_WEEK_NAMES)}",
            default="monday"
        ),
        OpenApiParameter(
            name="number_of_days_in_work_week", location=OpenApiParameter.QUERY,
            required=False, type=OpenApiTypes.INT,
            default=5,
            description="Must be between 1-7. Note that if work_days_to_ignore parameter is provided," \
                        "those days will not be considered in the total calculation"
        ),
        OpenApiParameter(
            name="work_days_to_ignore", location=OpenApiParameter.QUERY,
            required=False, type=OpenApiTypes.STR,
            default="saturday,sunday",
            description="Work days that will be ignored. Must be provided as comma seperated values. " \
                        "Accepts the same values as week_start."
        )
    ])
    def get(self, request: Request):
        """Fetch productive time break down for the provided date, the day before the provided date
        and the week for the provided date.

        It will return the total duration and percentage of working time, productive time,
        non-productive time, neutral time and away time for the provided date, the 
        day before the provided date and the week for the provided date.

        Please note that start_time and end_time provided is assumed to be in the Asia/Kolkata
        timezone. As such, this will be converted into UTC time for proper analysis.

        Response can be both Activity Key Based and Day Key Based, so any format can be
        chosen. By default, response will be provided on the basis of activity keys.
        """

        try:
            serializer = TrackerProductiveBreakDownSerializer(data=request.query_params)
            if not serializer.is_valid():
                return Response(status=400, data=serializer.errors)

            user = serializer.validated_data.get("user")
            date = serializer.validated_data.get("date")
            start_time = serializer.validated_data.get("start_time")
            end_time = serializer.validated_data.get("end_time")
            output_format = serializer.validated_data.get("output_format")
            week_start = serializer.validated_data.get("week_start")
            number_of_days_in_work_week = serializer.validated_data.get("number_of_days_in_work_week")
            work_days_to_ignore = serializer.validated_data.get("work_days_to_ignore")

            response = self.get_response(
                user=user,
                date=date,
                start_time=start_time,
                end_time=end_time,
                week_start=week_start,
                number_of_days_in_work_week=number_of_days_in_work_week,
                work_days_to_ignore=work_days_to_ignore,
                output_format=output_format
            )

            return Response(status=200, data=response)

        except Exception as e:
            print(json.dumps(get_traceback(), indent=4))

            with open("errors.log", "a") as file:
                file.write("Time recorded: " + timezone.now().strftime("%Y-%m-%d %H:%M:%S %p") + "\n")
                file.write(json.dumps(get_traceback()))
                file.write("\n\n")

            return Response(status=500, data=get_traceback())


class TrackerCategoryBreakDownView(APIView):
    @staticmethod
    def format_time(seconds: int | float | None) -> str | None:
        if seconds is None:
            return None

        time_object = timedelta(seconds=seconds)
        mins, seconds = divmod(seconds, 60)
        hours, minutes = divmod(mins, 60)

        result = ""

        if time_object.days is not None and time_object.days != 0:
            result += f"{time_object.days} day{abs(time_object.days) != 1 and "s" or ""} "
        if hours is not None and hours != 0:
            result += f"{int(hours)}h "
        if minutes is not None and minutes != 0:
            result += f"{int(minutes)}m "
        if seconds is not None and seconds != 0:
            result += f"{int(seconds)}s"

        if result == "":
            result = "0s"

        return result.strip()

    @staticmethod
    def get_default_start_time(user, date: datetime | std_date) -> std_time:
        """Get the default start time for the provided date in case no start time is provided
        
        Here, we assume that the start_timestamp of the first activity log entry for the
        requested user on the request date as the default start time.
        """

        activity_logs = ActivityLogs.objects.filter(user=user)
            
        if isinstance(date, datetime):
            activity_logs = activity_logs.filter(start_timestamp__date=date.date())
        else:
            activity_logs = activity_logs.filter(start_timestamp__date=date)

        first_entry = activity_logs.order_by("start_timestamp").first()
        if first_entry is None:
            raise NoActivityLogFound(f"No entry found for user on date {date.strftime("%Y-%m-%d")}")

        start_time = first_entry.start_timestamp.time()
        return start_time

    @staticmethod
    def get_default_end_time(user, date: datetime | std_date) -> std_time:
        """Get the default end time for the provided date in case no end time is provided

        Here, we assume that the end_timestamp of the last activity log entry for the
        requested user on the request date as the default end time.
        """

        activity_logs = ActivityLogs.objects.filter(user=user)

        if isinstance(date, datetime):
            activity_logs = activity_logs.filter(start_timestamp__date=date.date())
        else:
            activity_logs = activity_logs.filter(start_timestamp__date=date)

        last_entry = activity_logs.order_by("start_timestamp").last()
        if last_entry is None:
            raise NoActivityLogFound(f"No entry found for user on date {date.strftime("%Y-%m-%d")}")

        end_time = last_entry.end_timestamp.time()
        return end_time

    @extend_schema(parameters=[
            OpenApiParameter(
                name="date", location=OpenApiParameter.QUERY,
                required=True, type=OpenApiTypes.DATE,
                default=datetime.now().date()
            ),
            OpenApiParameter(
                name="user", location=OpenApiParameter.QUERY,
                required=True, type=OpenApiTypes.STR,
            ),
            OpenApiParameter(
                name="start_time", location=OpenApiParameter.QUERY,
                required=False, type=OpenApiTypes.TIME,
                default=datetime.now().time().strftime("%H:%M:%S")
            ),
            OpenApiParameter(
                name="end_time", location=OpenApiParameter.QUERY,
                required=False, type=OpenApiTypes.TIME,
                default=(datetime.now() + timedelta(hours=1)).time().strftime("%H:%M:%S")
            )
        ]
    )
    def get(self, request: Request):
        try:
            serializer = TrackerCategoryBreakDownSerializer(data=request.query_params)
            if not serializer.is_valid():
                return Response(status=400, data=serializer.errors)

            data = serializer.validated_data
            date = data["date"]
            user = data["user"]
            start_time = data.get("start_time")
            end_time = data.get("end_time")

            try:
                if start_time is None:
                    start_time = self.get_default_start_time(user, date)
                if end_time is None:
                    end_time = self.get_default_end_time(user, date)
            except NoActivityLogFound:
                return Response(status=400, data={"msg": "Please provide a start and end time"})

            total_work_duration = (
                (datetime.combine(date, end_time, tzinfo=ZoneInfo("UTC"))
                - datetime.combine(date, start_time, tzinfo=ZoneInfo("UTC")))
                .total_seconds()
            )
            category_counts = (
                ActivityLogs.objects
                .filter(
                    start_timestamp__date=date,
                    user=user,
                )
                .annotate(name=F("category__name"))
                .values("name")
                .annotate(total_duration=Sum("duration"))
                .annotate(total_percentage=Sum("duration") / total_work_duration)
                .order_by()
            )
            categories_not_recorded = (
                TrackerAppCategories.objects
                .exclude(name__in=category_counts.values("name"))
            )

            response = {}
            for category_count in category_counts.values("name", "total_duration", "total_percentage"):
                name, total_duration, total_percentage = (
                    category_count.get("name"),
                    category_count.get("total_duration"),
                    category_count.get("total_percentage")
                )

                response[name] = {
                    "duration": self.format_time(float(total_duration)),
                    "percentage": f"{round(total_percentage, 2)}%"
                }
            for category in categories_not_recorded:
                response[category.name] = {"duration": None, "percentage": None}

            return Response(status=200, data={"category_breakdown": response})

        except Exception as e:
            print(json.dumps(get_traceback(), indent=4))

            with open("errors.log", "a") as file:
                file.write("Time recorded: " + timezone.now().strftime("%Y-%m-%d %H:%M:%S %p") + "\n")
                file.write(json.dumps(get_traceback()))
                file.write("\n\n")

            return Response(status=500, data=get_traceback())
