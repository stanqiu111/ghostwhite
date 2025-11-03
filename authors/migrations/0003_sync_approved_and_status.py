# Migration to sync approved and status fields for existing Follow records
from django.db import migrations


def sync_approved_and_status(apps, schema_editor):
    """
    Ensure approved and status fields are in sync for existing Follow records.
    - If approved=True, set status='accepted'
    - If approved=False and status='pending', keep as is
    """
    Follow = apps.get_model('authors', 'Follow')

    # Update all records where approved=True but status is not 'accepted'
    Follow.objects.filter(approved=True).exclude(status='accepted').update(status='accepted')

    # Update all records where approved=False but status is 'accepted' (shouldn't happen, but just in case)
    Follow.objects.filter(approved=False, status='accepted').update(status='pending')


class Migration(migrations.Migration):

    dependencies = [
        ('authors', '0002_follow'),
    ]

    operations = [
        migrations.RunPython(sync_approved_and_status, reverse_code=migrations.RunPython.noop),
    ]
