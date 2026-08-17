# Tasks: Live Stream Feature

**Input**: Design documents from `/specs/002-live-stream/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/streams-api.md, quickstart.md

**Tests**: Included — explicitly requested ("Add tests for model/view/API behavior"). Per constitution III, all tests hit the real SQLite test DB (no mocked DB).

**Organization**: Tasks grouped by user story so each story is an independently testable increment.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 = Start a stream, US2 = Discover & watch, US3 = End a stream (owner only)

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the `streams` app skeleton and register it with the project.

- [X] T001 Create the `streams` app skeleton: `streams/__init__.py`, `streams/apps.py` (`StreamsConfig`, `default_auto_field` matching existing apps), `streams/admin.py` (empty for now), `streams/migrations/__init__.py`, empty `streams/templates/streams/` and `streams/static/streams/` directories
- [X] T002 Register `"streams"` in `INSTALLED_APPS` in `ghostwhite/settings.py` (under the `# my apps` comment, after `"inbox"`)
- [X] T003 [P] Add FQID helpers to `utils/fqid.py`: `build_stream_fqid(author_id, stream_uuid)` returning `{host}api/authors/{author_serial}/streams/{stream_uuid}` and `extract_stream_id_from_fqid(fqid)` returning the UUID after `/streams/` — mirror `build_entry_fqid` / `extract_entry_id_from_fqid` exactly (note: import Stream lazily or take strings only; `utils/fqid.py` must not import `streams.models` at module level to avoid a circular import)

**Checkpoint**: `python manage.py check` passes with the empty app registered.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The `Stream` model, migration, and serializer that every user story depends on. Constitution I: model + migration land before any view/template code.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 Create `Stream` model in `streams/models.py` per `data-model.md`: FQID `CharField` pk assigned in `save()` via `build_stream_fqid`, `owner` FK → `authors.Author` (`related_name="streams"`), `node` FK → `nodes.Node` (`related_name="streams"`), `title` (max 200), `description` (blank), `status` choices live/ended default live, `started_at` auto_now_add, `ended_at` nullable; `Meta` with `ordering=["-started_at"]`, partial `UniqueConstraint(fields=["owner"], condition=Q(status="live"), name="unique_live_stream_per_owner")`, index on `(status, started_at)`; methods `end()` (idempotent), properties `serial`, `is_live`, `get_absolute_url()`
- [X] T005 Generate and apply the migration: `python manage.py makemigrations streams` → `streams/migrations/0001_initial.py`, then `python manage.py migrate`; verify the partial unique constraint exists in the SQL
- [X] T006 Create `StreamSerializer` in `streams/serializers.py` per `contracts/streams-api.md`: read shape `type="stream"`, `id` (FQID), `serial`, nested `owner` via existing `AuthorSerializer`, `title`, `description`, `status`, `startedAt`, `endedAt`, `webUrl`; write fields `title` (required, stripped, 1–200) + `description`; `validate()` rejects a second live stream per owner with "You already have a live stream."; `create()` sets `owner=request.user`, `node=local node`, `status="live"` (constitution IV: all validation/DB writes here, views stay thin)
- [X] T007 [P] Register `Stream` in `streams/admin.py` with `list_display = ("title", "owner", "status", "started_at", "ended_at")` and `list_filter = ("status",)`
- [X] T008 [P] Model tests in `streams/tests.py` (class `StreamModelTests`, real SQLite, local `Node` in `setUp` like `entries/tests.py`): FQID pk generated on save and contains `/streams/`; `serial` extracts the UUID; `end()` sets status/ended_at; `end()` twice leaves `ended_at` unchanged; second live stream for same owner raises `IntegrityError` at DB level

**Checkpoint**: `python manage.py test streams` passes model tests — user story phases can now begin.

---

## Phase 3: User Story 1 — Start a stream (Priority: P1) 🎯 MVP

**Goal**: A logged-in user submits a title/description and lands on their live stream's detail page.

**Independent Test**: Log in, open `/streams/create/`, submit a title, verify redirect to a detail page showing status Live, correct owner, and start time (quickstart S1).

### Tests for User Story 1

- [X] T009 [US1] API + page tests in `streams/tests.py` (class `StreamCreateTests`): `POST /api/streams/` with valid title → 201 with `type/id/serial/status="live"` shape; blank title → 400; second stream while live → 400 with "already have a live stream"; unauthenticated → 401; JWT-auth'd POST also succeeds (constitution II); `GET /streams/create/` unauthenticated → redirect to login; authenticated form POST → redirect to detail page

### Implementation for User Story 1

- [X] T010 [US1] Implement `StreamCreateAPIView` (`generics.CreateAPIView`, `permission_classes=[IsAuthenticated]`, session + JWT auth) in `streams/views.py`, delegating everything to `StreamSerializer`
- [X] T011 [US1] Implement `stream_create_page` template view in `streams/views.py`: GET renders the form; POST validates via `StreamSerializer` and redirects to the new stream's detail page on success, re-renders with errors on failure; unauthenticated → redirect `authors_pages:auth_page`
- [X] T012 [US1] Create `streams/urls.py` (`app_name="streams"`; route `streams/` POST→create wired in the API view) and `streams/page_urls.py` (`streams/create/` → `stream_create_page`); include both in `ghostwhite/urls.py`: `path("api/", include(("streams.urls", "streams"), namespace="streams_api"))` and `path("", include(("streams.page_urls", "streams_pages"), namespace="streams_pages"))`
- [X] T013 [US1] Create `streams/templates/streams/stream_create.html`: ÉTHÉRÉ header (match `entries/templates/entries/create_entry.html` structure), card-styled form with title input + description textarea + CSRF + inline error display, submit "Go live"
- [X] T014 [US1] Start `streams/static/streams/streams.css` with form/card styles scoped under `.streams-page` (constitution VI — no inline styles); link it from `stream_create.html`

**Checkpoint**: Quickstart S1 passes end-to-end — a user can go live. This alone is a deployable MVP.

---

## Phase 4: User Story 2 — Discover and watch active streams (Priority: P1)

**Goal**: Logged-in users see all live streams on `/streams/` and can open a detail page with streamer, title, description, status, and a placeholder player.

**Independent Test**: With one live stream, log in as another user, see it listed on `/streams/`, click through, verify detail content and player placeholder (quickstart S2).

### Tests for User Story 2

- [X] T015 [US2] API + page tests in `streams/tests.py` (class `StreamListDetailTests`): `GET /api/streams/` returns only live streams (create one live + one ended, assert one item); `GET /api/streams/<serial>/` → 200 for live and ended, 404 for unknown UUID; both endpoints 401 unauthenticated; `GET /streams/` and `GET /streams/<serial>/` redirect to login when logged out and render (200) when logged in

### Implementation for User Story 2

- [X] T016 [US2] Implement `StreamListAPIView` (live-only queryset `Stream.objects.filter(status="live").select_related("owner")`, response `{"type":"streams","items":[...]}`) and `StreamRetrieveAPIView` (any status, lookup by serial → resolve FQID pk) in `streams/views.py`; add routes `streams/` GET and `streams/<uuid:pk>/` in `streams/urls.py`
- [X] T017 [US2] Implement `stream_list_page` and `stream_detail_page` template views in `streams/views.py`: list passes live streams via context; detail passes `stream` + `is_owner` (constitution V) and 404s on unknown serial; both redirect unauthenticated users to login; add `streams/` and `streams/<uuid:pk>/` to `streams/page_urls.py`
- [X] T018 [P] [US2] Create `streams/templates/streams/stream_list.html`: grid of stream cards (streamer avatar/name, title, "LIVE" badge, started-at time, link to detail), empty state "No one is live right now", "Go live" button linking to create page
- [X] T019 [P] [US2] Create `streams/templates/streams/stream_detail.html`: streamer identity block, title, description, status badge (Live/Ended), start time, placeholder player `<div class="stream-player-placeholder" data-stream-serial="{{ stream.serial }}">` with comment `<!-- EXTENSION POINT: media player mounts here -->`
- [X] T020 [US2] Extend `streams/static/streams/streams.css` with list-grid, card, LIVE badge, and player-placeholder styles consistent with `static/css/main.css` card look
- [X] T021 [US2] Add a "Live" nav button to the header actions in `authors/templates/home.html` linking to `/streams/` (styled like the existing header buttons, CSS class in `streams.css` or `main.css`, no inline styles)

**Checkpoint**: Quickstart S2 passes — discovery + viewing loop complete.

---

## Phase 5: User Story 3 — End a stream, owner only (Priority: P1)

**Goal**: The owner (and only the owner) ends their stream; ended streams leave the active list but stay reachable.

**Independent Test**: Owner sees and uses End button → status flips to Ended and stream leaves `/streams/`; non-owner sees no button and direct POST returns 403 (quickstart S3).

### Tests for User Story 3

- [X] T022 [US3] API + page tests in `streams/tests.py` (class `StreamEndTests`): owner `POST /api/streams/<serial>/end/` → 200, status ended, `endedAt` set; repeat POST → 200 with unchanged `endedAt` (idempotent); non-owner POST → 403 and stream stays live; unauthenticated → 401; ended stream absent from `GET /api/streams/`; detail page HTML contains End button for owner and not for non-owner; ended detail page shows ended status and both times

### Implementation for User Story 3

- [X] T023 [US3] Implement `StreamEndAPIView` (POST) in `streams/views.py`: load by serial, 403 "Only the stream owner can end this stream." unless `request.user == stream.owner`, call `stream.end()`, return serialized stream; add route `streams/<uuid:pk>/end/` to `streams/urls.py`
- [X] T024 [US3] Wire the End button in `streams/templates/streams/stream_detail.html`: rendered only when `is_owner and stream.is_live` (server-side context, constitution V); small JS handler POSTs to `/api/streams/<serial>/end/` with CSRF/JWT headers (follow the existing dual-auth fetch pattern from `entry_detail.html`) and reloads on success; show Ended badge + end time when stream is over
- [X] T025 [US3] Style the End button and Ended state in `streams/static/streams/streams.css` (destructive-action styling consistent with the existing Delete button look)

**Checkpoint**: All three stories pass quickstart S1–S3 independently.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T026 Run the full regression suite: `python manage.py test` — all pre-existing tests must still pass (SC-005); fix any breakage caused by this feature
- [X] T027 Run `python manage.py check` and `python manage.py makemigrations --check --dry-run` (no missing migrations); run `python manage.py collectstatic --noinput` to confirm WhiteNoise picks up `streams/streams.css`
- [X] T028 Execute `specs/002-live-stream/quickstart.md` manual walkthrough (S1–S3 + regression sweep) in a real browser with two users; verify empty-state, long-description rendering, and 404 on unknown stream URL edge cases from spec.md

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none — start immediately (T003 parallel with T001–T002)
- **Foundational (Phase 2)**: needs Phase 1; **blocks all user stories** (T004 → T005 → T006; T007, T008 parallel after T005)
- **US1 (Phase 3)**: needs Phase 2. T009 (tests first) → T010–T012 → T013–T014
- **US2 (Phase 4)**: needs Phase 2; shares `streams/views.py`/`urls.py` files with US1, so run after US1 (same-file conflicts), though logically independent
- **US3 (Phase 5)**: needs Phase 2; End-button task T024 touches `stream_detail.html` created in T019, so run after US2
- **Polish (Phase 6)**: after all stories

### Parallel Opportunities

- Phase 1: T003 alongside T001/T002
- Phase 2: T007 + T008 together after T005/T006
- Phase 4: T018 + T019 (different template files) together
- Test-writing tasks (T009, T015, T022) can each be written in parallel with reading their contract, before their story's implementation

### Parallel Example: User Story 2

```bash
# After T016–T017 land, launch template work together:
Task: "Create streams/templates/streams/stream_list.html"    # T018
Task: "Create streams/templates/streams/stream_detail.html"  # T019
```

---

## Implementation Strategy

**MVP first**: Phases 1–3 alone ship a working "go live" flow (quickstart S1). Stop and validate there.

**Incremental delivery**: Phase 4 completes the discovery/viewing loop (S2); Phase 5 completes the lifecycle with owner-only end (S3); Phase 6 locks in regression safety (SC-005). Each checkpoint is independently demonstrable.

**Notes**:

- Tests are written first within each story and must fail before implementation (constitution III: real SQLite, no DB mocks).
- Commit after each phase checkpoint; migration `0001_initial.py` commits together with `models.py` (constitution I).
- Total: 28 tasks — Setup 3, Foundational 5, US1 6, US2 7, US3 4, Polish 3.
