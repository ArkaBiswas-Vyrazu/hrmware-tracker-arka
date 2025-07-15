"""Hrmware Tracker API - Type Definitions"""

from datetime import datetime
from typing import Literal, TypedDict

Weekday = (
    Literal["monday"]
    | Literal["tuesday"]
    | Literal["wednesday"]
    | Literal["thursday"]
    | Literal["friday"]
    | Literal["saturday"]
    | Literal["sunday"]
)


class TimeTracker(TypedDict):
    productive_time: int
    non_productive_time: int
    neutral_time: int


class TimeBarDataItem(TypedDict):
    """Type Definition for Time Bar Data Items"""

    start_time: datetime
    end_time: datetime
    productivity_status_map: dict[str, int]
