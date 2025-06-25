"""HRMWARE Tracker API - Models Schema

ORM Definitions have been set for database agnostic operations.
"""

from datetime import datetime, date, time
import uuid
import enum

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import (
    BigInteger,
    String,
    Integer,
    DateTime,
    ForeignKey,
    Identity,
    Date,
    Time,
    Text,
    Enum,
    UniqueConstraint,
    func
)


class Base(DeclarativeBase):
    """SQLAlchemy ORM Base Initialization"""

    pass


class Users(Base):
    """Main Users Model

    Following schema has been setup to follow the version provided in
    the HRMWARE project
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(255), nullable=False)
    employee_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    first_name: Mapped[str] = mapped_column(String(255))
    last_name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    remember_token: Mapped[str] = mapped_column(String(100), nullable=True)
    type_: Mapped[str] = mapped_column("type", String(100), nullable=False)
    status: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    activation_confirm: Mapped[int] = mapped_column(Integer, nullable=False)

    # devices: Mapped[list["Devices"]] = relationship(back_populates="user")

    def __repr__(self):
        return f"Users(id={self.id!r}, email={self.email!r})"


# class Devices(Base):
#     """Model For tracking User Devices

#     Here, we assume that a user may use the tracker on multiple devices.
#     At the moment, this model is not to be used as it may not be required
#     right now. Moreover, uniquely identifying devices is a bit complex, and
#     properly identifying devices requires privacy invasion... which is obviously
#     a bad idea.
#     """

#     __tablename__ = "devices"

#     id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
#     uuid: Mapped[str] = mapped_column(String(255), unique=True, default=uuid.uuid4(), nullable=False)
#     device_name: Mapped[str] = mapped_column(String(255), nullable=False)
#     os: Mapped[str] = mapped_column(String(255), nullable=False)
#     last_seen: Mapped[datetime] = mapped_column(DateTime, nullable=False)
#     created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

#     user_id: Mapped[int] = mapped_column(
#             ForeignKey(
#                 f"{Users.__tablename__}.id",
#                 name="fk_devices_users"
#             ),
#             nullable=False
#     )
#     user: Mapped["Users"] = relationship(back_populates="devices")


class TrackerSummaries(Base):
    """Model For collecting tracker summaries.

    Date in this table will be created and/or updated only when analytics
    are requested.
    """

    __tablename__ = "tracker_summaries"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    summary_id: Mapped[str] = mapped_column(String(255), unique=True, default=uuid.uuid4(), nullable=False)
    summary_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    last_seen_time: Mapped[time] = mapped_column(Time, nullable=False)

    # Time tracked in seconds
    working_time: Mapped[int] = mapped_column(Integer, nullable=False)
    productive_time: Mapped[int] = mapped_column(Integer, nullable=False)
    non_productive_time: Mapped[int] = mapped_column(Integer, nullable=False)
    away_time: Mapped[int] = mapped_column(Integer, nullable=False)

    user_id: Mapped[int] = mapped_column(
            ForeignKey(
                f"{Users.__tablename__}.id",
                name="fk_tracker_summaries_users",
            ),
            nullable=False
    )
    user: Mapped["Users"] = relationship()

    def __repr__(self):
        return f"TrackerSummaries(id={self.id!r}, summary_id={self.summary_id!r}"


class TrackerAppCategories(Base):
    """Model for storing categories defined for each application.

    This ensures the ability to modify the category of an app safely.
    """

    __tablename__ = "tracker_app_categories"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    uuid: Mapped[str] = mapped_column(String(255), unique=True, default=uuid.uuid4(), nullable=False)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    def __repr__(self):
        return f"TrackerAppCategories(id={self.id!r}, uuid={self.uuid!r}, name={self.name!r}"


class TrackerApps(Base):
    """Model for storing apps that have been encountered by users

    While this is not required at this time, this ensures that the system can be extended later on.
    Ideally, records will be saved when the app first encounters them.
    """

    __tablename__ = "tracker_apps"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    uuid: Mapped[str] = mapped_column(String(255), unique=True, default=uuid.uuid4(), nullable=False)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    
    def __repr__(self):
        return f"TrackerApps(id={self.id!r}, uuid={self.uuid!r}, name={self.name!r}"


class TrackerAppCategoriesMapping(Base):
    """Model for mapping categories to apps."""

    __tablename__ = "tracker_app_categories_mapping"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)

    app_id: Mapped[int] = mapped_column(
            ForeignKey(
                f"{TrackerApps.__tablename__}.id",
                name="fk_tracker_app_categories_mapping_tracker_apps",
            ),
            nullable=False,
    )
    app: Mapped["TrackerApps"] = relationship()

    category_id: Mapped[int] = mapped_column(
            ForeignKey(
                f"{TrackerAppCategories.__tablename__}.id",
                name="fk_tracker_app_categories_mapping_tracker_app_categories",
            ),
            nullable=False,
    )
    category: Mapped["Category"] = relationship()

    __table_args__ = (
            UniqueConstraint(
                "app_id", "category_id",
                name="uq_tracker_app_categories_mapping_app_id_category_id",
            ),
    )

    def __repr__(self):
        return f"TrackerAppCategoriesMapping(id={self.id!r}, app_id={self.app_id!r}, category_id={self.category_id!r}"


class ActivityLogs(Base):
    """Model for storing granular logs of tracker activity

    Ideally, we would like to update the table instead of adding logs, as this
    table can get way too large.

    That being said, we are currently adding logs.
    """

    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    log_id: Mapped[str] = mapped_column(String(255), unique=True, default=uuid.uuid4(), nullable=False)
    window_title: Mapped[str] = mapped_column(Text, nullable=False)
    start_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration: Mapped[int] = mapped_column(Integer, nullable=False, comment="Measured in seconds")
    
    # app_name: Mapped[str] = mapped_column(String(255), nullable=False)
    app_id: Mapped[int] = mapped_column(
            ForeignKey(
               f"{TrackerApps.__tablename__}.id",
               name="fk_activity_logs_tracker_apps",
            ),
            nullable=False
    )
    app: Mapped["TrackerApps"] = relationship()

    category_id: Mapped[int] = mapped_column(
            ForeignKey(
              f"{TrackerAppCategories.__tablename__}.id",
              name="fk_activity_logs_tracker_app_categories",
            ),
            nullable=False
    )
    category: Mapped["TrackerAppCategories"] = relationship()

    productivity_status: Mapped[enum.Enum] = mapped_column(
            Enum(
                enum.Enum(
                    f"{__tablename__}_productivity_status_enum",
                    {
                        "productive": 1,
                        "non-productive": 2,
                        "neutral": 3
                    }
                )
            )
    )

    user_id: Mapped[int] = mapped_column(
            ForeignKey(
                f"{Users.__tablename__}.id",
                name="fk_tracker_summaries_users",
            ),
            nullable=False
    )
    user: Mapped["Users"] = relationship()

    def __repr__(self):
        return f"ActivityLogs(id={self.id!r}, user_id={self.user_id!r})"


class TimeSegments(Base):
    """Model used to store time segment data."""

    __tablename__ = "time_segments"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    uuid: Mapped[str] = mapped_column(String(255), unique=True, default=uuid.uuid4(), nullable=False)
    date_: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    duration: Mapped[int] = mapped_column(Integer, nullable=False)
    segment_type: Mapped[enum.Enum] = mapped_column(
            Enum(
                enum.Enum(
                    f"{__tablename__}_segment_type_enum",
                    {
                        "productive": 1,
                        "non-productive": 2,
                        "neutral": 3,
                        "away": 4,
                        "idle": 5
                    }
                )
            )
    )

    def __repr__(self):
        return f"TimeSegments(id={self.id!r})"


class Screenshots(Base):
    """Model for storing screenshot information"""

    __tablename__ = "screenshots"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    uuid: Mapped[str] = mapped_column(String(255), unique=True, default=uuid.uuid4(), nullable=False)
    
    user_id: Mapped[int] = mapped_column(
            ForeignKey(
                f"{Users.__tablename__}.id",
                name="fk_screenshots_users",
            ),
            nullable=False
    )
    user: Mapped["Users"] = relationship()

    capture_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    
    def __repr__(self):
        return "Screenshots(id={self.id!r}, uuid={self.uuid!r}, user_id={self.user_id!r}"
