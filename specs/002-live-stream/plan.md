# Implementation Plan: Live Stream Feature

**Branch**: `002-live-stream` | **Date**: 2026-07-06 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-live-stream/spec.md`

## Summary

Add an MVP live-stream lifecycle to ÉTHÉRÉ: a new `streams` Django app with a federation-ready `Stream` model (FQID primary key mirroring `Entry`), server-rendered pages for stream list / detail / create, a small DRF API surface for lifecycle actions (create, list active, retrieve, end), owner-only end permission enforced server-side, and a placeholder player area on the detail page as the extension point for future media transport. No WebRTC, no media servers, no remote-node federation in this pass.

## Technical Context

**Language/Version**: Python 3.12 (pyenv), Django 5.1.1

**Primary Dependencies**: Django REST Framework, djangorestframework-simplejwt, drf-spectacular (already installed — no new dependencies)

**Storage**: SQLite locally / PostgreSQL on Heroku (existing setup); one new table `streams_stream`

**Testing**: Django `TestCase` + DRF `APIClient` against real SQLite test DB (constitution III — no mocked DB)

**Target Platform**: Existing Django web app (server-rendered templates + JS-enhanced pages), Heroku deploy with WhiteNoise static files

**Project Type**: Django monolith with per-feature apps (`authors`, `entries`, `inbox`, `nodes`) — new app `streams`

**Performance Goals**: Streams list renders in one query (select_related owner); no polling/websockets in MVP

**Constraints**: Dual auth (session + JWT) on all API views (constitution II); CSS in `streams/static/streams/` not inline (constitution VI); FQID `id` + UUID `serial` in API shapes (constitution VII)

**Scale/Scope**: Course-project scale (tens of users); 1 model, 4 API endpoints, 3 template pages, 1 nav entry point

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | Status | How the plan complies |
|---|-----------|--------|----------------------|
| I | Model-First Development | PASS | Task order: model + migration first, then serializers → views → urls → templates → CSS. Migration committed with model. |
| II | Dual Authentication | PASS | All DRF views keep default `JWTAuthentication` + add `SessionAuthentication`; template views check `request.user.is_authenticated`. No `authentication_classes` stripping. |
| III | No Mocked Database | PASS | All tests are `TestCase`/`APITestCase` hitting the real test SQLite DB, following `entries/tests.py` pattern (local `Node` created in `setUp`). |
| IV | Serializers Own Validation | PASS | Title required/bounded and "one live stream per owner" enforced in `StreamSerializer.validate()` / `create()`. Views stay thin. |
| V | Relationship State is Server-Side | PASS | `is_owner` computed in the Django template view and passed via context; the End button renders only when `is_owner`. JS enhances, doesn't decide. |
| VI | CSS in App Files | PASS | Page CSS in `streams/static/streams/streams.css`; no inline `style=` except dimensional image sizing. |
| VII | Public API Contract | PASS | API returns `type: "stream"`, `id` = full FQID URL, `serial` = UUID shorthand, consistent with Entry shapes. Visibility enforcement in views (list filters `status="live"`), not serializers. |
| VIII | Simplicity and Scope Control | PASS | No feature flags, no chat/viewers/recording, no federation shims — just a model whose PK scheme doesn't preclude federation. Placeholder player is a `<div>`, not a stub media pipeline. |

**Post-design re-check (after Phase 1)**: PASS — no violations introduced; Complexity Tracking left empty.

## Project Structure

### Documentation (this feature)

```text
specs/002-live-stream/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── streams-api.md   # Phase 1 output — HTTP contract for the streams API
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
streams/                          # NEW Django app
├── __init__.py
├── apps.py
├── admin.py                      # register Stream for staff visibility
├── models.py                     # Stream model (FQID pk, owner FK, lifecycle fields)
├── migrations/
│   └── 0001_initial.py
├── serializers.py                # StreamSerializer (validation + create/end logic)
├── views.py                      # DRF API views + template page views
├── urls.py                       # /api/streams/... routes
├── page_urls.py                  # /streams/... template page routes
├── templates/streams/
│   ├── stream_list.html          # active streams page
│   ├── stream_detail.html        # detail + placeholder player + owner End button
│   └── stream_create.html        # start-stream form
├── static/streams/
│   └── streams.css               # app-scoped styles matching ÉTHÉRÉ cards/header
└── tests.py                      # model + API + page tests (real SQLite)

ghostwhite/
├── settings.py                   # add "streams" to INSTALLED_APPS
└── urls.py                       # include streams API + page urls

utils/
└── fqid.py                       # add build_stream_fqid / extract_stream_id_from_fqid helpers

authors/templates/home.html       # header link/button to /streams/ (entry point)
```

**Structure Decision**: Mirror the `entries` app layout exactly (`urls.py` for `/api/`, `page_urls.py` for pages, app-scoped templates/static). This is the established per-feature pattern in this repo; a new `streams` app keeps the change isolated and reviewable.

## Design Decisions (from research.md)

1. **New `streams` app** over folding into `entries` — Stream is not an Entry (no content body, different lifecycle), and the repo convention is one app per concept.
2. **FQID `CharField` primary key** exactly like `Entry.id` (`{host}/api/authors/{author_serial}/streams/{uuid}`), assigned in `save()` via a new `build_stream_fqid()` in `utils/fqid.py`. This satisfies FR-010 (federation-ready identity) with zero federation code.
3. **Status as `CharField` choices** `live` / `ended` (+ `ended_at` timestamp) rather than deriving status from `ended_at is null` — explicit status matches `Entry.visibility` style and leaves room for future states (`scheduled`, `suspended`).
4. **"One live stream per owner" in serializer validation** (constitution IV) with a conditional `UniqueConstraint(fields=["owner"], condition=Q(status="live"))` as a DB-level backstop.
5. **End action = POST `/api/streams/<uuid>/end/`**, idempotent (ending an ended stream returns 200 with unchanged `ended_at`), owner-checked in the view via object comparison (403 for non-owner) — mirrors `EntryDeleteView`'s owner check.
6. **Placeholder player** is a styled `<div class="stream-player-placeholder">` in `stream_detail.html` with an HTML comment marking the extension point; no `<video>` element, no JS media code.
7. **Node FK now, unused logic later**: `Stream.node` FK to `nodes.Node` (like `Entry.node`), always the local node in MVP — this is the second half of federation-readiness.

## Complexity Tracking

*No constitution violations — table intentionally empty.*
