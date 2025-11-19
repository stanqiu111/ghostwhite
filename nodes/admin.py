from django.contrib import admin
from .models import Node

@admin.register(Node)
class NodeAdmin(admin.ModelAdmin):
    list_display = ("host_url", "is_local", "is_active")
    list_filter = ("is_local", "is_active")
    actions = ["deactivate_nodes", "activate_nodes"]

    @admin.action(description="Deactivate selected nodes (stop sharing)")
    def deactivate_nodes(self, request, queryset):
        queryset.update(is_active=False)

    @admin.action(description="Activate selected nodes")
    def activate_nodes(self, request, queryset):
        queryset.update(is_active=True)