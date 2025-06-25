"""HRMWARE Tracker API Serializers"""

from rest_framework import serializers
from .models import ActivityLogs


class ActivityLogsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityLogs
        fields = "__all__"


class ActivityLogsDataItemsSessionSerializer(serializers.Serializer):
    duration = serializers.IntegerField()
    start_time = serializers.CharField()
    end_time = serializers.CharField(allow_blank=True)


class ActivityLogsDataItemsSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    firstUsed = serializers.CharField()
    lastUsed = serializers.CharField()
    name = serializers.CharField()
    title = serializers.CharField()
    session = ActivityLogsDataItemsSessionSerializer(many=True)
    totalUsage = serializers.IntegerField()
    isActive = serializers.BooleanField()


class ActivityLogsDataSerializer(serializers.Serializer):
    allWindows = ActivityLogsDataItemsSerializer(many=True)
