# Tasks: Stream Video Controls and Bullet Curtain

**Input**: Design documents from `/specs/004-stream-video-controls/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/bullets-api.md, quickstart.md

**Tests**: Included — spec FR-012 requires automated tests for bullet creation, permissions, ended-stream rejection, and sanitization. Per constitution III, all tests hit the real SQLite test DB. Overlay animation, controls, and multi-watcher visuals are validated by the quickstart manual walkthrough.

**Organization**: Tasks grouped by user story. US1 (send & display) carries the whole client stack (`bullets.js`, template, CSS); US2 (streamer sees) is a thin owner-side slice over it; US3–US5 are additive controls.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 = viewer sends bullet, US2 = streamer sees bullets, US3 = curtain toggle, US4 = volume/mute, US5 = display modes

## Phase 1: Setup

**Purpose**: No new apps/deps (plan: zero new dependencies). Confirmation only.

- [X] T001 Verify no dependency/deploy changes are required: `Procfile`, `requirements.txt`, `ghostwhite/settings.py` untouched by this feature; note confirmation here when checking off
  - ✅ Confirmed 2026-07-06: feature touched only `streams/` (models, migration 0003, serializers, views, urls, tests, template, bullets.js, player_controls.js, streams.css) + WORKFLOW.md. Zero dependency/deploy changes.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: `StreamBulletMessage` model → migration → serializer → endpoint → tests (constitution I order). US1–US3 all depend on this; US4/US5 don't but share the template region.

**⚠️ CRITICAL**: No user story work before this phase completes.

- [X] T002 Add `StreamBulletMessage` model to `streams/models.py` per `data-model.md`: `stream` FK (`related_name="bullets"`), `sender` FK (`related_name="+"`), `content` CharField(120), `created_at` auto_now_add; `Meta` ordering `["id"]`, index `("stream", "id")` named `bullet_cursor_idx`
- [X] T003 Generate and apply `streams/migrations/0003_streambulletmessage.py` (`makemigrations streams` + `migrate`); confirm index in `sqlmigrate` output
- [X] T004 Add `StreamBulletMessageSerializer` to `streams/serializers.py` per contract §3: `content` strip → non-empty → ≤120 (constitution IV); nested sender `{serial, displayName}` read-only; `stream`/`sender` injected via context in `create()`, never client-writable; response fields `type`("bullet")/`id`/`content`/`sender`/`created_at`
- [X] T005 Add `StreamBulletView` (POST + GET on one URL) to `streams/views.py` per `contracts/bullets-api.md`: dual `[JWTAuthentication, SessionAuthentication]` + `IsAuthenticated`; 404 unknown stream, **410 ended stream (both verbs, checked first)**; GET modes `?after=<int>` (id-cursor, ≤50 rows, ascending, non-consuming, returns `{"type":"bullets","items":[...],"cursor":N}`) and `?latest=1` (the 30 most recent bullets ascending + current max id as cursor — locked bootstrap decision); invalid/missing params → 400; register `streams/<uuid:pk>/bullets/` in `streams/urls.py`
- [X] T006 Foundational bullet tests in `streams/tests.py` (class `StreamBulletMessageAPITests`, reuse `StreamTestBase`): authenticated POST → 201 echoing content verbatim; owner can also POST; unauthenticated POST/GET → 401/403; ended stream POST/GET → 410; unknown stream → 404; empty/whitespace content → 400; >120 chars → 400; exactly 120 chars → 201; **XSS payload `<script>alert(1)</script>` stored verbatim in DB and returned as identical JSON string (no encoding mutation)** (FR-012/SC-002 server half); cursor polling: `latest=1` returns the 30 most recent ascending + max-id cursor (older rows excluded); `after=<id>` returns only newer rows ascending capped at 50; two watchers polling independently both receive the same message (non-consuming); missing/invalid `after` → 400; JWT-auth'd POST works (constitution II); ending a stream does NOT delete bullets (contrast with signals purge)

**Checkpoint**: `python manage.py test streams` green — bullet API proven; client work can begin.

---

## Phase 3: User Story 1 — Viewer sends a bullet that flies across the stream (Priority: P1) 🎯 MVP

**Goal**: Send form under the player; messages animate across every watcher's player ≤5 s; XSS-inert rendering; controls never blocked.

**Independent Test**: Quickstart S1 — two browsers, message sent in one animates in both; hostile markup renders as text.

- [X] T007 [US1] Create `streams/static/streams/bullets.js` per contract §5, fully isolated from `screenshare.js`: copy the CSRF + optional-JWT header helper pattern from `signaling.js`; `BulletCurtain` class — bootstrap via `GET ?latest=1` (backfill up to 30 recent through the normal display pipeline), poll `?after=<cursor>` every 1.5 s while page open; render each item as a `<span class="bullet-msg">` using **`textContent` only**, 6 lanes desktop / 3 on narrow viewports via `--lane` custom property (least-recently-used assignment, drop from display when all lanes busy), CSS animation right→left with duration scaled by content length, remove node on `animationend`; send form submit → POST, on 201 clear input, on 400 show serializer message inline, client-side throttle ≥1 s between sends; on 410 stop polling and disable input with ended hint (do NOT touch player state machine)
- [X] T008 [US1] Update `streams/templates/streams/stream_detail.html`: `#bulletOverlay` div inside `#streamPlayer` (before the fullscreen button); bullet send form (`#bulletForm` with `#bulletInput` maxlength=120 + send button + `#bulletError`) under the player for all logged-in users, disabled server-side when stream ended; load `bullets.js`; instantiate `BulletCurtain` for live streams (all roles)
- [X] T009 [P] [US1] Add overlay styles to `streams/static/streams/streams.css`: `#bulletOverlay` absolute inset-0, `pointer-events: none`, `overflow: hidden`, above videos/below nothing clickable; `.bullet-msg` lane positioning via `top: calc(var(--lane) * …)`, `white-space: nowrap`, text shadow for readability, `transform: translateX` keyframes; send form styled to match `.stream-form-*` patterns (constitution VI)

**Checkpoint**: Quickstart S1 passes — bullets flow between two browsers, XSS-inert, controls clickable, video undisturbed.

---

## Phase 4: User Story 2 — Streamer sees viewer bullets while broadcasting (Priority: P1)

**Goal**: Owner's page runs the same curtain; bullets overlay the local preview during sharing without touching broadcast logic.

**Independent Test**: Quickstart S1 owner-side items — viewer's message crosses the owner's player while sharing.

- [X] T010 [US2] Verify/adjust owner-side wiring in `stream_detail.html` + `bullets.js`: `BulletCurtain` instantiates for `is_owner` too (independent of `Broadcaster`); overlay z-order sits above `#localPreview`; confirm zero changes to `screenshare.js` signaling/PC logic (FR-011); manual spot-check with sharing active

**Checkpoint**: Owner sees audience bullets mid-broadcast; broadcast unaffected.

---

## Phase 5: User Story 3 — Curtain toggle (Priority: P2)

**Goal**: Per-visit on/off; off hides display only.

**Independent Test**: Quickstart S2.

- [X] T011 [US3] Add curtain toggle to `stream_detail.html` controls row + `bullets.js`: default on; off → clear overlay children and discard incoming items (polling continues, cursor keeps advancing so re-enable shows only new messages — FR-008); on → resume display; toggle is a styled checkbox/button consistent with `.stream-btn`
- [X] T012 [P] [US3] Toggle styles in `streams/static/streams/streams.css` (active/inactive states)

**Checkpoint**: Quickstart S2 passes.

---

## Phase 6: User Story 4 — Volume & mute (Priority: P2)

**Goal**: Standard player audio controls, safe on today's silent streams.

**Independent Test**: Quickstart S3 audio items.

- [X] T013 [US4] Add volume slider (`input[type=range]` 0–1 step .05) and mute button to the viewer controls row in `stream_detail.html`, group rendered `hidden`; new small `streams/static/streams/player_controls.js` (keep out of screenshare.js): on `loadedmetadata` check `remoteVideo.srcObject.getAudioTracks()` — unhide the group only when an audio track exists (locked decision: no fake controls); slider → `remoteVideo.volume`, mute button toggles `remoteVideo.muted` remembering prior level; non-owners only
- [X] T014 [P] [US4] Slider/mute styles in `streams/static/streams/streams.css` matching existing control aesthetics

**Checkpoint**: Quickstart S3 audio items pass; video-only streams unaffected.

---

## Phase 7: User Story 5 — Display modes Auto/Fit/Fill/Theater (Priority: P3)

**Goal**: CSS-only geometry modes incl. Theater page widening; fullscreen-compatible.

**Independent Test**: Quickstart S3 display items.

- [X] T015 [US5] Add display-mode `<select>` (Auto/Fit/Fill/Theater) to the viewer controls row in `stream_detail.html`; wiring in `player_controls.js` sets `data-display-mode` on `#streamPlayer` and toggles `stream-theater` class on the page container; per research R8 Auto≡Fit
- [X] T016 [P] [US5] Mode styles in `streams/static/streams/streams.css`: `[data-display-mode="fill"] video { object-fit: cover }` (default stays contain); `.stream-theater .streams-container { max-width: 1280px }`; verify no conflict with `:fullscreen` rules

**Checkpoint**: Quickstart S3 display items pass.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T017 Template-level tests in `streams/tests.py`: live stream page contains bullet form + overlay div for owner and viewer; ended stream page renders form disabled/absent; (extend `StreamListDetailTests` or `StreamBulletMessageAPITests`)
- [X] T018 Run full suite `python manage.py test` and diff against the pre-existing baseline (~84 failures in authors/entries/inbox/nodes; zero in streams) — zero NEW failures (SC-006); `python manage.py check` + `makemigrations --check --dry-run` clean; `node --check` on `bullets.js`; grep `bullets.js` for `innerHTML` → must be absent (research R4)
- [X] T019 `python manage.py collectstatic --noinput` — WhiteNoise picks up `bullets.js` + updated `streams.css` + template-adjacent statics
- [ ] T020 Execute `specs/004-stream-video-controls/quickstart.md` S1–S4 manually (two+ browsers); verify SC-001…SC-006; update `WORKFLOW.md` Live Streams section with the bullets API and controls
  - ◐ Partially done 2026-07-06: WORKFLOW.md updated (bullets API + controls + tests). Remaining: the manual multi-browser walkthrough (needs a human for screen capture + visual overlay checks).

---

## Dependencies & Execution Order

- **Setup (Phase 1)**: none
- **Foundational (Phase 2)**: blocks US1–US3; strictly T002 → T003 → T004 → T005 → T006
- **US1 (Phase 3)**: needs Phase 2. T007 → T008; T009 [P] alongside either
- **US2 (Phase 4)**: needs US1 (shares bullets.js/template)
- **US3 (Phase 5)**: needs US1; T012 [P] with T011
- **US4 (Phase 6)**: independent of bullets — can start any time after Phase 1, but touches the same template controls row: run after Phase 5 to avoid merge friction; T014 [P] with T013
- **US5 (Phase 7)**: same as US4; T016 [P] with T015
- **Polish (Phase 8)**: last; T017 can be written any time after T008

### Parallel opportunities

- T009, T012, T014, T016 (CSS) each parallel with their phase's template/JS task
- US4/US5 (controls) are functionally independent of US1–US3 (bullets) — a second contributor could build them in parallel against the same template region with coordination

## Implementation Strategy

**MVP first**: Phases 1–3 deliver the send-and-see loop (quickstart S1) — the feature's entire core value. Phase 4 confirms the owner side (thin). Phases 5–7 are additive comfort controls in descending priority. Phase 8 is regression/deploy safety.

**Totals**: 20 tasks — Setup 1, Foundational 5, US1 3, US2 1, US3 2, US4 2, US5 2, Polish 4.
