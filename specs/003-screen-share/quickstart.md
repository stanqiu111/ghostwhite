# Quickstart Validation: Screen-Sharing for Live Streams

**Date**: 2026-07-06 | **Plan**: [plan.md](plan.md) | **Contract**: [contracts/signaling-api.md](contracts/signaling-api.md)

## Prerequisites

```bash
cd /Users/stanqiu/f25-project-ghostwhite
source venv/bin/activate
python manage.py migrate            # applies streams/0002_streamsignal
python manage.py runserver 8000
```

Two local user accounts; two different browsers (or one normal + one incognito window) on the same machine. Screen-capture permission prompts require a real (non-headless) browser.

## Automated validation

```bash
python manage.py test streams       # 002 lifecycle tests + new signaling tests — all green
python manage.py test               # full suite — no NEW failures vs. the known pre-existing baseline
python manage.py check
```

## Manual scenario walkthrough

### S1 — Streamer shares their screen (User Story 1)

1. As user A: go live (`/streams/create/`), land on the stream detail page.
2. **Expect**: a **Share Screen** button (A is the owner; stream is live).
3. Click it → browser permission prompt → pick a screen/window → Allow.
4. **Expect**: local preview shows the captured screen; an **on-air** badge and **Stop sharing** button appear; Share Screen button is gone.
5. Click **Stop sharing** → **Expect**: preview stops, page returns to the non-sharing owner state, stream is still Live.
6. Click Share Screen again but **Deny/Cancel** the prompt → **Expect**: a clear hint/error message, no broadcast, page fully usable.

### S2 — Viewer watches (User Story 2)

1. As user B (second browser): open the same stream's detail page **before** A shares.
2. **Expect**: placeholder in **"Waiting for streamer…"** state; no Share Screen button (B is not the owner).
3. Have A start sharing → **Expect (≤10 s, no reload)**: B's player passes through **connecting** and then shows A's screen **live**.
4. Open the same page as a third user / third window → **Expect**: it also reaches live (multi-viewer mesh).
5. Have A click Stop sharing → **Expect**: B returns to **waiting** without reload.
6. Have A share again → **Expect**: B comes back to **live** automatically (heartbeat join).

### S3 — Integrity & lifecycle (User Story 3)

1. As B, attempt to hijack: `curl -X POST .../api/streams/<serial>/signals/ -d '{"kind":"offer","direction":"to_viewer","peer_id":"x","payload":{}}' -H "Authorization: Bearer <B token>"` → **Expect 403**; A's viewers never see video from B.
2. As B, poll `?role=streamer` → **Expect 403**.
3. While A is sharing and B watching: A clicks **End stream** → **Expect**: broadcast stops, B transitions to **ended** state (≤10 s), stream leaves `/streams/`, signal POST/GET now return **410**.
4. Refresh the ended stream's page → **Expect**: ended state, no Share button, no connection attempts (no signal polling in devtools network tab).
5. Kill A's tab mid-broadcast (without ending) → **Expect**: B drops back to **waiting**; stream still listed as live.

### Regression sweep (SC-006 / FR-011)

- Run `python manage.py test streams` — all 002 lifecycle tests still pass.
- Create/list/end a stream with **no** sharing at all — placeholder behaves exactly as in 002.
- `python manage.py collectstatic --noinput` — picks up `signaling.js`, `screenshare.js`, updated `streams.css`.
