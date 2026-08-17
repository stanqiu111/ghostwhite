# Research: Stream Video Controls and Bullet Curtain

**Feature**: 004-stream-video-controls | **Date**: 2026-07-06

All decisions verified against the actual 003 implementation (`streams/views.py`, `screenshare.js`, `signaling.js`, `streams.css`) — no unresolved NEEDS CLARIFICATION items remain.

## R1. Is true resolution/quality switching feasible? → No; use display modes

- **Decision**: Implement display-size modes (Auto / Fit / Fill / Theater) instead of resolution selection.
- **Rationale**: 003's architecture is a P2P mesh — the broadcaster encodes **one** video feed and `addTrack`s it to every viewer's `RTCPeerConnection`. Per-viewer quality requires either simulcast + an SFU (new infrastructure, explicitly banned by "no media server") or `RTCRtpSender.setParameters({encodings:[{scaleResolutionDownBy}]})`, which changes the encoding for **all** viewers at once — that's a broadcaster control, not a viewer control, and misleading UX. Receiver-side, a viewer cannot request a different resolution of an already-encoded track.
- **Alternatives considered**: (a) SFU (Janus/mediasoup) — rejected: heavy dependency, deployment change; (b) broadcaster-side global quality knob — rejected: doesn't satisfy the "viewer chooses" story and adds renegotiation complexity; (c) `video.requestVideoFrameCallback` tricks — irrelevant to bandwidth/quality.

## R2. Volume/mute on audio-less streams → native properties, future-proof

- **Decision**: Bind a slider to `video.volume` and a toggle to `video.muted` on `#remoteVideo`.
- **Rationale**: 003 captures with `audio: false`, so no audio track exists today; setting `volume`/`muted` on such an element is spec-legal and inert. The controls become functional the moment a future capture adds audio — zero rework. Also note `muted=true` initially is browser-autoplay-friendly if audio ever arrives.
- **Alternatives considered**: hiding controls until an audio track exists (`video.srcObject.getAudioTracks()`) — rejected: spec (US4) wants the standard affordance visible now; conditional UI is more code for less consistency.

## R3. Bullet delivery: cursor polling, NOT consume-on-read

- **Decision**: `GET /api/streams/<uuid>/bullets/?after=<id>` returns rows `id > after`, ordered by `id`, capped at 50; rows are never deleted on read. Client remembers the last seen `id` as its cursor. A `?latest=1` form returns only the current max id for bootstrap.
- **Rationale**: The signaling relay deletes on read because each signal has exactly one addressee. Bullets have N readers — consume-on-read would deliver each message to exactly one lucky poller. Auto-increment `id` is a perfect monotonic cursor (no timestamp-collision issues); the existing `StreamSignal` polling cadence (~1.5–3 s) proves short polling is acceptable on this deployment (WSGI, classroom scale).
- **Alternatives considered**: (a) WebSockets/Channels — rejected by feature constraints; (b) `created_at`-based cursor — rejected: same-millisecond ties can drop or duplicate messages; (c) reusing `StreamSignal` with a new kind — rejected: wrong lifecycle (signals are purged on end and TTL-swept; bullets are persistent content) and wrong read semantics.

## R4. XSS safety end-to-end → store raw, render inert

- **Decision**: Store content as plain text (stripped, ≤200 chars) without HTML-encoding at write time; serve via DRF JSON; render in the overlay **exclusively** with `textContent`. Automated test posts `<script>alert(1)</script>`, asserts the API echoes it as a JSON string (DRF gives `<script>`-safe JSON anyway) and that it lands in the DB verbatim; a second assertion greps rendering code paths (no `innerHTML` in `bullets.js`).
- **Rationale**: Encoding at storage (e.g. `django.utils.html.escape` before save) double-escapes when content is later serialized or shown in Django templates, and hides the real length from the 200-char cap. The only render surface is the JS overlay — making it `textContent`-only is both necessary and sufficient. This matches how the rest of the page handles user data (`screenshare.js` uses `textContent` everywhere).
- **Alternatives considered**: server-side `bleach`/sanitizer dependency — rejected: heavy dependency for a plain-text field; escape-on-write — rejected as above.

## R5. Ended/unknown stream semantics → mirror the signaling API

- **Decision**: POST or GET bullets on an ended stream → **410 Gone**; unknown uuid → **404**; unauthenticated → 401/403 (dual-auth). GET is allowed for any authenticated user on a live stream (viewers and owner alike — US2 needs the owner polling too).
- **Rationale**: 003 established exactly these semantics for `/signals/`; the page code and tests already speak this dialect. One difference: on 410 the bullets client only disables sending/polling for bullets — the player's own ended-state handling (via signaling/stream GET) remains the single owner of the big UI transition (FR-011: don't disturb existing behavior).

## R6. Overlay animation approach → CSS keyframes + fixed lanes

- **Decision**: One absolutely-positioned `#bulletOverlay` div inside `.stream-player` with `pointer-events: none; overflow: hidden`. Each message becomes a `<span>` placed in one of 6 fixed-height lanes (CSS custom property `--lane`), animated with a single `transform: translateX` keyframe animation (GPU-composited), duration ~8–12 s scaled by text length, removed on `animationend`. Lane assignment: least-recently-used; if all lanes were used within a threshold, drop the bullet from display (still stored/delivered — display-only shedding).
- **Rationale**: CSS transform animation runs on the compositor and won't jank the WebRTC `<video>`; `requestAnimationFrame`-driven JS positioning was rejected as more code and more main-thread work. `pointer-events: none` guarantees FR-007 (controls stay clickable) with zero z-index gymnastics. The fullscreen container is `#streamPlayer` (003), and the overlay lives inside it, so bullets appear in fullscreen for free.
- **Alternatives considered**: canvas-based danmaku renderer — rejected: much more code, text rendering/accessibility loss; third-party danmaku lib — rejected: new dependency for ~80 lines of JS.

## R7. Controls placement & state gating

- **Decision**: A control bar row directly under the player (`.stream-controls-bar`): volume slider + mute button + display-mode select + curtain toggle; the bullet send form sits beside/below it. Volume/mode controls render for non-owners (viewer player); curtain toggle and send form render for **all** logged-in users (owner sees bullets too, US2). Send form is disabled at ended state; controls are plain server-rendered HTML (constitution V) enhanced by JS.
- **Rationale**: Keeps the existing template structure (badges, share controls, end button untouched); matches existing `.stream-btn` styling; avoids overlaying interactive controls on the video (which would fight `pointer-events: none` on the overlay and the fullscreen button).

## R8. Theater mode mechanics

- **Decision**: `data-display-mode="theater"` on `#streamPlayer` plus a `stream-theater` class on the page container widens the player column (max-width from 960px → ~1280px) while keeping the 16:9 ratio; Fit/Fill toggle `object-fit` (`contain`/`cover`) on the videos; Auto = Fit (current default look).
- **Rationale**: Pure CSS, reversible, coexists with `:fullscreen` (fullscreen styles already drop the aspect-ratio box); no layout thrash on the WebRTC element (object-fit does not renegotiate anything).
