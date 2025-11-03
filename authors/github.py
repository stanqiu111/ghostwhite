try:
    import requests
except Exception:
    requests = None

import logging
from django.utils import timezone
from entries.models import Entry

logger = logging.getLogger(__name__)

GITHUB_API_USER_REPOS = "https://api.github.com/users/{username}/repos"


def fetch_user_repos(github_username, access_token=None):
    """Fetch public repos for a GitHub username. If access_token is provided, include it to increase rate limits.

    If the `requests` package is not available in the running environment this function
    will raise a clear RuntimeError so Django doesn't fail to import the module at startup.
    """
    if requests is None:
        raise RuntimeError(
            "The 'requests' package is required to fetch GitHub data. Install it with: pip install requests"
        )

    headers = {"Accept": "application/vnd.github+json"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    url = GITHUB_API_USER_REPOS.format(username=github_username)
    resp = requests.get(url, headers=headers, params={"per_page": 100}, timeout=10)
    resp.raise_for_status()
    return resp.json()


def sync_repos_for_author(author, github_username, access_token=None):
    """Fetch repos and create Entry objects for each repo. Skips duplicates by (source, source_url).
    Returns number of created entries."""
    created = 0
    try:
        repos = fetch_user_repos(github_username, access_token=access_token)
    except Exception as e:
        logger.error(f"Failed to fetch repos for {github_username}: {e}", exc_info=True)
        return 0

    for repo in repos:
        repo_url = repo.get("html_url")
        if not repo_url:
            continue
        # Skip if already created for this source/url
        if Entry.objects.filter(source="github", source_url=repo_url).exists():
            continue

        name = repo.get("full_name") or repo.get("name")
        description = repo.get("description") or ""
        language = repo.get("language") or ""
        stars = repo.get("stargazers_count") or 0

        # Build markdown content
        content_lines = [f"**{name}**"]
        if description:
            content_lines.append("")
            content_lines.append(description)
        content_lines.append("")
        meta_parts = []
        if language:
            meta_parts.append(f"Language: {language}")
        meta_parts.append(f"Stars: {stars}")
        content_lines.append(" · ".join(meta_parts))
        content_lines.append("")
        content_lines.append(f"[View on GitHub]({repo_url})")
        content = "\n".join(content_lines)

        # create entry
        Entry.objects.create(
            author=author,
            content=content,
            content_type="markdown",
            visibility="public",
            node=author.node,
            source="github",
            source_url=repo_url,
        )
        created += 1

    # Optionally update last_synced_at in a GitHubIntegration record (done by caller)
    return created
