from django.contrib import admin
from .models import Entry, Comment, EntryLike, CommentLike

# Register your models here.


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("id", "author", "entry", "content", "created_at")
    list_filter = ("created_at",)
    search_fields = ("content", "author__username")
    date_hierarchy = "created_at"
    readonly_fields = ("created_at",)

    # Enable bulk delete
    actions = ["delete_selected"]


@admin.register(Entry)
class EntryAdmin(admin.ModelAdmin):
    list_display = ("id", "author", "content_type", "visibility", "created_at")
    list_filter = ("content_type", "visibility", "created_at")
    search_fields = ("content", "author__username")


@admin.register(CommentLike)
class CommentLikeAdmin(admin.ModelAdmin):
    list_display = ("comment", "author", "created_at")
    list_filter = ("created_at",)


@admin.register(EntryLike)
class EntryLikeAdmin(admin.ModelAdmin):
    list_display = ("entry", "author", "created_at")
    list_filter = ("created_at",)
