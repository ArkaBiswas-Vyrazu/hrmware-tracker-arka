"""HRMWARE Tracker API Serializers"""

from datetime import datetime
import json

from rest_framework import serializers
from .models import ActivityLogs, TimeSegments, Users


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

    # Reference: https://www.yourdictionary.com/articles/abbreviations-days-months
    shortcut_names = {
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

        if week_start in self.shortcut_names:
            week_start = self.shortcut_names[week_start]
            return week_start
        
        if week_start not in valid_week_names:
            msg = "Please provide a valid week name"
            raise serializers.ValidationError(msg)

        return week_start

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
