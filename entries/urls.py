from django.urls import path
from . import views
from django.views.generic import TemplateView

app_name = "entries"
urlpatterns = [
    path("entries/", views.EntryListView.as_view(), name="entry-list"),
    path("entries/create/", views.EntryCreateView.as_view(), name="entry-create"),
    path("entries/<uuid:pk>/", views.EntryRetrieveView.as_view(), name="entry-detail"), 
    path("entries/<uuid:pk>/update/", views.EntryUpdateView.as_view(), name="entry-update"),
    path("entries/<uuid:pk>/delete/", views.EntryDeleteView.as_view(), name="entry-delete"),
    
    path("entries/<uuid:pk>/addcomment/", views.add_comment, name="add_comment"),
    path("entries/<uuid:pk>/like/", views.like_entry, name="like_entry"),
    path("entries/<uuid:pk>/comments/<int:comment_id>/like/", views.like_comment, name="like_comment"),
    
    # HTML pages for manual testing
    path("entries/create/page/",
         TemplateView.as_view(template_name="entries/create.html"),
         name="entry-create-page"),
    path("entries/<uuid:pk>/page/",
         views.entry_detail_page,
         name="detail"),

]
