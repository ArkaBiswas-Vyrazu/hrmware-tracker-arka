from uuid import uuid4
import unicodedata
from collections.abc import Iterable
from datetime import timedelta, datetime

from django.db import models
from django.db import models
from django.apps import apps
from django.contrib.auth import password_validation, get_backends
from django.conf import settings
from django.utils.crypto import salted_hmac
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.models import (
    BaseUserManager,
    Group,
    Permission,
)
from django.contrib.auth.hashers import (
    acheck_password,
    is_password_usable,
    make_password,
    check_password
)
from django.utils import timezone


class ActivityLogs(models.Model):
    id = models.BigAutoField(primary_key=True)
    log_id = models.UUIDField(unique=True, default=uuid4, editable=False)
    window_title = models.TextField()
    start_timestamp = models.DateTimeField()
    end_timestamp = models.DateTimeField()
    duration = models.IntegerField(db_comment='Measured in seconds')
    app = models.ForeignKey('TrackerApps', models.CASCADE)
    category = models.ForeignKey('TrackerAppCategories', models.CASCADE)
    is_active = models.BooleanField()

    PRODUCTIVITY_STATUS_CHOICES = {
        "productive": "productive",
        "non-productive": "non-productive",
        "neutral": "neutral",
    }

    productivity_status = models.CharField(max_length=255, choices=PRODUCTIVITY_STATUS_CHOICES)
    user = models.ForeignKey('Users', models.CASCADE)

    class Meta:
        managed = True
        db_table = 'activity_logs'


class Screenshots(models.Model):
    id = models.BigAutoField(primary_key=True)
    uuid = models.UUIDField(unique=True, default=uuid4, editable=False)
    user = models.ForeignKey('Users', models.CASCADE)
    capture_time = models.DateTimeField()

    class Meta:
        managed = True
        db_table = 'screenshots'


class TimeSegments(models.Model):
    id = models.BigAutoField(primary_key=True)
    uuid = models.UUIDField(unique=True, default=uuid4, editable=False)
    date = models.DateField(default=timezone.now)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()

    # Here, duration does not mean end_time - start_time
    # It is the duration measured from start_time to the time the
    # currently tracked activity ends
    duration = models.IntegerField(db_comment="Measured in seconds")

    SEGMENT_TYPE_CHOICES = {
        "productive": "productive",
        "non-productive": "non-productive",
        "neutral": "neutral",
        "away": "away",
        "idle": "idle",
    }

    segment_type = models.CharField(max_length=255, choices=SEGMENT_TYPE_CHOICES, default="neutral")
    user = models.ForeignKey("Users", models.CASCADE)

    activity_log = models.OneToOneField(
        "ActivityLogs",
        models.CASCADE,
        related_name="time_segment",
        null=True,
        blank=False,
        default=None
    )

    class Meta:
        managed = True
        db_table = 'time_segments'

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

    PRODUCTIVITY_STATUS_CHOICES = {
        "productive": "productive",
        "non-productive": "non-productive",
        "neutral": "neutral",
    }
    productivity_status_type = models.CharField(
        max_length=255,
        choices=PRODUCTIVITY_STATUS_CHOICES,
        default="neutral"
    )

    class Meta:
        managed = True
        db_table = 'tracker_app_categories'


class TrackerApps(models.Model):
    id = models.BigAutoField(primary_key=True)
    uuid = models.UUIDField(unique=True, default=uuid4, editable=False)
    name = models.CharField(unique=True, max_length=255)
    category: "TrackerAppCategories" = models.ForeignKey(
        "TrackerAppCategories",
        models.CASCADE,
        related_name="apps"
    )

    class Meta:
        managed = True
        db_table = 'tracker_apps'


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
    user = models.ForeignKey('Users', models.CASCADE)

    class Meta:
        managed = True
        db_table = 'tracker_summaries'


class UserManager(BaseUserManager):
    def create_user(self, first_name, email, password, **extra_fields):
        if not email:
            raise ValueError('User must have an email address')
        user = self.model(email=self.normalize_email(email),first_name=first_name,**extra_fields)
        user.set_password(password)
        user.save(using=self._db)

        return user
    
    def create_superuser(self, first_name, email, password, **fields):
        user = self.create_user(first_name=first_name, email=email, password=password, **fields)
        user.is_admin = True
        user.save()
        return user


class AbstractBaseUser(models.Model):
    password = models.CharField(_("password"), max_length=128)

    REQUIRED_FIELDS = []

    # Stores the raw password if set_password() is called so that it can
    # be passed to password_changed() after the model is saved.
    _password = None

    class Meta:
        abstract = True

    def __str__(self):
        return self.get_username()

    # RemovedInDjango60Warning: When the deprecation ends, replace with:
    # def save(self, **kwargs):
    #   super().save(**kwargs)
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self._password is not None:
            password_validation.password_changed(self._password, self)
            self._password = None

    def get_username(self):
        """Return the username for this User."""
        return getattr(self, self.USERNAME_FIELD)

    def clean(self):
        setattr(self, self.USERNAME_FIELD, self.normalize_username(self.get_username()))

    def natural_key(self):
        return (self.get_username(),)

    @property
    def is_anonymous(self):
        """
        Always return False. This is a way of comparing User objects to
        anonymous users.
        """
        return False

    @property
    def is_authenticated(self):
        """
        Always return True. This is a way to tell if the user has been
        authenticated in templates.
        """
        return True

    def set_password(self, raw_password):
        self.password = make_password(raw_password)
        # self.password = bcrypt.hashpw(raw_password.encode('utf-8'), bcrypt.gensalt())
        self._password = raw_password

    def check_password(self, raw_password):
        """
        Return a boolean of whether the raw_password was correct. Handles
        hashing formats behind the scenes.
        """

        def setter(raw_password):
            self.set_password(raw_password)
            # Password hash upgrades shouldn't be considered password changes.
            self._password = None
            self.save(update_fields=["password"])

        if self.password.startswith(('$2b', '$2a', '$2x', '$2y')):
            # if self.password.startswith(('$2x','$2y')):
            #     print(self.password, 'bcrypt$$2b'+self.password[3:])
            #     return check_password(raw_password, 'bcrypt$$2b'+self.password[3:], setter)
            return check_password(raw_password, 'bcrypt$'+self.password, setter)

        return check_password(raw_password, self.password, setter)

    async def acheck_password(self, raw_password):
        """See check_password()."""

        async def setter(raw_password):
            self.set_password(raw_password)
            # Password hash upgrades shouldn't be considered password changes.
            self._password = None
            await self.asave(update_fields=["password"])

        return await acheck_password(raw_password, self.password, setter)

    def set_unusable_password(self):
        # Set a value that will never be a valid hash
        self.password = make_password(None)

    def has_usable_password(self):
        """
        Return False if set_unusable_password() has been called for this user.
        """
        return is_password_usable(self.password)

    def get_session_auth_hash(self):
        """
        Return an HMAC of the password field.
        """
        return self._get_session_auth_hash()

    def get_session_auth_fallback_hash(self):
        for fallback_secret in settings.SECRET_KEY_FALLBACKS:
            yield self._get_session_auth_hash(secret=fallback_secret)

    def _get_session_auth_hash(self, secret=None):
        key_salt = "django.contrib.auth.models.AbstractBaseUser.get_session_auth_hash"
        return salted_hmac(
            key_salt,
            self.password,
            secret=secret,
            algorithm="sha256",
        ).hexdigest()

    @classmethod
    def get_email_field_name(cls):
        try:
            return cls.EMAIL_FIELD
        except AttributeError:
            return "email"

    @classmethod
    def normalize_username(cls, username):
        return (
            unicodedata.normalize("NFKC", username)
            if isinstance(username, str)
            else username
        )

# A few helper functions for common logic between User and AnonymousUser.
def _user_get_permissions(user, obj, from_name):
    permissions = set()
    name = "get_%s_permissions" % from_name
    for backend in get_backends():
        if hasattr(backend, name):
            permissions.update(getattr(backend, name)(user, obj))
    return permissions


class PermissionsMixin(models.Model):
    """
    Add the fields and methods necessary to support the Group and Permission
    models using the ModelBackend.
    """

    groups = models.ManyToManyField(
        Group,
        verbose_name=_("groups"),
        blank=True,
        help_text=_(
            "The groups this user belongs to. A user will get all permissions "
            "granted to each of their groups."
        ),
        related_name="user_set",
        related_query_name="user",
    )
    user_permissions = models.ManyToManyField(
        Permission,
        verbose_name=_("user permissions"),
        blank=True,
        help_text=_("Specific permissions for this user."),
        related_name="user_set",
        related_query_name="user",
    )

    class Meta:
        abstract = True

    def get_user_permissions(self, obj=None):
        """
        Return a list of permission strings that this user has directly.
        Query all available auth backends. If an object is passed in,
        return only permissions matching this object.
        """
        return _user_get_permissions(self, obj, "user")

    def get_group_permissions(self, obj=None):
        """
        Return a list of permission strings that this user has through their
        groups. Query all available auth backends. If an object is passed in,
        return only permissions matching this object.
        """
        return _user_get_permissions(self, obj, "group")

    def get_all_permissions(self, obj=None):
        return _user_get_permissions(self, obj, "all")

    # def has_perm(self, perm, obj=None):
    #     """
    #     Return True if the user has the specified permission. Query all
    #     available auth backends, but return immediately if any backend returns
    #     True. Thus, a user who has permission from a single auth backend is
    #     assumed to have permission in general. If an object is provided, check
    #     permissions for that object.
    #     """
    #     # Active superusers have all permissions.
    #     if self.is_active and self.is_superuser:
    #         return True

    #     # Otherwise we need to check the backends.
    #     return _user_has_perm(self, perm, obj)

    def has_perms(self, perm_list, obj=None):
        """
        Return True if the user has each of the specified permissions. If
        object is passed, check if the user has all required perms for it.
        """
        if not isinstance(perm_list, Iterable) or isinstance(perm_list, str):
            raise ValueError("perm_list must be an iterable of permissions.")
        return all(self.has_perm(perm, obj) for perm in perm_list)

    # def has_module_perms(self, app_label):
    #     """
    #     Return True if the user has any permissions in the given app label.
    #     Use similar logic as has_perm(), above.
    #     """
    #     # Active superusers have all permissions.
    #     if self.is_active and self.is_superuser:
    #         return True

    #     return _user_has_module_perms(self, app_label)


class Users(AbstractBaseUser, PermissionsMixin):
    organization_id = models.CharField(max_length=255)
    employee_id = models.CharField(max_length=255, unique=True)
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    email = models.CharField(unique=True, max_length=255)
    password = models.CharField(max_length=255)
    remember_token = models.CharField(max_length=100, blank=True, null=True)
    type = models.CharField(max_length=255)
    status = models.IntegerField(default=1)
    deleted_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, blank=True, null=True)
    activation_confirm = models.IntegerField(blank=True, null=True)
    is_admin = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name']

    @property
    def is_staff(self):
        return self.is_admin

    def __str__(self):
        return self.email

    class Meta:
        db_table = 'users'
        ordering = ['id']

    def getFullNameAttribute(self):
        return self.first_name + " " + self.last_name
