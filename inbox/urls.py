from django.urls import path
from .views import FollowingActivityView

app_name = "inbox"

urlpatterns = [
    path("following-activity/", FollowingActivityView.as_view(), name="following-activity"),
]