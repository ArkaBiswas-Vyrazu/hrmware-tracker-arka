from datetime import datetime, timedelta
from uuid import uuid4

from django.db import models
from django.utils import timezone


class TrackerActivity(models.Model):
    id = models.BigAutoField(primary_key=True)
    tracker_activity_id = models.CharField(max_length=255)
    tracker_id = models.CharField(max_length=255)
    employee_id = models.CharField(max_length=255)
    screenshot = models.CharField(max_length=255)
    comment = models.CharField(max_length=255, blank=True, null=True)
    activity_level = models.FloatField(blank=True, null=True)
    duration = models.FloatField()
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "tracker_activity"
        ordering = ["id"]


class TrackerToken(models.Model):
    id = models.BigAutoField(primary_key=True)
    user_id = models.IntegerField()
    employee_id = models.CharField(max_length=255)
    token = models.CharField(max_length=255)
    ip = models.CharField(max_length=255, blank=True, null=True)
    device_id = models.CharField(max_length=255)
    os = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "tracker_token"
        ordering = ["id"]


class ActivityLogs(models.Model):
    id = models.BigAutoField(primary_key=True)
    log_id = models.UUIDField(unique=True, default=uuid4, editable=False)
    window_title = models.TextField()
    start_timestamp = models.DateTimeField()
    end_timestamp = models.DateTimeField()
    app = models.ForeignKey("TrackerApps", models.CASCADE)
    category = models.ForeignKey("TrackerAppCategories", models.CASCADE)
    is_active = models.BooleanField()

    # Here, duration does not mean end_time - start_time
    # It is the duration measured from start_time to the time the
    # currently tracked activity ends
    duration = models.IntegerField()  # Measured in seconds

    # This does not work with older Django Versions
    # PRODUCTIVITY_STATUS_CHOICES = {
    #     "productive": "productive",
    #     "non-productive": "non-productive",
    #     "neutral": "neutral",
    # }
    PRODUCTIVITY_STATUS_CHOICES = (
        ("productive", "productive"),
        ("non-productive", "non-productive"),
        ("neutral", "neutral"),
    )

    productivity_status = models.CharField(max_length=255, choices=PRODUCTIVITY_STATUS_CHOICES)
    user = models.ForeignKey("authentication.Users", models.CASCADE)

    class Meta:
        managed = True
        db_table = "activity_logs"

    def get_actual_end_time(self) -> datetime:
        return self.start_timestamp + timedelta(seconds=self.duration)


class Screenshots(models.Model):
    id = models.BigAutoField(primary_key=True)
    uuid = models.UUIDField(unique=True, default=uuid4, editable=False)
    user = models.ForeignKey("authentication.Users", models.CASCADE)
    capture_time = models.DateTimeField()

    class Meta:
        managed = True
        db_table = "screenshots"


class TimeSegments(models.Model):
    id = models.BigAutoField(primary_key=True)
    uuid = models.UUIDField(unique=True, default=uuid4, editable=False)
    date = models.DateField(default=timezone.now)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()

    # Here, duration does not mean end_time - start_time
    # It is the duration measured from start_time to the time the
    # currently tracked activity ends
    duration = models.IntegerField()  # Measured in seconds

    # This does not work with older Django Versions
    # SEGMENT_TYPE_CHOICES = {
    #     "productive": "productive",
    #     "non-productive": "non-productive",
    #     "neutral": "neutral",
    #     "away": "away",
    #     "idle": "idle",
    # }
    SEGMENT_TYPE_CHOICES = (
        ("productive", "productive"),
        ("non-productive", "non-productive"),
        ("neutral", "neutral"),
        ("away", "away"),
        ("idle", "idle"),
    )

    segment_type = models.CharField(max_length=255, choices=SEGMENT_TYPE_CHOICES, default="neutral")
    user = models.ForeignKey("authentication.Users", models.CASCADE)

    activity_log = models.OneToOneField(
        "ActivityLogs",
        models.CASCADE,
        related_name="time_segment",
        null=True,
        blank=False,
        default=None,
    )

    class Meta:
        managed = True
        db_table = "time_segments"

    def get_actual_end_time(self) -> datetime:
        return (
            timedelta(seconds=self.duration)
            # + datetime.combine(self.date, self.start_time)
            + self.start_time
        )


class TrackerAppCategories(models.Model):
    id = models.BigAutoField(primary_key=True)
    uuid = models.UUIDField(unique=True, default=uuid4, editable=False)
    name = models.CharField(unique=True, max_length=255)

    # This does not work with older Django Versions
    # PRODUCTIVITY_STATUS_CHOICES = {
    #     "productive": "productive",
    #     "non-productive": "non-productive",
    #     "neutral": "neutral",
    # }
    PRODUCTIVITY_STATUS_CHOICES = (
        ("productive", "productive"),
        ("non-productive", "non-productive"),
        ("neutral", "neutral"),
    )
    productivity_status_type = models.CharField(
        max_length=255, choices=PRODUCTIVITY_STATUS_CHOICES, default="neutral"
    )

    class Meta:
        managed = True
        db_table = "tracker_app_categories"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        activity_logs = ActivityLogs.objects.filter(category=self)
        if not activity_logs.exists():
            return

        for activity_log in activity_logs:
            activity_log.productivity_status = self.productivity_status_type
            activity_log.save()

            time_segments = TimeSegments.objects.filter(activity_log=activity_log)
            for time_segment in time_segments:
                time_segment.segment_type = activity_log.productivity_status
                time_segment.save()

        return


class TrackerApps(models.Model):
    id = models.BigAutoField(primary_key=True)
    uuid = models.UUIDField(unique=True, default=uuid4, editable=False)
    name = models.CharField(unique=True, max_length=255)
    actual_name = models.CharField(max_length=255)
    category = models.ForeignKey("TrackerAppCategories", models.CASCADE, related_name="apps")

    class Meta:
        managed = True
        db_table = "tracker_apps"

    def update(self, *args, **kwargs):
        self.save(*args, **kwargs)

        activity_logs = ActivityLogs.objects.filter(app=self).exclude(
            productivity_status=self.category.productivity_status_type
        )
        for activity_log in activity_logs:
            if activity_log.productivity_status != self.category.productivity_status_type:
                activity_log.productivity_status = self.category.productivity_status_type
                activity_log.save()

            time_segments = TimeSegments.objects.filter(activity_log=activity_log)
            for time_segment in time_segments:
                if time_segment.segment_type != activity_log.productivity_status:
                    time_segment.segment_type = activity_log.productivity_status
                    time_segment.save()

        return

    def save(self, name=None, *args, **kwargs):
        self.actual_name = name or kwargs.get("name") or getattr(self, "name", None)
        if self.actual_name is None:
            try:
                self.actual_name = args[0]
            except IndexError:
                self.actual_name = None
        return super().save(*args, **kwargs)


class TrackerSummaries(models.Model):
    id = models.BigAutoField(primary_key=True)
    summary_id = models.UUIDField(unique=True, default=uuid4, editable=False)
    summary_date = models.DateField()
    start_time = models.TimeField()
    last_seen_time = models.TimeField()
    working_time = models.IntegerField()
    productive_time = models.IntegerField()
    non_productive_time = models.IntegerField()
    away_time = models.IntegerField()
    user = models.ForeignKey("authentication.Users", models.CASCADE)

    class Meta:
        managed = True
        db_table = "tracker_summaries"
