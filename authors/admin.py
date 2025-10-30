from django.contrib import admin
from .models import Author, Follow

admin.site.register(Follow)

@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ("username", "display_name", "approved", "is_active", "is_staff", "created_at")
    list_filter = ("approved", "is_active", "is_staff")
    search_fields = ("username", "display_name")

    actions = ["approve_and_activate"]

    def approve_and_activate(self, request, queryset):
        updated = queryset.update(approved=True, is_active=True)
        self.message_user(request, f"Approved and activated {updated} author(s).")
    approve_and_activate.short_description = "Approve selected authors (activate accounts)"