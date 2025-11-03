from django.contrib import admin
from .models import Author, Follow

admin.site.register(Follow)

@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ("username", "display_name", "approved", "is_active", "is_staff", "created_at")
    list_filter = ("approved", "is_active", "is_staff")
    search_fields = ("username", "display_name")
    readonly_fields = ("created_at", "updated_at")

    actions = ["approve_and_activate"]

    def approve_and_activate(self, request, queryset):
        updated_count = 0
        for author in queryset:
            if not author.approved or not author.is_active:
                author.approved = True
                author.is_active = True
                author.save(update_fields=["approved", "is_active"])
                updated_count += 1
        self.message_user(request, f"Approved and activated {updated_count} author(s).")
    approve_and_activate.short_description = "Approve selected authors (activate accounts)"
    
    def save_model(self, request, obj, form, change):
        if "password" in form.changed_data:
            obj.set_password(obj.password)
        super().save_model(request, obj, form, change)