# Quickstart & Manual Test Checklist: Stream Video Controls and Bullet Curtain

**Feature**: 004-stream-video-controls | **Date**: 2026-07-06

Validation guide for the implemented feature. Automated coverage: `python manage.py test streams`. The overlay animation, controls, and multi-watcher visuals need the manual walkthrough below.

## Prerequisites

```bash
source venv/bin/activate
python manage.py migrate            # applies 0003_streambulletmessage
python manage.py collectstatic --noinput   # WhiteNoise must pick up bullets.js + streams.css
python manage.py runserver 0.0.0.0:8000
```

Two logged-in browser contexts (e.g. Chrome normal = **Owner**, Chrome incognito or second profile = **Viewer**; a third context makes SC-001's "3 concurrent watchers" check possible). Owner creates a stream at `/streams/create/` and both open its detail page.

## S1 — Bullet send & display (US1, US2) — P1

- [ ] Viewer types a message under the player, presses send → input clears (≤1 s).
- [ ] Message animates right→left across the **Viewer's** player within 5 s.
- [ ] Same message animates across the **Owner's** player within 5 s (owner sharing or not) — SC-001.
- [ ] Owner starts screen sharing; Viewer sends another message → it overlays live video on both sides; video never stutters or disconnects.
- [ ] Send `<script>alert(1)</script><b>bold?</b>` → appears as literal text on every screen; no alert, no bold — SC-002.
- [ ] Send 120 × "a" → accepted; 121 × "a" → rejected with a clear length message (input maxlength blocks typing; API enforces too); player unaffected.
- [ ] Send only spaces → rejected; nothing appears.
- [ ] Send a 120-char single word → animates without breaking layout or wrapping off-screen.
- [ ] Burst-send ~10 messages quickly from two contexts → messages spread across multiple lanes, remain readable; page stays responsive (excess may simply not display).
- [ ] While bullets fly, click the fullscreen button and hover other controls → all controls still clickable (overlay never traps the pointer) — FR-007.
- [ ] Enter fullscreen → bullets continue to animate over the fullscreen video.

## S2 — Curtain toggle (US3) — P2

- [ ] Viewer switches the curtain **off** → on-screen bullets disappear/finish; new messages from Owner's side do not appear for Viewer.
- [ ] Meanwhile the Owner still sees those messages — SC-004.
- [ ] Viewer (curtain off) sends a message → Owner still receives it.
- [ ] Viewer switches curtain **on** → only messages sent after re-enabling appear (no replay of missed ones) — FR-008.
- [ ] Reload the Viewer page → curtain defaults back to on; at most the 30 most recent messages backfill once, then live-only (FR-008).

## S3 — Volume, mute, display modes (US4, US5) — P2/P3

- [ ] With today's (silent) stream, **no volume/mute controls are visible** — no fake/broken-looking controls (FR-009).
- [ ] (Only if testing with an audio-carrying stream) volume slider moves smoothly; mute toggles state and icon; unmute restores prior level — responses <1 s (SC-005).
- [ ] Display mode **Fit**: whole frame visible, letterboxed. **Fill**: player area fully covered, edges cropped. **Auto**: same as Fit.
- [ ] **Theater**: player column visibly enlarges; other page content reflows sanely; switching back to Auto restores the normal layout.
- [ ] Pick Fill → enter fullscreen → exit → Fill still applied (FR-010).
- [ ] Mode changes while bullets are flying and video playing → no playback interruption (SC-005).

## S4 — Lifecycle & permissions (FR-003, SC-003, SC-006)

- [ ] Log out in a third tab, `curl` POST `/api/streams/<serial>/bullets/` without credentials → 401/403.
- [ ] Owner clicks **End stream** → Viewer's player shows ended state (existing behavior intact); bullet input becomes disabled with an ended hint; no errors in console.
- [ ] POST a bullet to the ended stream (devtools/curl) → **410**.
- [ ] Open the ended stream's page fresh → no bullet input active, no polling errors.
- [ ] Full regression sweep: share → watch → retry → fullscreen → stop sharing → re-share → end. Everything behaves exactly as before this feature (SC-006).

## Automated gates (run before the walkthrough)

- [ ] `python manage.py test streams` — green, including new `StreamBulletMessageAPITests`.
- [ ] `python manage.py test` — failure set identical to the pre-existing baseline (~84 in authors/entries/inbox/nodes; zero in streams).
- [ ] `python manage.py check` and `python manage.py makemigrations --check --dry-run` — clean.

References: [contracts/bullets-api.md](contracts/bullets-api.md) for exact statuses/shapes; [data-model.md](data-model.md) for the entity.
