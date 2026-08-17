from django.contrib import admin

from .models import Stream


@admin.register(Stream)
class StreamAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "status", "started_at", "ended_at")
    list_filter = ("status",)
