from typing import Any
import uuid

from rest_framework.views import APIView
from rest_framework.response import Response

from .models import ActivityLogs, TrackerApps, TrackerAppCategoriesMapping, TrackerAppCategories


class GetTrackerData(APIView):
    def post(self, request):
        """API to receive HRMWARE Tracker data"""

        # with open("test.json", "w") as file:
        #     file.write(json.dumps(request.data, indent=4))
        # return Response(data={"message": "Successfully retrieved stuff!"}, status=200)

        try:
            data_rows: list[dict[str, Any]] = request.data.get("allWindows")
            response = {}

            for data in data_rows:
                start_timestamp = data.get("firstUsed")
                end_timestamp = data.get("lastUsed")
                duration = data.get("totalUsage")
                is_active = data.get("isActive")
                window_title = data.get("title")
                app = data.get("name", None)
                if isinstance(app, str):
                    app = app.strip().lower()

                log_id = uuid.uuid4()
                tracker_app = TrackerApps.objects.filter(name=app).first()
                if tracker_app is None:
                    tracker_app = TrackerApps.objects.create(
                        uuid=uuid.uuid4(),
                        name=app
                    )

                tracker_app_category = (
                    TrackerAppCategoriesMapping.objects
                    .filter(app=tracker_app.name)
                    .first()
                )
                if tracker_app_category is None:
                    msg = "Unknown app encountered, please set productivity status for it. Currently setting it to neutral"
                    response["warning"] = msg

                    tracker_app_category = (
                        TrackerAppCategoriesMapping.objects
                        .create(
                            app=tracker_app,
                            category=
                        )
                    )



        except Exception as e:
            return Response(message=str(e))
