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
from .views import home_view
from django.conf import settings
from django.conf.urls.static import static 
from django.views.generic import RedirectView
from .views import home_view


urlpatterns = [
    path("", RedirectView.as_view(url="/api/authors/auth/", permanent=False)),
    path("home/", home_view, name="home"),
    path("admin/", admin.site.urls),
    path( "", RedirectView.as_view(url="/authors/auth/", permanent=False), name="home"),
    path("api/authors/", include(("authors.urls", "authors_api"), namespace="authors_api")),
    path("home/", home_view, name="home"),
    path("authors/", include(("authors.page_urls", "authors"), namespace="authors_pages")),

]

#for uploding media files
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)