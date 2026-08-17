# Research: Live Stream Feature

**Date**: 2026-07-06 | **Plan**: [plan.md](plan.md)

No NEEDS CLARIFICATION markers remained in the Technical Context; research focused on aligning each design choice with existing repo patterns.

## R1 — New app vs. extending `entries`

- **Decision**: Create a new `streams` Django app.
- **Rationale**: A stream has no content body, a different lifecycle (live→ended vs. create/edit/soft-delete), and different list semantics (only-active). The repo already isolates concepts per app (`authors`, `entries`, `inbox`, `nodes`), and the user explicitly suggested a `streams` app. Registration cost is two lines (`INSTALLED_APPS`, `urls.py` include).
- **Alternatives considered**: Adding a `Stream` model inside `entries` — rejected: couples unrelated lifecycles, bloats an already 380-line `views.py`, and violates the repo's app-per-concept convention.

## R2 — Federation-ready identity

- **Decision**: `id = CharField(max_length=512, primary_key=True)` holding an FQID URL `{host}/api/authors/{author_serial}/streams/{stream_uuid}`, assigned in `Stream.save()` via a new `build_stream_fqid()` helper in `utils/fqid.py`, alongside a `node` FK to `nodes.Node` (local node in MVP).
- **Rationale**: This is byte-for-byte the `Entry` pattern (`entries/models.py` `save()` + `utils/fqid.py build_entry_fqid`). Existing remote-node code addresses objects by FQID; reusing the scheme means federation later requires no identifier migration (FR-010). Constitution VII requires `id` = FQID and `serial` = UUID in API shapes.
- **Alternatives considered**: Plain `UUIDField` pk with FQID computed at serialization time — rejected: diverges from Entry, and remote-origin streams could not be stored under their origin FQID later.

## R3 — Status representation

- **Decision**: `status = CharField(choices=[("live","Live"),("ended","Ended")], default="live")` plus `started_at` (auto) and nullable `ended_at`.
- **Rationale**: Matches spec vocabulary (status is a first-class attribute), matches `Entry.visibility` choices style, and is directly filterable (`Stream.objects.filter(status="live")`). Leaves room for future states without schema change.
- **Alternatives considered**: Deriving status from `ended_at IS NULL` — rejected: works today but makes future states (scheduled, suspended) impossible without another migration, and reads worse in templates/tests.

## R4 — Enforcing one live stream per user

- **Decision**: Serializer-level check in `StreamSerializer.validate()` (raises friendly 400) plus DB-level `UniqueConstraint(fields=["owner"], condition=Q(status="live"), name="unique_live_stream_per_owner")` as a race-condition backstop.
- **Rationale**: Constitution IV places validation in serializers; the conditional unique constraint is the same defensive pattern already used in `entries` (`unique_author_source_sourceid`). SQLite and Postgres both support partial unique indexes.
- **Alternatives considered**: View-level check only — rejected (constitution IV); constraint only — rejected (IntegrityError → ugly 500 instead of a clear validation message).

## R5 — End-stream endpoint shape and permission

- **Decision**: `POST /api/streams/<uuid:pk>/end/` (session or JWT auth). View loads the stream, returns 403 unless `request.user == stream.owner`, then delegates to serializer/model `end()` which sets `status="ended"`, `ended_at=now()` only if still live (idempotent).
- **Rationale**: Mirrors `EntryDeleteView`'s URL style (`entries/<uuid:pk>/delete/`) and its owner check. POST (not DELETE) because the stream is not removed — it transitions state. Idempotency satisfies the double-submit edge case (FR-011).
- **Alternatives considered**: DRF custom permission class `IsOwner` — fine, but the repo's existing owner checks are inline object comparisons; consistency wins (constitution VIII). PATCH of `status` field — rejected: allows arbitrary status writes, larger validation surface.

## R6 — Template pages and auth

- **Decision**: Three server-rendered pages under `/streams/` via `page_urls.py` (`stream_list`, `stream_detail`, `stream_create`), each redirecting unauthenticated users to `authors_pages:auth_page` — same guard as `home_view`. Detail view passes `is_owner` in context (constitution V).
- **Rationale**: Matches `entries/page_urls.py` split of API vs. page routes and the existing redirect-to-login convention.
- **Alternatives considered**: `login_required` decorator — behaviorally equal, but existing views use the explicit `request.user.is_authenticated` check + named-URL redirect; keep one idiom.

## R7 — Placeholder player / extension points

- **Decision**: A styled `<div>` region on the detail page labeled "Live stream player coming soon", with an HTML comment `<!-- EXTENSION POINT: media player mounts here; stream identity available as data-stream-serial -->`. No `<video>`, no media JS.
- **Rationale**: The spec explicitly defers media transport. A dumb div with a documented mount point and the stream serial in a data attribute is the entire contract a future WebRTC/HLS integration needs.
- **Alternatives considered**: Static `<video>` tag with poster — rejected: implies playable media that doesn't exist; adds dead UI.

## R8 — Entry point in existing UI

- **Decision**: One "Live" link/button in the `home.html` header actions (next to Add Entry / notifications), pointing to `/streams/`.
- **Rationale**: Smallest discoverable entry point; the header is where global nav already lives. Feed/profile surfacing is explicitly out of scope (spec Assumptions).
- **Alternatives considered**: Sidebar card of live streams on home — rejected for MVP scope (constitution VIII).
