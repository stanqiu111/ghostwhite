from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from django.db import models
from django.utils import timezone
from .models import Entry
from .serializers import EntryRetrieveSerializer, EntryCreateSerializer
from django.shortcuts import render, get_object_or_404


class EntryListView(generics.ListAPIView):
    serializer_class = EntryRetrieveSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_authenticated and self.request.user.is_staff:
            # admin can see all entries, including the deleted ones
            return Entry.objects.all()

        queryset = Entry.objects.filter(deleted_at__isnull=True)

        return queryset


class EntryRetrieveView(generics.RetrieveAPIView):
    """Retrieve a single entry by ID"""

    serializer_class = EntryRetrieveSerializer
    permission_classes = [AllowAny]  # this allows anyone with link can view the entry

    def get_queryset(self):
        if self.request.user.is_authenticated and self.request.user.is_staff:
            #  if entry is deleted, admin can still see it
            return Entry.objects.all()

        return Entry.objects.filter(deleted_at__isnull=True)


class EntryCreateView(generics.CreateAPIView):
    serializer_class = EntryCreateSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(author=self.request.user, node=self.request.user.node)


class EntryUpdateView(generics.UpdateAPIView):
    serializer_class = EntryCreateSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Entry.objects.filter(deleted_at__isnull=True, author=self.request.user)

    def perform_update(self, serializer):
        if self.request.user != serializer.instance.author:
            raise PermissionDenied("Only the author can update their own entry.")
        serializer.save()


class EntryDeleteView(generics.DestroyAPIView):
    queryset = Entry.objects.filter(deleted_at__isnull=True)
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Entry.objects.filter(deleted_at__isnull=True, author=self.request.user)

    def perform_destroy(self, instance):
        if not self.request.user.is_staff and self.request.user != instance.author:
            # either author or admin can delete the entry
            raise PermissionDenied("Only the author can delete their own entry.")

        instance.soft_delete()


def view_entry_detail(request, pk):
    # initial entry detail page load
    entry = get_object_or_404(Entry, pk=pk)
    return render(request, "entries/entry_detail.html", {"entry": entry})
