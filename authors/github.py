import logging

import requests
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from entries.models import Entry

logger = logging.getLogger(__name__)

PERSONAL_EVENTS_URL = "https://api.github.com/users/{username}/events/public"


def auth_headers(token=None):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "ghostwhite-github-importer"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers

def map_event_to_entry(event, author):
    """Returns a dict of Entry fields for the given event and local author."""
    etype = event.get("type")
    repo = event.get("repo", {}).get("name", "")
    event_id = str(event.get("id"))
    created_at_str = event.get("created_at")
    created_at = parse_datetime(created_at_str) if created_at_str else None
    if created_at is None:
        created_at = timezone.now()

    body_lines = []
    source_url = None
    actor = event.get("actor") or {}
    display_login = actor.get("login") or event.get("display_login") or ""
    title = f"{display_login} "

    if etype == "PushEvent":
        commits = event.get("payload", {}).get("commits", [])
        n = len(commits)
        title += f"pushed {n} commit{'s' if n != 1 else ''} to {repo}"
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
        title += f"{action} PR: {pr_title} — {repo}"
        body_lines.append(pr.get("body") or "")
        source_url = pr_html_url

    elif etype == "WatchEvent":
        title += f"starred ⭐ {repo}"
        body_lines.append("Started watching this repository")
        source_url = f"https://github.com/{repo}"

    elif etype == "CreateEvent":
        ref_type = event.get("payload", {}).get("ref_type", "")
        ref = event.get("payload", {}).get("ref", "")
        title += f"created {ref_type} {ref} in {repo}"
        source_url = f"https://github.com/{repo}"

    else:
        source_url = f"https://github.com/{repo}"

    content_lines = [f"### {title.strip()}", ""]
    content_lines.extend(l for l in body_lines if l)
    if source_url:
        content_lines.extend(["", f"[View on GitHub]({source_url})"])

    content = "\n".join(line for line in content_lines if line is not None)

    return {
        "content": content,
        "content_type": "text/markdown",
        "visibility": "public",
        "author": author,
        "source": "github",
        "source_id": event_id,
        "source_url": source_url,
        "created_at": created_at or timezone.now(),
    }


def sync_github_events(author, github_username, access_token=None, *, limit=50):
    """Fetch public events for the user and create Entry rows. Returns processed/created counts."""
    if not github_username:
        return {"processed": 0, "created": 0, "errors": False}

    headers = auth_headers(access_token)
    events = []
    errors = False

    url = PERSONAL_EVENTS_URL.format(username=github_username)
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        events = resp.json()
        logger.info(f"events: {events}")
    except Exception as exc:
        errors = True
        logger.warning("Failed to fetch events for %s: %s", github_username, exc)
        events = []

    processed = 0
    created = 0
    seen_event_ids = set()
    max_events = limit if limit and limit > 0 else len(events)

    for event in events[:max_events]:
        processed += 1
        event_id = str(event.get("id"))
        if not event_id or event_id in seen_event_ids:
            continue
        seen_event_ids.add(event_id)

        if Entry.objects.filter(source="github", source_id=event_id).exists():
            continue

        entry_data = map_event_to_entry(event, author)
        e = Entry.objects.create(
            author=entry_data["author"],
            content=entry_data["content"],
            content_type=entry_data["content_type"],
            visibility=entry_data["visibility"],
            node=entry_data["author"].node,
            source=entry_data["source"],
            source_id=entry_data["source_id"],
            source_url=entry_data["source_url"],
        )
        try:
            e.created_at = entry_data["created_at"]
            e.save(update_fields=["created_at"])
        except Exception:
            pass
        created += 1

    return {"processed": processed, "created": created, "errors": errors}