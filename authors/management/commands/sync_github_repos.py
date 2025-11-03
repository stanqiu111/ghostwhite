from django.core.management.base import BaseCommand
from authors.models import GitHubIntegration
from authors.github import sync_repos_for_author
from django.utils import timezone


class Command(BaseCommand):
    help = "Sync GitHub repos for all linked authors"

    def handle(self, *args, **options):
        total = 0
        integrations = GitHubIntegration.objects.select_related('author').all()
        for gi in integrations:
            author = gi.author
            created = sync_repos_for_author(author, gi.github_username, access_token=gi.access_token)
            # update last_synced_at
            gi.last_synced_at = timezone.now()
            gi.save(update_fields=['last_synced_at'])
            self.stdout.write(f"Synced {created} repos for {author.username}")
            total += created
        self.stdout.write(self.style.SUCCESS(f"Total created: {total}"))
