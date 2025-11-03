# entries/management/commands/sync_github_activity.py
import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
import requests
from entries.models import Entry
from authors.models import GitHubIntegration
from dateutil import parser as dateparser

logger = logging.getLogger(__name__)
GITHUB_EVENTS_URL = "https://api.github.com/users/{username}/events/public"

def auth_headers(token=None):
    headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "ghostwhite-github-importer"}
    if token:
        headers["Authorization"] = f"token {token}"
    return headers

def map_event_to_entry(event, author):
    """
    Returns a dict of Entry fields for the given event and local author.
    """
    etype = event.get("type")
    repo = event.get("repo", {}).get("name", "")
    event_id = str(event.get("id"))
    created_at_str = event.get("created_at")
    created_at = None
    if created_at_str:
        try:
            created_at = dateparser.parse(created_at_str)
        except Exception:
            created_at = timezone.now()

    title = f"{etype} in {repo}"
    body_lines = []
    source_url = None

    if etype == "PushEvent":
        commits = event.get("payload", {}).get("commits", [])
        n = len(commits)
        title = f"Pushed {n} commit{'s' if n != 1 else ''} to {repo}"
        for c in commits:
            sha = c.get("sha", "")[:7]
            msg = c.get("message", "")
            body_lines.append(f"- {sha} — {msg}")
        source_url = f"https://github.com/{repo}"

    elif etype == "PullRequestEvent":
        action = event.get("payload", {}).get("action", "")
        pr = event.get("payload", {}).get("pull_request", {})
        pr_title = pr.get("title", "")
        pr_html_url = pr.get("html_url")
        title = f"{action.capitalize()} PR: {pr_title} — {repo}"
        body_lines.append(pr.get("body") or "")
        source_url = pr_html_url

    elif etype == "CreateEvent":
        ref_type = event.get("payload", {}).get("ref_type", "")
        ref = event.get("payload", {}).get("ref", "")
        title = f"Created {ref_type} {ref} in {repo}"
        source_url = f"https://github.com/{repo}"

    else:
        # Fallback
        title = f"{etype} in {repo}"
        source_url = f"https://github.com/{repo}"

    return {
        "title": title,
        "body": "\n".join(l for l in body_lines if l),
        "author": author,
        "public": True,
        "source": "github",
        "source_id": event_id,
        "source_url": source_url,
        "created_at": created_at or timezone.now(),
    }

class Command(BaseCommand):
    help = "Sync public GitHub events for all GitHubIntegration records and create entries."

    def add_arguments(self, parser):
        parser.add_argument("--author", help="Restrict sync to a single local author username", default=None)
        parser.add_argument("--limit", type=int, help="Max events to process per author", default=50)

    def handle(self, *args, **options):
        # iterate integrations
        integrations = GitHubIntegration.objects.all()
        if options["author"]:
            integrations = integrations.filter(author__username=options["author"])

        total_created = 0
        for integration in integrations:
            username = integration.github_username
            token = integration.access_token
            self.stdout.write(f"Syncing GitHub events for {integration.author} ({username})...")

            headers = auth_headers(token)
            try:
                resp = requests.get(GITHUB_EVENTS_URL.format(username=username), headers=headers, timeout=10)
                resp.raise_for_status()
            except Exception as exc:
                self.stderr.write(f"Failed to fetch events for {username}: {exc}")
                logger.exception("GitHub fetch failed for %s", username)
                continue

            events = resp.json()
            created = 0
            processed = 0
            for event in events[: options["limit"]]:
                processed += 1
                event_id = str(event.get("id"))
                if not event_id:
                    continue
                # Skip already imported
                if Entry.objects.filter(source="github", source_id=event_id).exists():
                    continue

                entry_data = map_event_to_entry(event, integration.author)
                # create entry (respect your model fields)
                e = Entry.objects.create(
                    title=entry_data["title"],
                    body=entry_data["body"],
                    author=entry_data["author"],
                    public=entry_data["public"],
                    source=entry_data["source"],
                    source_id=entry_data["source_id"],
                    source_url=entry_data["source_url"],
                )
                # set created_at if not auto_now_add
                try:
                    e.created_at = entry_data["created_at"]
                    e.save(update_fields=["created_at"])
                except Exception:
                    # ignore if created_at is auto
                    pass

                created += 1

            integration.last_synced_at = timezone.now()
            integration.save(update_fields=["last_synced_at"])
            self.stdout.write(self.style.SUCCESS(f"{integration.author}: processed={processed} created={created}"))
            total_created += created

        self.stdout.write(self.style.SUCCESS(f"Sync complete. Total new entries created: {total_created}"))
