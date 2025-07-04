"""HRMWARE Tracker API Serializers"""

from datetime import datetime, time as std_time, timezone as std_timezone
import json
from zoneinfo import ZoneInfo

from django.conf import settings
from rest_framework import serializers
from rest_framework.settings import api_settings
from .models import (
    ActivityLogs,
    TimeSegments,
    Users,
    TrackerAppCategories,
    TrackerApps
)


class ActivityLogsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityLogs
        fields = "__all__"


class ActivityLogsDataIdleStatesSerializer(serializers.Serializer):
    duration = serializers.IntegerField()
    startTime = serializers.CharField()
    endTime = serializers.CharField(allow_blank=True)


class ActivityLogsDataItemsSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    firstUsed = serializers.CharField()
    lastUsed = serializers.CharField(allow_blank=True, required=True)
    name = serializers.CharField()
    title = serializers.CharField()
    session = ActivityLogsDataIdleStatesSerializer(many=True)
    totalUsage = serializers.IntegerField()
    isActive = serializers.BooleanField()

    def validate(self, attrs):
        with open("attrs.json", "a") as file:
            file.write("\nBefore\n")
            file.write(json.dumps(attrs, indent=4))
            file.write("\n")
        
        if attrs["lastUsed"] == "" and attrs["isActive"] != True:
            raise serializers.ValidationError("lastUsed cannot be blank when isActive is False")

        if attrs["lastUsed"] == "":
            attrs["lastUsed"] = datetime.now().strftime("%I:%M:%S %p")

        with open("attrs.json", "a") as file:
            file.write("\nAfter\n")
            file.write(json.dumps(attrs, indent=4))
            file.write("\n")

        return super().validate(attrs)


class ActivityLogsDataSerializer(serializers.Serializer):
    allWindows = ActivityLogsDataItemsSerializer(many=True)
    idleStates = ActivityLogsDataIdleStatesSerializer(many=True)


class TimeSegmentsSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimeSegments
        fields = "__all__"


class GetTimeSegmentsSerializer(serializers.Serializer):
    date = serializers.DateField()
    user = serializers.CharField()
    time_start = serializers.CharField(required=False)
    time_end = serializers.CharField(required=False)
    fine_grained = serializers.BooleanField(required=False)

    def validate(self, attrs):
        super().validate(attrs)

        time_start = attrs.get("time_start")
        time_end = attrs.get("time_end")
        if ((time_start is not None and time_end is None)
            or (time_start is None and time_end is not None)):
            msg = "Please provide both time_start and time_end arguments if required"
            raise serializers.ValidationError(msg)

        if (time_start is not None
            and time_end is not None
            and datetime.strptime(time_start, "%H:%M:%S") > datetime.strptime(time_end, "%H:%M:%S")):
            msg = "Please provide valid time_start and time_end arguments"
            raise serializers.ValidationError(msg)

        user = Users.objects.filter(employee_id=attrs.get("user")).first()
        if user is None:
            msg = "User does not exist"
            raise serializers.ValidationError(msg)

        attrs["user"] = user
        return attrs


class GetWeeklyHoursSerializer(serializers.Serializer):
    user = serializers.CharField()
    date = serializers.DateField(required=False)
    week_start = serializers.CharField(required=False)
    time_start = serializers.CharField()
    time_end = serializers.CharField()


    PROGRESSION_VALUES = ("forward", "backward", "f", "b")
    progression = serializers.ChoiceField(
        choices=PROGRESSION_VALUES,
        required=False,
        default="forward",
    )

    # Reference: https://www.yourdictionary.com/articles/abbreviations-days-months
    SHORTCUT_NAMES = {
        "mon": "monday", "m": "monday",
        "tue": "tuesday", "tues": "tuesday", "tu": "tuesday", "t": "tuesday",
        "wed": "wednesday", "w": "wednesday",
        "thu": "thursday", "thur": "thursday", "thurs": "thursday", "th": "thursday", "r": "thursday",
        "fri": "friday", "f": "friday",
        "sat": "saturday", "s": "saturday",
        "sun": "sunday", "su": "sunday", "u": "sunday"
    }

    def validate_week_start(self, week_start):
        week_start = week_start.strip().lower()
        valid_week_names = (
            "monday", "tuesday", "wednesday",
            "thursday", "friday", "saturday",
            "sunday"
        )

        if week_start in self.SHORTCUT_NAMES:
            week_start = self.SHORTCUT_NAMES[week_start]
            return week_start
        
        if week_start not in valid_week_names:
            msg = "Please provide a valid week name"
            raise serializers.ValidationError(msg)

        return week_start

    def validate_progression(self, progression):
        if progression in ("f", "b"):
            progression = "forward" if progression == "f" else "backward"

        return progression

    def validate(self, attrs):
        super().validate(attrs)

        if datetime.strptime(attrs["time_start"], "%H:%M:%S") > datetime.strptime(attrs["time_end"], "%H:%M:%S"):
            msg = "Please provide valid time_start and time_end arguments"
            raise serializers.ValidationError(msg)

        user = Users.objects.filter(employee_id=attrs.get("user")).first()
        if user is None:
            msg = "User does not exist"
            raise serializers.ValidationError(msg)

        attrs["user"] = user
        return attrs


class TrackerAppCategoriesSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrackerAppCategories
        fields = ["uuid", "name", "productivity_status_type"]


class TrackerAppCategoryPatchSerializer(serializers.Serializer):
    uuid = serializers.CharField()
    name = serializers.CharField(required=False)
    productivity_status_type = serializers.ChoiceField(
        choices=tuple(TrackerAppCategories.PRODUCTIVITY_STATUS_CHOICES.keys()),
        required=False
    )

    def validate(self, attrs):
        if attrs.get("name") is None and attrs.get("productivity_status_type") is None:
            raise serializers.ValidationError("Please provide either name or productivity_status_type")

        app_category = TrackerAppCategories.objects.filter(uuid=attrs["uuid"]).first()
        if app_category is None:
            raise serializers.ValidationError("Invalid category uuid provided")

        if (attrs.get("name") is not None
            and app_category.name != attrs.get("name")
            and TrackerAppCategories.objects.filter(name=attrs["name"]).exists()):
            raise serializers.ValidationError("This app category already exists")

        attrs["app_category"] = app_category
        return attrs


class TrackerAppCategoryPostSerializer(serializers.Serializer):
    name = serializers.CharField()
    productivity_status_type = serializers.ChoiceField(
        choices=tuple(TrackerAppCategories.PRODUCTIVITY_STATUS_CHOICES.keys()),
        required=False,
        default="neutral",
    )

    def validate(self, attrs):
        if TrackerAppCategories.objects.filter(name=attrs["name"]).exists():
            raise serializers.ValidationError("This category already exists")

        return attrs


class TrackerSetAppCategorySerializer(serializers.Serializer):
    app = serializers.CharField()
    category = serializers.CharField()

    def validate_app(self, app):
        app_object = TrackerApps.objects.filter(uuid=app).first()
        if app_object is None:
            raise serializers.ValidationError("Please provide a valid app uuid")

        return app_object

    def validate_category(self, category):
        category_object = (
            TrackerAppCategories.objects
            .filter(uuid=category)
            .first()
        )
        if category_object is None:
            raise serializers.ValidationError("Please provide a valid category uuid.")

        return category_object


class TrackerAppsSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrackerApps
        fields = ["uuid", "name", "category_id"]


class TrackerProductiveBreakDownSerializer(serializers.Serializer):
    """
    Please note that the time_start and time_end variables will be
    assumed as localtime and converted to equivalent UTC Format
    for proper results.
    """

    date = serializers.DateField(required=False, default=datetime.now().date())
    user = serializers.CharField()
    start_time = serializers.TimeField(required=False, format=api_settings.TIME_FORMAT)
    end_time = serializers.TimeField(required=False, format=api_settings.TIME_FORMAT)

    OUTPUT_FORMAT_CHOICES = ("activity", "day")
    output_format = serializers.ChoiceField(
        choices=OUTPUT_FORMAT_CHOICES,
        required=False,
        default="activity"
    )

    number_of_days_in_work_week = serializers.IntegerField(required=False, default=5)
    work_days_to_ignore = serializers.CharField(required=False, default="saturday,sunday")

    VALID_WEEK_NAMES = (
        "monday", "tuesday", "wednesday",
        "thursday", "friday", "saturday",
        "sunday"
    )

    # Reference: https://www.yourdictionary.com/articles/abbreviations-days-months
    SHORTCUT_NAMES = {
        "mon": "monday", "m": "monday",
        "tue": "tuesday", "tues": "tuesday", "tu": "tuesday", "t": "tuesday",
        "wed": "wednesday", "w": "wednesday",
        "thu": "thursday", "thur": "thursday", "thurs": "thursday", "th": "thursday", "r": "thursday",
        "fri": "friday", "f": "friday",
        "sat": "saturday", "s": "saturday",
        "sun": "sunday", "su": "sunday", "u": "sunday"
    }
    week_start = serializers.CharField(required=False, default="monday")

    def validate_number_of_days_in_work_week(self, number_of_days_in_work_week):
        if number_of_days_in_work_week <= 0 or number_of_days_in_work_week > 7:
            msg = ("Number of days in work week cannot be less than 0 or "
                   + "more than 7")
            raise serializers.ValidationError(msg)
        return number_of_days_in_work_week

    def validate_week_start(self, week_start):
        if week_start in self.SHORTCUT_NAMES:
            week_start = self.SHORTCUT_NAMES[week_start]
            return week_start
        
        if week_start not in self.VALID_WEEK_NAMES:
            msg = "Please provide a valid week name"
            raise serializers.ValidationError(msg)

        return week_start

    def validate_work_days_to_ignore(self, work_days_to_ignore):
        work_days_to_ignore_list: list[str] = work_days_to_ignore.split(",")
        final_work_day_list = []
        for work_day in work_days_to_ignore_list:
            work_day = work_day.strip()
            if work_day in self.SHORTCUT_NAMES:
                work_day_to_add = self.SHORTCUT_NAMES.get(work_day)
                if work_day_to_add not in final_work_day_list:
                    final_work_day_list.append(work_day_to_add)
                continue

            if work_day not in self.VALID_WEEK_NAMES:
                raise serializers.ValidationError("Please provide valid work days as comma seperated values")

            if work_day not in final_work_day_list:
                final_work_day_list.append(work_day)

        return final_work_day_list

    def validate_user(self, user):
        user_object = Users.objects.filter(employee_id=user).first()
        if user_object is None:
            raise serializers.ValidationError("Provided user does not exist")

        return user_object

    def validate(self, attrs):
        start_time = attrs.get("start_time")
        end_time = attrs.get("end_time")

        if start_time is None and end_time is None:
            return attrs

        if ((start_time is not None and end_time is None)
            or (start_time is None and end_time is not None)):
            msg = ("Please provide both start_time and end_time parameters. "
                   + "By default, the first discovered and the last discovered "
                   + "time for the requested user will be used.")
            raise serializers.ValidationError(msg)

        if isinstance(start_time, str):
            start_time = (
                datetime.strptime(start_time, api_settings.TIME_FORMAT)
                .replace(tzinfo=ZoneInfo(settings.TIME_ZONE))
            )
        if isinstance(end_time, str):
            end_time = (
                datetime.strptime(end_time, api_settings.TIME_FORMAT)
                .replace(tzinfo=ZoneInfo(settings.TIME_ZONE))
            )

        if start_time > end_time:
            msg = "Start time should be lesser than End time"
            raise serializers.ValidationError(msg)

        if start_time.tzinfo not in (std_timezone.utc, ZoneInfo("UTC")):
            if isinstance(start_time, std_time):
                attrs["start_time"] = (
                    datetime.combine(datetime.now().date(), start_time)
                    .astimezone(ZoneInfo("UTC"))
                    .time()
                )
            else:
                attrs["start_time"] = start_time.astimezone(ZoneInfo("UTC"))

        if end_time.tzinfo not in (std_timezone.utc, ZoneInfo("UTC")):
            if isinstance(end_time, std_time):    
                attrs["end_time"] = (
                    datetime.combine(datetime.now().date(), end_time)
                    .astimezone(ZoneInfo("UTC"))
                    .time()
                )
            else:
                attrs["end_time"] = end_time.astimezone(ZoneInfo("UTC"))

        return attrs


class TrackerCategoryBreakDownSerializer(serializers.Serializer):
    date = serializers.DateField()
    user = serializers.CharField()
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()

    def validate_user(self, user):
        user_object = Users.objects.filter(employee_id=user).first()
        if user_object is None:
            raise serializers.ValidationError("Provided user uuid does not exist")
        return user_object

    def validate(self, attrs):
        start_time = attrs.get("start_time")
        end_time = attrs.get("end_time")

        if start_time is None and end_time is None:
            return attrs

        if ((start_time is not None and end_time is None)
            or (start_time is None and end_time is not None)):
            msg = ("Please provide both start_time and end_time parameters. "
                   + "By default, the first discovered and the last discovered "
                   + "time for the requested user will be used.")
            raise serializers.ValidationError(msg)

        if isinstance(start_time, str):
            start_time = (
                datetime.strptime(start_time, api_settings.TIME_FORMAT)
                .replace(tzinfo=ZoneInfo(settings.TIME_ZONE))
            )
        if isinstance(end_time, str):
            end_time = (
                datetime.strptime(end_time, api_settings.TIME_FORMAT)
                .replace(tzinfo=ZoneInfo(settings.TIME_ZONE))
            )

        if start_time > end_time:
            msg = "Start time should be lesser than End time"
            raise serializers.ValidationError(msg)

        if start_time.tzinfo not in (std_timezone.utc, ZoneInfo("UTC")):
            if isinstance(start_time, std_time):
                attrs["start_time"] = (
                    datetime.combine(datetime.now().date(), start_time)
                    .astimezone(ZoneInfo("UTC"))
                    .time()
                )
            else:
                attrs["start_time"] = start_time.astimezone(ZoneInfo("UTC"))

        if end_time.tzinfo not in (std_timezone.utc, ZoneInfo("UTC")):
            if isinstance(end_time, std_time):    
                attrs["end_time"] = (
                    datetime.combine(datetime.now().date(), end_time)
                    .astimezone(ZoneInfo("UTC"))
                    .time()
                )
            else:
                attrs["end_time"] = end_time.astimezone(ZoneInfo("UTC"))

        return attrs


class TrackerApplicationGroupsSerializer(serializers.Serializer):
    date = serializers.DateField()
    user = serializers.CharField()
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()

    def validate_user(self, user):
        user_object = Users.objects.filter(employee_id=user).first()
        if user_object is None:
            raise serializers.ValidationError("Provided user uuid does not exist")
        return user_object

    def validate(self, attrs):
        start_time = attrs.get("start_time")
        end_time = attrs.get("end_time")

        if start_time is None and end_time is None:
            return attrs

        if ((start_time is not None and end_time is None)
            or (start_time is None and end_time is not None)):
            msg = ("Please provide both start_time and end_time parameters. "
                   + "By default, the first discovered and the last discovered "
                   + "time for the requested user will be used.")
            raise serializers.ValidationError(msg)

        if isinstance(start_time, str):
            start_time = (
                datetime.strptime(start_time, api_settings.TIME_FORMAT)
                .replace(tzinfo=ZoneInfo(settings.TIME_ZONE))
            )
        if isinstance(end_time, str):
            end_time = (
                datetime.strptime(end_time, api_settings.TIME_FORMAT)
                .replace(tzinfo=ZoneInfo(settings.TIME_ZONE))
            )

        if start_time > end_time:
            msg = "Start time should be lesser than End time"
            raise serializers.ValidationError(msg)

        if start_time.tzinfo not in (std_timezone.utc, ZoneInfo("UTC")):
            if isinstance(start_time, std_time):
                attrs["start_time"] = (
                    datetime.combine(datetime.now().date(), start_time)
                    .astimezone(ZoneInfo("UTC"))
                    .time()
                )
            else:
                attrs["start_time"] = start_time.astimezone(ZoneInfo("UTC"))

        if end_time.tzinfo not in (std_timezone.utc, ZoneInfo("UTC")):
            if isinstance(end_time, std_time):    
                attrs["end_time"] = (
                    datetime.combine(datetime.now().date(), end_time)
                    .astimezone(ZoneInfo("UTC"))
                    .time()
                )
            else:
                attrs["end_time"] = end_time.astimezone(ZoneInfo("UTC"))

        return attrs
