from django.urls import path
from .views import FollowingActivityView, MyNotificationsView, MarkNotificationsReadView, inbox_page

app_name = "inbox"

urlpatterns = [
    path("following-activity/", FollowingActivityView.as_view(), name="following-activity"),
    # mark-read must come before notifications/ to avoid URL shadowing
    path("notifications/mark-read/", MarkNotificationsReadView.as_view(), name="mark-notifications-read"),
    path("notifications/", MyNotificationsView.as_view(), name="my-notifications"),
    path("", inbox_page, name="inbox-page"),
]