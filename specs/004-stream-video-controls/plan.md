# Implementation Plan: Stream Video Controls and Bullet Curtain

**Branch**: `after` (feature dir `004-stream-video-controls`) | **Date**: 2026-07-06 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/004-stream-video-controls/spec.md`

## Summary

Add viewer comfort controls (volume/mute, display modes Auto/Fit/Fill/Theater) and a bullet-curtain (danmaku) live comment overlay to the stream detail page. Bullet messages are persisted content on a new `StreamBulletMessage` model, sent and fetched through plain DRF endpoints under the existing `/api/streams/<uuid>/` namespace, delivered to all watchers by **cursor-based short polling** (`?after=<id>`, non-consuming — deliberately different from the signaling relay's consume-on-read, because bullets are broadcast to everyone). Frontend is one new isolated module `bullets.js` plus small template/CSS additions; `screenshare.js` signaling logic is untouched. Zero new dependencies.

## Technical Context

**Language/Version**: Python 3.12, Django 5.1.1, ES2020 browser JavaScript (no build step)

**Primary Dependencies**: Django REST Framework, djangorestframework-simplejwt (both already installed). No new dependencies.

**Storage**: SQLite (dev/test) / PostgreSQL (Heroku prod) via Django ORM — one new table `streams_streambulletmessage`

**Testing**: Django `TestCase` + DRF `APIClient` against real SQLite test DB (constitution III), extending `streams/tests.py`

**Target Platform**: Existing Django WSGI deployment (Heroku, gunicorn + WhiteNoise); evergreen desktop browsers

**Project Type**: Server-rendered Django web app with progressive-enhancement JS

**Performance Goals**: Bullet visible on all watchers' screens ≤5 s after send (SC-001) with 1.5 s polling; controls respond <1 s (SC-005); overlay animation must not disturb WebRTC playback

**Constraints**: No WebSockets/Channels, no media server, no new deps; XSS-safe rendering (textContent only, DB stores raw text, DRF returns JSON); overlay must not block player controls (pointer-events)

**Scale/Scope**: Classroom-scale (tens of watchers per stream); one new model + 2 endpoints (one URL), 2 small new JS files (`bullets.js`, `player_controls.js`), template + CSS additions, ~15 new tests. Content limit **120 chars** (locked decision)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | Status | How this plan complies |
|---|-----------|--------|------------------------|
| I | Model-First | ✅ | `StreamBulletMessage` model + migration land first; serializer → view → template → JS strictly after |
| II | Dual Auth | ✅ | Bullet endpoints declare `[JWTAuthentication, SessionAuthentication]` + `IsAuthenticated`, same as every streams view |
| III | Real DB tests | ✅ | All new tests extend `StreamTestBase` in `streams/tests.py`, real SQLite, no mocks |
| IV | Serializer-owned validation | ✅ | strip/empty/length rules in `StreamBulletMessageSerializer.validate_content`; `stream`/`sender` injected server-side via context; views stay thin (liveness gate + 404/410 routing only, mirroring `StreamSignalView`) |
| V | Server-side relationship state | ✅ | No new relationship-dependent UI; existing `is_owner` context reused; bullet input rendered server-side for all logged-in users on live streams |
| VI | CSS in app files | ✅ | All new styles in `streams/static/streams/streams.css`; no inline styles (animation positioning uses CSS custom properties set via `style.setProperty` for per-bullet lane/duration — dimensional only, the sanctioned exception) |
| VII | Public API contract | ✅ | Responses follow platform shape: `{"type": "bullets", "items": [...]}`; author exposed as serial + displayName (no FQID needed for overlay); documented in contracts/bullets-api.md |
| VIII | Simplicity | ✅ | No rate limiter, no moderation, no history replay, no per-account persistence of UI prefs; display modes instead of an SFU |

**Post-design re-check (Phase 1)**: all gates still pass; no Complexity Tracking entries needed.

## Project Structure

### Documentation (this feature)

```text
specs/004-stream-video-controls/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0: feasibility decisions (resolution, audio, polling style)
├── data-model.md        # Phase 1: StreamBulletMessage
├── quickstart.md        # Phase 1: manual validation walkthrough (also the manual test checklist)
├── contracts/
│   └── bullets-api.md   # Phase 1: bullet message API contract
├── checklists/
│   └── requirements.md  # Spec quality checklist (complete)
└── tasks.md             # Phase 2 output (/speckit-tasks — not created by /speckit-plan)
```

### Source Code (repository root)

```text
streams/
├── models.py                          # + StreamBulletMessage
├── migrations/
│   └── 0003_streambulletmessage.py    # + new
├── serializers.py                     # + StreamBulletMessageSerializer
├── views.py                           # + StreamBulletView (POST/GET on one URL)
├── urls.py                            # + streams/<uuid:pk>/bullets/
├── tests.py                           # + StreamBulletMessageAPITests
├── templates/streams/
│   └── stream_detail.html             # + player control bar (volume/mute/mode/curtain toggle),
│                                      #   bullet overlay div, bullet send form; loads bullets.js
└── static/streams/
    ├── bullets.js                     # + NEW, isolated: polling + overlay lanes + send form
    ├── screenshare.js                 # touched ONLY to expose remoteVideo volume default; no signaling changes
    └── streams.css                    # + control bar, overlay, lane animation, theater mode styles
```

**Structure Decision**: everything stays inside the existing `streams` app — same layout as 002/003. `bullets.js` is deliberately independent of `screenshare.js` (they share only the DOM and the CSRF/JWT header pattern, which is copied from `signaling.js`, not imported) so a bullets bug can never break the WebRTC path (FR-011).

## Key Design Decisions (from research.md)

1. **Cursor polling, not consume-on-read** — `GET .../bullets/?after=<id>` returns rows with `id > after` (capped at 50). Signals are addressed to one reader and must vanish when read; bullets are broadcast, so every watcher keeps their own cursor and rows are never deleted by reads. Poll interval **1.5 s** (locked decision; SC-001's 5 s bound met with margin).
2. **Latest-30 bootstrap** — on page load the client calls `GET .../bullets/?latest=1`, which returns the **30 most recent messages** (ascending) plus the current max id as cursor; the client backfills those through the normal display pipeline and polls from the cursor. Implements FR-008: recent context, never full history.
3. **XSS strategy: escape at render, store raw** — DB keeps what the user typed (length-capped, stripped); DRF returns JSON (no HTML context); the overlay writes exclusively via `textContent`/`createTextNode`. Template-side, nothing user-generated is rendered by Django for this feature. Tests assert a `<script>` payload round-trips as literal text in JSON and that the JS file contains no `innerHTML` usage.
4. **410 for ended streams** — same convention as the signaling API: POST/GET on an ended stream → 410, unknown stream → 404. The client already has the `StreamEndedError` idea; bullets.js handles 410 by disabling the input, not by tearing down the player.
5. **Display modes are CSS-only** — `data-display-mode` attribute on the player container: Auto/Fit → `object-fit: contain`, Fill → `object-fit: cover`, Theater → a container class that widens the player column. True resolution switching rejected (P2P mesh fans out one encoding; `RTCRtpSender.setParameters` degrades every viewer — out of scope per spec).
6. **Volume/mute are native video properties** (`video.volume`, `video.muted`) on `#remoteVideo`, but the control group is **hidden unless the received stream has an audio track** (checked on `loadedmetadata` via `srcObject.getAudioTracks()`) — locked decision: no fake controls on today's silent streams.
7. **Overlay implementation** — absolutely-positioned layer over the player, `pointer-events: none` (FR-007 clickability), fixed lanes (**6 desktop, 3 on narrow/mobile viewports**) assigned least-recently-used, CSS `transform` keyframe animation right→left with duration scaled by message length, element removed on `animationend`. When all lanes are busy, excess bullets are shed from display only (still stored/delivered).

## Complexity Tracking

No constitution violations — table intentionally empty.
