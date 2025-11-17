"""
URL configuration for ghostwhite project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

from inbox.views import inbox_page
from .views import home_view
from django.conf import settings
from django.conf.urls.static import static

from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


urlpatterns = [
    path("", RedirectView.as_view(url="/home/", permanent=False)),
    path("home/", home_view, name="home"),
    path("admin/", admin.site.urls),
    path("api/authors/", include("authors.urls")),
    path("api/", include(("entries.urls", "entries"), namespace="entries_api")),
    path("", include(("entries.page_urls", "entries_pages"), namespace="entries_pages")),
    path("authors/", include(("authors.page_urls", "authors"), namespace="authors_pages")),
    path("api/inbox/", include("inbox.urls", namespace="inbox")),
    path("inbox/", inbox_page, name="inbox-page"),

    # API schema and docs
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]

# https://stackoverflow.com/questions/60052020/render-images-from-media-directory-django
if settings.DEBUG:
    urlpatterns+=static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)                                                    
