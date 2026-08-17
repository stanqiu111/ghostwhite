# Tasks: Screen-Sharing for Live Streams

**Input**: Design documents from `/specs/003-screen-share/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/signaling-api.md, quickstart.md

**Tests**: Included — spec FR-012 requires automated tests for server-side signaling permissions/scoping. Per constitution III, all tests hit the real SQLite test DB. The browser-side WebRTC media path is validated by the quickstart manual walkthrough (two real browsers).

**Organization**: Tasks grouped by user story. Note: US1 (broadcast) and US2 (watch) share the WebRTC handshake, so US1 builds the broadcaster half and US2 the viewer half; each has its own independent test criteria.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 = Streamer shares screen, US2 = Viewer watches, US3 = Integrity & lifecycle

## Phase 1: Setup

**Purpose**: No new apps/deps needed (plan: zero new dependencies). Only a docs touch-point.

- [X] T001 Verify no dependency/deploy changes are required: confirm `Procfile`, `requirements.txt`, `ghostwhite/settings.py` need no edits for this feature (WSGI + polling design); note confirmation in `specs/003-screen-share/tasks.md` when checking off
  - ✅ Confirmed 2026-07-06: `Procfile` and `requirements.txt` untouched; the only `settings.py` diff on this branch is the pre-existing `streams` app registration (002) and an unrelated email feature — 003 added zero dependency/deploy changes.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The `StreamSignal` model, migration, serializer, and both signaling endpoints — every user story depends on them (constitution I: model first).

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 Add `StreamSignal` model to `streams/models.py` per `data-model.md`: `stream` FK (`related_name="signals"`), `sender` FK (`related_name="+"`), `direction` choices to_streamer/to_viewer, `peer_id` (≤64), `kind` choices join/offer/answer/candidate/bye, `payload` JSONField, `created_at`; `Meta` ordering `["created_at"]`, index `("stream","direction","peer_id")` named `signal_route_idx`
- [X] T003 Generate and apply migration `streams/migrations/0002_streamsignal.py` (`makemigrations streams` + `migrate`); verify index in `sqlmigrate` output
- [X] T004 Add `StreamSignalSerializer` to `streams/serializers.py` per `data-model.md` validation rules: kind/direction coherence (`offer`→to_viewer only, `join`/`answer`→to_streamer only), payload ≤ 32 KB, **direction rule** — `to_viewer` requires `sender == stream.owner` (raise `PermissionDenied`); `stream`/`sender` injected server-side, never client-writable (constitution IV)
- [X] T005 Add `SignalCreateView` (POST) and `SignalPollView` (GET, consume-on-read inside `transaction.atomic()`, plus 5-minute TTL sweep per poll) to `streams/views.py` per `contracts/signaling-api.md`: dual `[JWTAuthentication, SessionAuthentication]`, `IsAuthenticated`; 404 unknown stream, **410 ended stream**, 403 non-owner `role=streamer` poll, 400 missing/invalid `role` or missing `peer_id`; register route `streams/<uuid:pk>/signals/` in `streams/urls.py`
- [X] T006 Extend `StreamEndView` in `streams/views.py` to purge the stream's remaining signals (`stream.signals.all().delete()`) after `stream.end()` — implements FR-008 cleanup
- [X] T007 Foundational signaling tests in `streams/tests.py` (class `StreamSignalAPITests`, real SQLite, reuse `StreamTestBase`): POST join/answer/candidate to_streamer as viewer → 201; **POST offer/to_viewer as non-owner → 403** (SC-003); POST offer as owner → 201; kind/direction mismatch → 400; oversized payload → 400; POST/GET on ended stream → 410; unknown stream → 404; unauthenticated → 401/403; `role=streamer` poll as non-owner → 403; poll returns items once then empty (consume-on-read); viewer poll returns only matching `peer_id` items; ending a stream deletes its signals; JWT-auth'd POST also works (constitution II)

**Checkpoint**: `python manage.py test streams` green — signaling relay is proven server-side; browser work can begin.

---

## Phase 3: User Story 1 — Streamer shares their screen (Priority: P1) 🎯 MVP

**Goal**: Owner clicks Share Screen → browser permission → local preview + on-air state; Stop sharing reverts, stream stays live.

**Independent Test**: Quickstart S1 — as owner, share, see preview/on-air, stop, deny-permission path shows a hint. (Testable without any viewer.)

### Implementation for User Story 1

- [X] T008 [US1] Create `streams/static/streams/signaling.js`: `postSignal(serial, {kind, direction, peerId, payload})` and `pollSignals(serial, role, peerId)` wrapping `fetch('/api/streams/...')` with the CSRF + optional-JWT header pattern from `stream_detail.html`'s end-button JS; 410 responses surface as a typed `StreamEndedError` — transport module only, no WebRTC code (research R7 extension point)
- [X] T009 [US1] Create `streams/static/streams/screenshare.js` — `Broadcaster` class: `start()` calls `navigator.mediaDevices.getDisplayMedia({video: true, audio: false})`, attaches stream to `#localPreview`, starts `role=streamer` polling (~1.5 s); on `join` (unknown peer_id) → new `RTCPeerConnection` (Google STUN config per contract §3), `addTrack`s, `createOffer`/`setLocalDescription`, POST offer to_viewer; on `answer` → `setRemoteDescription`; on viewer `candidate` → `addIceCandidate`; local `onicecandidate` → POST candidate to_viewer; `stop()` (button or captured track's `ended` event) closes all PCs, POSTs `bye` per peer, stops polling; permission-denied → UI hint state, no broadcast (FR-002)
- [X] T010 [US1] Update `streams/templates/streams/stream_detail.html` for the owner: `#shareScreenBtn` rendered only when `is_owner and stream.is_live` (server-side, constitution V); `#stopSharingBtn`, on-air badge, `#localPreview` `<video muted>` shown only while sharing; load `signaling.js` + `screenshare.js`; expose `data-stream-serial`/`data-is-owner`/`data-stream-status` on the player container; keep existing End-button JS
- [X] T011 [US1] Add owner-side styles to `streams/static/streams/streams.css`: `.stream-onair-badge` (pulsing red, reuse `stream-badge-live` pattern), `#localPreview` sizing within the player area, Share/Stop button states (no inline styles, constitution VI)

**Checkpoint**: Quickstart S1 passes — owner can capture, preview, stop, and handle denial. Signals flow (visible in devtools) even with zero viewers.

---

## Phase 4: User Story 2 — Viewer watches the shared screen (Priority: P1)

**Goal**: Viewers on a live stream page auto-receive the broadcast; five visible states: waiting / connecting / live / ended / error.

**Independent Test**: Quickstart S2 — two browsers: viewer waits, sees video ≤10 s after share starts, returns to waiting on stop, multi-viewer works.

### Implementation for User Story 2

- [X] T012 [US2] Extend `streams/static/streams/screenshare.js` — `Player` class: generate `peer_id` (crypto.randomUUID), POST `join` + heartbeat every 10 s while `waiting`; poll `role=viewer` (~1 s handshake / ~3 s live); on `offer` → state `connecting`, `setRemoteDescription`, `createAnswer` → POST answer; trickle ICE both ways; `ontrack` + `connectionState === "connected"` → attach `MediaStream` to `#remoteVideo`, state `live`; on `bye`/PC `disconnected|failed|closed` while stream live → back to `waiting` (resume heartbeat); on `StreamEndedError` (410) → confirm via `GET /api/streams/<serial>/` → state `ended`, stop everything; unrecoverable error → state `error` (FR-004, FR-005, contract §3 P1–P7)
- [X] T013 [US2] Update `streams/templates/streams/stream_detail.html` for viewers: `#remoteVideo` `<video autoplay playsinline>` hidden by default; placeholder div now carries `data-player-state` with copy per state — waiting "Waiting for streamer…", connecting "Connecting…", ended (existing copy), error + `#retryBtn` (new peer_id → rejoin); instantiate `Player` for non-owners on live streams, and ended-state rendering for ended streams (FR-011: placeholder remains the waiting/fallback visual)
- [X] T014 [US2] Add viewer-side styles to `streams/static/streams/streams.css`: `#remoteVideo` fills the 16:9 player area, per-state placeholder styling via `[data-player-state="..."]` selectors, connecting spinner, error + retry button styling

**Checkpoint**: Quickstart S2 passes — full watch loop across two browsers, multi-viewer verified.

---

## Phase 5: User Story 3 — Broadcast integrity & lifecycle integration (Priority: P1)

**Goal**: Non-owners provably cannot broadcast; ending a stream tears everything down; 002 MVP unbroken.

### Tests for User Story 3

- [X] T015 [US3] Integration-grade tests in `streams/tests.py` (class `StreamSignalLifecycleTests`): full handshake relay simulation via API only — viewer joins, owner polls & receives join, owner posts offer, viewer polls & receives offer, posts answer, owner receives answer (assert exact consume-on-read sequencing); non-owner cannot receive streamer-role signals nor deliver to_viewer signals even mid-handshake; after `POST .../end/` all signal traffic → 410 and previously queued signals are gone; TTL sweep removes >5-minute-old rows on poll

### Implementation for User Story 3

- [X] T016 [US3] Wire "End stream" to broadcast teardown in `streams/templates/streams/stream_detail.html` / `screenshare.js`: owner's end-button handler calls `broadcaster.stop()` (close PCs + byes) before the existing end POST; `Player` handles the resulting 410 → ended state without reload (US3-AS2, FR-008)
- [X] T017 [US3] Guard re-entrancy and owner edge cases in `streams/static/streams/screenshare.js`: Share button disabled while a broadcast is active (no double-start); `getDisplayMedia` track `ended` (browser-native "Stop sharing" bar) funnels into the same `stop()`; page `beforeunload` best-effort byes (research R8)

**Checkpoint**: Quickstart S3 passes; `python manage.py test streams` fully green including lifecycle tests.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T018 Run the full suite `python manage.py test` and diff failures against the known pre-existing baseline (see memory/WORKFLOW context) — zero NEW failures (SC-006); `python manage.py check` and `makemigrations --check --dry-run` clean
  - ✅ 2026-07-06: 172 tests, 84 failures/errors — all in `authors`/`entries`/`inbox`/`nodes` (pre-existing baseline ~86), **zero in `streams`**; `check` and `makemigrations --check` clean; `streams` suite alone: 50/50 OK.
- [X] T019 `python manage.py collectstatic --noinput` — WhiteNoise manifest picks up `signaling.js`, `screenshare.js`, updated `streams.css`
- [ ] T020 Execute `specs/003-screen-share/quickstart.md` S1–S3 manually with two real browsers (screen-capture prompts can't be automated headlessly); verify SC-001 (share ≤15 s), SC-002 (viewer live ≤10 s), SC-005 (teardown ≤10 s); update `WORKFLOW.md` Live Streams section with the signaling API and screen-share flow
  - ◐ Partially done 2026-07-06: `WORKFLOW.md` Live Streams section updated (signaling API + browser flow). Remaining: the manual two-browser quickstart walkthrough (requires a human at real screen-capture permission prompts).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none
- **Foundational (Phase 2)**: blocks everything; strictly ordered T002 → T003 → T004 → T005 → T006 → T007
- **US1 (Phase 3)**: needs Phase 2. T008 → T009 → T010 → T011 (T011 can start alongside T010)
- **US2 (Phase 4)**: needs Phase 2 + T008 (transport) + shares `screenshare.js`/`stream_detail.html` with US1 → run after US1
- **US3 (Phase 5)**: T015 needs only Phase 2 (can be written in parallel with Phases 3–4); T016–T017 need US1+US2 code
- **Polish (Phase 6)**: last

### Parallel Opportunities

- T015 (US3 server-side lifecycle tests) in parallel with all of Phase 3/4 (different file regions, server-only)
- T011 alongside T010; T014 alongside T013 (CSS vs. template)

---

## Implementation Strategy

**MVP first**: Phases 1–3 give a broadcaster with local preview and server-proven signaling — demonstrable alone (quickstart S1). Phase 4 completes the actual watching loop (the feature's real value). Phase 5 locks integrity + lifecycle. Phase 6 is regression/deploy safety.

**Sequencing rationale**: US1 and US2 share the handshake, so the broadcaster half lands first (it is independently testable via devtools signal traffic), then the viewer half completes the loop — avoiding a half-wired state where neither side can be validated.

**Totals**: 20 tasks — Setup 1, Foundational 6, US1 4, US2 3, US3 3, Polish 3.
