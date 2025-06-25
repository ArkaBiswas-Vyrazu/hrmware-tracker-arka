from django.db import models


class ActivityLogs(models.Model):
    id = models.BigAutoField(primary_key=True)
    log_id = models.CharField(unique=True, max_length=255)
    window_title = models.TextField()
    start_timestamp = models.DateTimeField()
    end_timestamp = models.DateTimeField()
    duration = models.IntegerField(db_comment='Measured in seconds')
    app = models.ForeignKey('TrackerApps', models.CASCADE)
    category = models.ForeignKey('TrackerAppCategories', models.CASCADE)

    PRODUCTIVITY_STATUS_CHOICES = {
        "productive": "productive",
        "non-productive": "non-productive",
        "neutral": "neutral",
    }


    productivity_status = models.CharField(max_length=255, choices=PRODUCTIVITY_STATUS_CHOICES)
    user = models.ForeignKey('Users', models.CASCADE)

    class Meta:
        managed = False
        db_table = 'activity_logs'


# class AlembicVersion(models.Model):
#     version_num = models.CharField(primary_key=True, max_length=32)

#     class Meta:
#         managed = False
#         db_table = 'alembic_version'


class Screenshots(models.Model):
    id = models.BigAutoField(primary_key=True)
    uuid = models.CharField(unique=True, max_length=255)
    user = models.ForeignKey('Users', models.DO_NOTHING)
    capture_time = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'screenshots'


class TimeSegments(models.Model):
    id = models.BigAutoField(primary_key=True)
    uuid = models.CharField(unique=True, max_length=255)
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    duration = models.IntegerField()

    SEGMENT_TYPE_CHOICES = {
        "productive": "productive",
        "non-productive": "non-productive",
        "neutral": "neutral",
        "away": "away",
        "idle": "idle",
    }

    segment_type = models.CharField(max_length=255, choices=SEGMENT_TYPE_CHOICES)

    class Meta:
        managed = False
        db_table = 'time_segments'


class TrackerAppCategories(models.Model):
    id = models.BigAutoField(primary_key=True)
    uuid = models.CharField(unique=True, max_length=255)
    name = models.CharField(unique=True, max_length=255)

    class Meta:
        managed = False
        db_table = 'tracker_app_categories'


class TrackerAppCategoriesMapping(models.Model):
    id = models.BigAutoField(primary_key=True)
    app = models.ForeignKey('TrackerApps', models.DO_NOTHING)
    category = models.ForeignKey(TrackerAppCategories, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'tracker_app_categories_mapping'
        unique_together = (('app', 'category'),)


class TrackerApps(models.Model):
    id = models.BigAutoField(primary_key=True)
    uuid = models.CharField(unique=True, max_length=255)
    name = models.CharField(unique=True, max_length=255)

    class Meta:
        managed = False
        db_table = 'tracker_apps'


class TrackerSummaries(models.Model):
    id = models.BigAutoField(primary_key=True)
    summary_id = models.CharField(unique=True, max_length=255)
    summary_date = models.DateField()
    start_time = models.TimeField()
    last_seen_time = models.TimeField()
    working_time = models.IntegerField()
    productive_time = models.IntegerField()
    non_productive_time = models.IntegerField()
    away_time = models.IntegerField()
    user = models.ForeignKey('Users', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'tracker_summaries'


class Users(models.Model):
    id = models.BigAutoField(primary_key=True)
    organization_id = models.CharField(max_length=255)
    employee_id = models.CharField(unique=True, max_length=255)
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    email = models.CharField(unique=True, max_length=255)
    password = models.CharField(max_length=255)
    remember_token = models.CharField(max_length=100, blank=True, null=True)
    type = models.CharField(max_length=100)
    status = models.IntegerField()
    deleted_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    activation_confirm = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'users'
