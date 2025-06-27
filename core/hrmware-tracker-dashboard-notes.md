# Hrmware Tracker Dashboard API Notes

All features noted here have been noted from [this html file](./employee-activity-v1.html).

## Example that will be used

Requested Date: 27 June 2025
Employee: John Doe
Started working at: 09:00 AM
Ended working at: 01:00 PM
Total Duration of Work: 4 Hours

## Key Features

### Time Bar

Displays productivity data throughout the requested day.

#### Example

```json
{
    {
        "start_time": "09:00 AM",
        "end_time": "10:30 AM",
        "productivity_status": "productive",
    },
    {
        "start_time": "10:30 AM",
        "end_time": "11:00 AM",
        "productivity_status": "neutral",
    },
    {
        "start_time": "11:00 AM",
        "end_time": "12:00 PM",
        "productivity_status": "non-productive",
    },
    {
        "start_time": "12:00 PM",
        "end_time": "1:00 PM",
        "productivity_status": "away",
    },
}
```

### Productivity Status

Display total productivity status time

#### Example

```json
{
    "productive_time": "1h 30m",
    "non_productive_time": "1h",
    "neutral_time": "30m"
}
```

### Basic Time Details

Shows an overview of the basic details like start time, away time, etc.

#### Example

```json
{
    "start_time": "09:00 AM",
    "working_time": "4hrs",
    "last_seen": "01:00 PM", // Can be the same as end_time
    "away_time": "1h"
}
```

### Weekly Summary

Shows working hours graph and away time graph for the week.

#### Possible Example Data

Extra Data here is taken directly from provided reference file.

```json
{
    "working_hours": {
        "monday": "8hrs 25m",
        "tuesday": "7hrs 50m",
        "wednesday": "8hrs",
        "thursday": "8.5hrs",
        "friday": "4hrs",
    },
    "away_time": {
        "monday": "45m",
        "tuesday": "1hr",
        "wednesday": "30m",
        "thursday": "36m",
        "friday": "1hr"
    }
}
```

### Live Feed

Shows what apps were accessed by the user

#### Example

Data here is taken directly from provided reference file.

```json
{
    {
        "app_name": "google-chrome",
        "action": "visited", // How do we even track this?!
        "time": "05:45 PM"
    },
    {
        "app_name": "code",
        "action": "active",
        "time": "05:42 PM",
    },
    {
        "app_name": null,
        "action": "away",
        "time": "05:30 PM"
    }
}
```

### Activity Distribution

Shows a graph for activity distribution
Should be able to use data from [productivity analysis](#productivity-status) and [basic details](#basic-time-details).

### Top Websites Visited

Shows top 5 websites visited in first glance, along with the time taken in each website.

#### Example

```json
{
    "top_websited_visited": [
        {
            "website": "github.com",
            "duration": "2hrs 15m"
        },
        {
            "website": "stackoverflow.com",
            "duration": "1hr 45m"
        }
    ]
}
```
