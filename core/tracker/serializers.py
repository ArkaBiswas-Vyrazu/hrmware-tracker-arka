"""HRMWARE Tracker API Serializers"""

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
        if attrs["lastUsed"] == "" and attrs["isActive"] != True:
            raise serializers.ValidationError("lastUsed cannot be blank when isActive is False")

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

    def validate(self, attrs):
        super().validate(attrs)

        user = Users.objects.filter(employee_id=attrs.get("user")).first()
        if user is None:
            raise serializers.ValidationError("User does not exist")
        
        attrs["user"] = user
        return attrs
