import json

from django.test import TestCase, Client
from django.urls import reverse_lazy

from .models import ActivityLogs, TrackerApps, TrackerAppCategories


class TestActivityLogCreate(TestCase):
    def test_create_activity_log(self):
        c = Client()

        url = reverse_lazy("tracker-api-view")
        data = {
            "allWindows": [
                {
                    "firstUsed": "12:45:44 PM",
                    "id": 48234500,
                    "lastUsed": "12:45:52 PM",
                    "name": "hrmware_v2",
                    "title": "HRMWARE",
                    # "session": [
                    #     {
                    #         "duration": 1,
                    #         "startTime": "12:45:44 PM",
                    #         "endTime": "12:45:45 PM"
                    #     },
                    #     {
                    #         "startTime": "12:45:52 PM",
                    #         "endTime": "",
                    #         "duration": 9
                    #     }
                    # ],
                    "totalUsage": 31,
                    "isActive": True
                },
                {
                    "firstUsed": "12:45:45 PM",
                    "id": 25165828,
                    "lastUsed": "12:45:50 PM",
                    "name": "Code",
                    "title": "Tracker.tsx - hrmware-tracker-v2 - Visual Studio Code",
                    # "session": [
                    #     {
                    #         "startTime": "12:45:45 PM",
                    #         "endTime": "12:45:46 PM",
                    #         "duration": 1
                    #     },
                    #     {
                    #         "startTime": "12:45:47 PM",
                    #         "endTime": "12:45:50 PM",
                    #         "duration": 3
                    #     }
                    # ],
                    "totalUsage": 5,
                    "isActive": False
                },
                {
                    "firstUsed": "12:45:46 PM",
                    "id": 71303169,
                    "lastUsed": "12:45:47 PM",
                    "name": "Mysql-workbench-bin",
                    "title": "MySQL Workbench",
                    # "session": [
                    #     {
                    #         "startTime": "12:45:46 PM",
                    #         "endTime": "12:45:47 PM",
                    #         "duration": 1
                    #     }
                    # ],
                    "totalUsage": 1,
                    "isActive": False
                },
                {
                    "firstUsed": "12:45:50 PM",
                    "id": 58720260,
                    "lastUsed": "12:45:52 PM",
                    "name": "Google-chrome",
                    "title": "Guides: Authentication | Next.js - Google Chrome",
                    # "session": [
                    #     {
                    #         "startTime": "12:45:50 PM",
                    #         "endTime": "12:45:52 PM",
                    #         "duration": 2
                    #     }
                    # ],
                    "totalUsage": 2,
                    "isActive": False
                }
            ]
        }

        response = c.post(url, data=data)
        self.assertEqual(response.status_code, 200, msg=json.dumps(response.json(), indent=4))

        self.assertEqual(ActivityLogs.objects.count(), len(data["allWindows"]))
        self.assertGreater(TrackerAppCategories.objects.count(), 0)
        
        tracker_apps = (
            TrackerApps.objects
            .filter(name__in=[data_item.get("name").strip().lower() for data_item in data["allWindows"]])
        )
        self.assertEqual(tracker_apps.count(), len(data["allWindows"]))
