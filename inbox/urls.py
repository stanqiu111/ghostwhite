from django.urls import path
from .views import FollowingActivityView, MyNotificationsView, inbox_page

app_name = "inbox"

urlpatterns = [
    path("following-activity/", FollowingActivityView.as_view(), name="following-activity"),
    # 홈/인박스에서 쓰는 새 엔드포인트
    path("notifications/", MyNotificationsView.as_view(),
         name="my-notifications"),
         
    path("", inbox_page, name="inbox-page"),
]