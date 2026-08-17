# Implementation Plan: Screen-Sharing for Live Streams

**Branch**: `003-screen-share` | **Date**: 2026-07-06 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/003-screen-share/spec.md`

## Summary

Add real browser-to-browser screen sharing on top of the 002 stream lifecycle: the owner captures their screen with `getDisplayMedia` and broadcasts it over **WebRTC `RTCPeerConnection`** (P2P mesh, one connection per viewer). Signaling (join/offer/answer/ICE/bye) is exchanged through **REST endpoints + short polling** backed by a tiny ephemeral `StreamSignal` model — **not Django Channels**, because the deploy is WSGI-only (gunicorn, no daphne/redis) and polling delivers the same handshake with zero new dependencies. Server-side rule: **only the stream owner may address viewers** (offers/candidates), enforced in the serializer. The existing placeholder player becomes the "waiting" state of a five-state viewer UI (waiting / connecting / live / ended / error).

## Technical Context

**Language/Version**: Python 3.12, Django 5.1.1; ES2020 browser JS (no build step, matching existing static JS)

**Primary Dependencies**: DRF + simplejwt (existing). **No new Python or JS dependencies.** Browser APIs: `navigator.mediaDevices.getDisplayMedia`, `RTCPeerConnection`. STUN: free `stun:stun.l.google.com:19302` (LAN works with host candidates even without it)

**Storage**: One new table `streams_streamsignal` — short-lived rows, consumed (deleted) on read, purged on stream end and by a 5-minute TTL sweep

**Testing**: Django `TestCase`/`APIClient` against real SQLite for all signaling endpoints (constitution III). WebRTC media path itself is browser-side and validated via the quickstart manual walkthrough (automating two-browser WebRTC is out of scope)

**Target Platform**: Existing WSGI deploy (gunicorn/Heroku) — unchanged. Evergreen desktop browsers for broadcasting; viewing wherever WebRTC playback is supported

**Project Type**: Extends the existing `streams` Django app (no new app)

**Performance Goals**: Viewer sees video ≤10 s after share start (SC-002); polling cadence ≈1 s during handshake, ≈3–10 s idle; ≤5 concurrent viewers per stream (FR-010)

**Constraints**: WSGI-only (no ASGI server swap); no paid services; no media server; no TURN in v1 (local-first per spec assumption); dual session+JWT auth on all endpoints (constitution II)

**Scale/Scope**: 1 model, 2 API endpoints (POST signal, GET/consume signals), 2 new JS modules, detail-template rework, ~15 new tests

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | Status | How the plan complies |
|---|-----------|--------|----------------------|
| I | Model-First | PASS | `StreamSignal` model + migration land first; endpoints/JS follow. |
| II | Dual Authentication | PASS | Both signal endpoints use `[JWTAuthentication, SessionAuthentication]` like the 002 views. |
| III | No Mocked Database | PASS | All signaling tests hit the real test DB. Browser media path is manual-validated (quickstart) — no DB involved, nothing mocked. |
| IV | Serializers Own Validation | PASS | `StreamSignalSerializer.validate()` enforces kind choices, payload size cap, live-stream requirement, and the owner-only-addresses-viewers rule. Views stay thin. |
| V | Server-Side Relationship State | PASS | `is_owner` already comes from template context (002); Share Screen button renders only for the owner server-side. JS never decides ownership. |
| VI | CSS in App Files | PASS | All player-state styles go in `streams/static/streams/streams.css`; `<video>` gets only dimensional attributes inline. |
| VII | Public API Contract | PASS | Signal payloads use `type: "signal"` / `type: "signals"` envelopes; stream identity by UUID serial in URLs, consistent with 002. |
| VIII | Simplicity / Scope Control | PASS | No Channels, no media server, no TURN, no recording, no presence table — the minimum that satisfies the spec. Transport isolated in `signaling.js` so WebSockets can replace polling later without touching WebRTC logic. |

**Post-design re-check (after Phase 1)**: PASS — no violations introduced; Complexity Tracking left empty.

## Project Structure

### Documentation (this feature)

```text
specs/003-screen-share/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0 — decisions & rejected alternatives
├── data-model.md        # Phase 1 — StreamSignal model
├── quickstart.md        # Phase 1 — validation walkthrough
├── contracts/
│   └── signaling-api.md # Phase 1 — REST signaling + JS-visible protocol contract
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
streams/
├── models.py                        # + StreamSignal (ephemeral signaling rows)
├── migrations/0002_streamsignal.py  # NEW
├── serializers.py                   # + StreamSignalSerializer (all rules live here)
├── views.py                         # + SignalCreateView, SignalPollView; end-stream now purges signals
├── urls.py                          # + streams/<uuid:pk>/signals/ (GET poll, POST send)
├── templates/streams/
│   └── stream_detail.html           # player rework: 5 UI states, owner Share/Stop controls, <video> elements
├── static/streams/
│   ├── streams.css                  # + player-state / on-air / control styles
│   ├── signaling.js                 # NEW — transport: postSignal / pollSignals (REST polling; WS-swappable)
│   └── screenshare.js               # NEW — Broadcaster (getDisplayMedia + per-viewer RTCPeerConnection)
│                                    #        and Player (join/heartbeat, answer, state machine)
└── tests.py                         # + StreamSignalAPITests (permissions, scoping, ended-stream, consume-on-read)
```

**Structure Decision**: Extend the existing `streams` app — signaling is meaningless without a `Stream`, and 002 established the app as the home for all stream concerns. No new app, no new Python deps, no deploy changes.

## Design Decisions (details in research.md)

1. **REST + short polling for signaling, not Django Channels** — the repo is WSGI-only; Channels would force daphne/uvicorn, a channel layer, Procfile and Heroku changes. Polling at ≤6 participants is trivial load and needs zero new infrastructure. Transport is isolated behind `signaling.js` for a later WS swap.
2. **P2P mesh, no media server** — one streamer uploads to ≤5 viewers directly; ~5 outbound encodings is within a desktop browser's capability. An SFU would add a server component and deployment surface for zero benefit at this scale.
3. **`StreamSignal` rows are consumed on read** (deleted when their addressee fetches them) — no cursors, no growth; plus purge-on-end and a 5-minute TTL sweep.
4. **Direction rule as the security core**: signals addressed to viewers (`offer`, owner `candidate`, `bye`) may **only** be created by the stream owner — enforced in the serializer (403). Anyone authenticated may address the streamer (`join`, `answer`, viewer `candidate`, `bye`). This makes broadcast hijack impossible server-side (FR-006, SC-003).
5. **`peer_id` as capability token**: each viewer connection generates a client-side UUIDv4; viewer polls return only signals for that peer_id. Unguessable at 128 bits — adequate for v1 (documented trade-off in research R5).
6. **No persisted presence**: a viewer learns the streamer is sharing by receiving an offer in response to its `join` heartbeat (re-sent every 10 s while waiting). No `is_sharing` flag on `Stream` — broadcast presence stays ephemeral per the spec.
7. **Lifecycle integration**: "End stream" first stops the broadcast (close PCs, send `bye`s), then calls the existing end endpoint, which now also purges the stream's signals. Ended streams reject all signal traffic with `410 Gone`, which is the viewer's cue to show the ended state.

## Complexity Tracking

*No constitution violations — table intentionally empty.*
