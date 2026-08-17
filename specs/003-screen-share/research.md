# Research: Screen-Sharing for Live Streams

**Date**: 2026-07-06 | **Plan**: [plan.md](plan.md)

## R1 — Signaling transport: REST polling vs. Django Channels (WebSockets)

- **Decision**: REST endpoints + short polling, backed by an ephemeral `StreamSignal` table. No Django Channels.
- **Rationale**: The repo is **WSGI-only**: `Procfile` runs `gunicorn ghostwhite.wsgi`, `channels`/`daphne`/`redis` are not installed, and `asgi.py` is the untouched Django default. Adopting Channels means: two new dependencies, swapping the production server (gunicorn → daphne/uvicorn), choosing and operating a channel layer (in-memory is single-process-only; Redis is a new Heroku add-on), and re-verifying every existing view under ASGI. That is a deployment-risk mountain to move ~a dozen tiny JSON messages per viewer connection. WebRTC signaling is not latency-sensitive beyond human patience — a 1 s poll adds at most ~2 s to connection setup, well within SC-002's 10 s budget. The user's requirements explicitly allow "signaling **endpoints** or WebSocket routing". Load at course scale: 6 participants × 1 poll/s worst case ≈ trivial for gunicorn.
- **Alternatives considered**: **Django Channels** — rejected for v1 on infrastructure cost above; the swap path is preserved by isolating transport in `signaling.js` (`postSignal`/`pollSignals` are the only functions `screenshare.js` calls). **Server-Sent Events** — rejected: long-lived connections tie up sync gunicorn workers, which is worse than polling on this stack.

## R2 — Media topology: P2P mesh vs. media server (SFU)

- **Decision**: Pure P2P mesh — the streamer's browser maintains one `RTCPeerConnection` per viewer and uploads a copy of the video to each. No media server.
- **Rationale**: Spec bounds the scale to one streamer and ~5 viewers (FR-010). Desktop Chrome/Firefox comfortably sustain ~5 outbound encodings of a screen track (screen content is low-motion, encodes cheaply). An SFU (mediasoup/Janus/LiveKit self-hosted) would add a stateful media process that cannot run inside gunicorn, needs its own deployment, port management, and configuration — all to solve an upload-fanout problem this feature does not have at ≤5 viewers. This is the "explain why P2P is insufficient" test inverted: it is sufficient, so no server.
- **When to revisit**: >8–10 viewers per stream (streamer upload saturates), recording, or federation of live video. The signaling protocol (offer/answer per peer) is exactly what an SFU consumes, so a later migration changes the peer endpoint, not the protocol.

## R3 — NAT traversal: STUN only, no TURN

- **Decision**: `iceServers: [{ urls: "stun:stun.l.google.com:19302" }]`. No TURN server in v1.
- **Rationale**: Spec is local-first: same machine or LAN, where host candidates alone connect (STUN isn't even needed). Google's public STUN is free and covers most simple-NAT cases beyond LAN. TURN requires running/renting a relay (coturn or a paid service) — out of scope and explicitly excluded by "no paid third-party services". Failure beyond symmetric NAT surfaces as the viewer error state with retry.
- **Alternatives considered**: self-hosted coturn — real infra to operate, rejected for v1; paid TURN (Twilio etc.) — excluded by requirements.

## R4 — Signal storage & delivery: consume-on-read rows

- **Decision**: `StreamSignal` rows are deleted in the same transaction that returns them to their addressee. Viewers re-send `join` every 10 s while waiting ("heartbeat join"); the broadcaster dedups by `peer_id`.
- **Rationale**: Consume-on-read eliminates cursors, read-tracking, and unbounded growth; the table holds only in-flight handshake messages (a handful of rows). The heartbeat join solves the "streamer starts sharing after viewers arrived" race without any presence flag: whenever the broadcaster is live-polling, the next heartbeat join reaches it and triggers an offer. Stale/duplicate joins are cheap: the broadcaster ignores peer_ids it already has connections for.
- **Cleanup**: signals purged when the stream ends (in the end view) and rows older than 5 minutes deleted opportunistically on each poll — belt and suspenders against orphans.
- **Alternatives considered**: cursor-based fetch with `after=<id>` — keeps rows around, needs client cursor state, more code for zero benefit at this scale; in-memory dict — violates multi-process gunicorn (workers don't share memory) and constitution III's real-DB testing.

## R5 — Security model for signaling

- **Decision**: Three server-side rules, all in `StreamSignalSerializer` / the poll view:
  1. **Direction rule**: signals addressed `to_viewer` (`offer`, broadcaster `candidate`, broadcaster `bye`) may only be created by `stream.owner` → anyone else gets 403. Anyone authenticated may send `to_streamer` signals (`join`, `answer`, viewer `candidate`, viewer `bye`).
  2. **Streamer poll rule**: `GET ...signals/?role=streamer` returns signals only to `stream.owner` (403 otherwise).
  3. **Liveness rule**: all signal POST/GET on an ended (or unknown) stream → `410 Gone` / 404; ending a stream purges its remaining signals.
- **Rationale**: Rule 1 makes broadcast hijack structurally impossible: a malicious user can never deliver an SDP offer to a viewer, so no viewer ever renders video from a non-owner (FR-006, SC-003, US3-AS1). Rule 3 implements FR-008's "stop accepting connection setup after end" and doubles as the viewer's ended-state signal.
- **Accepted trade-off (documented)**: viewer polls are authorized by `peer_id` possession — a client-generated UUIDv4 acting as a 128-bit capability token. A user who somehow learned another viewer's peer_id could read that viewer's offer SDP (not inject video — rule 1 still holds; and both parties' media is DTLS-encrypted end-to-end). Binding peers to user accounts would need a peer registry table that outlives consumed signals — deliberate v1 simplification per constitution VIII.

## R6 — Presence: how a viewer knows the streamer is sharing

- **Decision**: No persisted `is_sharing` flag. The viewer's `join` heartbeat + receipt of an `offer` **is** the presence protocol. Waiting → connecting happens when an offer arrives; live → waiting happens when the RTCPeerConnection closes/disconnects (broadcaster stopped) with a `bye` as an accelerator.
- **Rationale**: The spec explicitly makes broadcast presence ephemeral and tied to the streamer's open page. A DB flag would lie the moment the streamer's tab crashes; connection state cannot lie. Keeps `Stream` untouched — zero migration risk to 002.
- **Alternatives considered**: `sharing_since` timestamp on `Stream` updated by broadcaster heartbeat — extra writes, staleness window, and a migration on a shipped model; rejected.

## R7 — Client architecture: two JS modules, five UI states

- **Decision**: `signaling.js` (transport only: `postSignal(streamSerial, kind, peerId, payload)`, `pollSignals(streamSerial, role, peerId)` with the dual-auth header pattern from `entry_detail.html`) and `screenshare.js` (a `Broadcaster` class: getDisplayMedia, per-peer RTCPeerConnection map, offer creation, track-ended handling; a `Player` class: peer_id generation, join heartbeat, answer/ICE, `<video>` attachment, and the state machine `waiting|connecting|live|ended|error`). `stream_detail.html` wires them via data attributes (`data-stream-serial`, `data-is-owner`, `data-stream-status`).
- **Rationale**: Transport isolation is the concrete "extension point" promised in 002 and the WS-swap path from R1. State machine in one place keeps FR-005's five states honest and testable by inspection. No build step, matching the repo's plain-static JS convention.
- **UI mapping**: waiting = existing placeholder div (new copy "Waiting for streamer…"); connecting = placeholder + spinner text; live = `<video autoplay playsinline>` shown, placeholder hidden; ended = placeholder with ended copy (already exists in 002); error = placeholder + message + Retry button (new peer_id, rejoin).

## R8 — Broadcaster lifecycle edge cases

- **Decision**:
  - "Stop sharing" and the browser's native stop control both funnel through the `getDisplayMedia` track's `ended` event → close all PCs, send `bye` per peer, revert owner UI. Stream stays live.
  - "End stream" click: stop sharing first (same routine), then the existing end POST; the end view purges signals; viewers get PC close + `410` on next poll → ended state.
  - Owner refresh/tab close mid-broadcast: PCs die with the page; viewers' `connectionstatechange` fires → back to waiting + heartbeat join resumes. No server cleanup needed (TTL sweep collects stray rows).
  - Double "Share Screen" / second tab: `Broadcaster` is a singleton per page (button disabled while active); a second tab starting a share triggers new offers that simply replace viewers' connections on next join cycle — last-writer-wins, no doubling (edge case per spec).
- **Rationale**: Every path reduces to "PC state is the truth, signals are hints" — the design stays correct even when the hints are lost, which is exactly what ephemeral-presence requires.
