# Contract: Screen-Share Signaling (REST + WebRTC protocol)

**Date**: 2026-07-06 | **Plan**: [../plan.md](../plan.md) | **Data model**: [../data-model.md](../data-model.md)

All endpoints accept **both** Django session auth and JWT `Bearer` auth (constitution II) and require login (401/403 otherwise). Stream addressed by UUID serial, as in 002.

## 1. Send a signal

```
POST /api/streams/<uuid:serial>/signals/
Content-Type: application/json
{
  "kind": "join" | "offer" | "answer" | "candidate" | "bye",
  "direction": "to_streamer" | "to_viewer",
  "peer_id": "<uuidv4 chosen by the viewer client>",
  "payload": { ... }        // sdp for offer/answer, ICE dict for candidate, {} otherwise
}
```

| Status | When |
|---|---|
| 201 `{"type": "signal", "kind": ..., "peer_id": ...}` | accepted |
| 400 | bad kind, kind/direction mismatch (`offer` must be `to_viewer`; `join`/`answer` must be `to_streamer`), missing/oversized fields (payload > 32 KB) |
| 401 | not authenticated |
| **403** | `direction: "to_viewer"` from anyone who is not the stream owner — **the anti-hijack rule** (FR-006) |
| 404 | unknown stream serial |
| **410** | stream has ended — connection setup no longer accepted (FR-008) |

## 2. Poll (and consume) signals

```
GET /api/streams/<uuid:serial>/signals/?role=streamer
GET /api/streams/<uuid:serial>/signals/?role=viewer&peer_id=<uuid>
```

| Status | When |
|---|---|
| 200 `{"type": "signals", "items": [ {kind, peer_id, payload, sender_serial}, ... ]}` | items are returned **once** — they are deleted atomically on read; ordered by creation |
| 400 | missing/invalid `role`, or `role=viewer` without `peer_id` |
| 401 | not authenticated |
| 403 | `role=streamer` requested by a non-owner |
| 404 / 410 | unknown / ended stream |

**Consumption**: a signal is delivered to exactly one poll response and then gone. Clients must not rely on re-reading. Each poll also garbage-collects signals for that stream older than 5 minutes.

## 3. Protocol (client behavior contract)

**Roles**: Broadcaster = stream owner's page while sharing. Player = any viewer's page on a live stream.

| Step | Actor | Action |
|---|---|---|
| P1 | Player | generate `peer_id` (UUIDv4); POST `join` (`to_streamer`); repeat every 10 s while in `waiting` |
| B1 | Broadcaster | poll `role=streamer` every ~1.5 s while sharing; on `join` with unknown `peer_id` → new `RTCPeerConnection`, add `getDisplayMedia` tracks, `createOffer` → POST `offer` (`to_viewer`, that peer_id) |
| P2 | Player | poll `role=viewer` every ~1 s; on `offer` → state `connecting`, `setRemoteDescription`, `createAnswer` → POST `answer` (`to_streamer`) |
| B2/P3 | both | trickle ICE: each local candidate → POST `candidate` (broadcaster: `to_viewer`; player: `to_streamer`); apply received candidates |
| P4 | Player | on `track` + connection `connected` → state `live` (attach stream to `<video>`); poll drops to ~3 s |
| B3 | Broadcaster | on stop sharing (button or browser-native): close all PCs, POST `bye` (`to_viewer`) per peer, stop polling |
| P5 | Player | on `bye` or PC `disconnected/closed/failed` while stream still live → back to `waiting` (new join heartbeat, same or new peer_id) |
| P6 | Player | on poll `410` → fetch stream via `GET /api/streams/<serial>/` → state `ended`, stop all polling |
| P7 | Player | on unrecoverable setup error → state `error` with Retry (Retry = new peer_id, back to P1) |

**ICE config (both sides)**: `{ iceServers: [{ urls: "stun:stun.l.google.com:19302" }] }` — free public STUN; LAN works via host candidates regardless.

## 4. UI contract (stream_detail.html)

| Element | Rendered for | Behavior |
|---|---|---|
| `#shareScreenBtn` | owner + stream live (server-side `is_owner`, constitution V) | starts `getDisplayMedia` → Broadcaster; hidden while sharing |
| `#stopSharingBtn` + on-air badge | owner while sharing | stops broadcast, stream stays live |
| `#localPreview` (`<video muted>`) | owner while sharing | shows captured screen |
| `#remoteVideo` (`<video autoplay playsinline>`) | viewers in `live` state | attached to received `MediaStream` |
| `.stream-player-placeholder` | everyone | carries `waiting` / `connecting` / `ended` / `error` states via `data-player-state` + copy; **unchanged as the fallback/waiting visual** (FR-011) |
| `#retryBtn` | viewers in `error` state | new peer_id, rejoin |
| End stream button (002) | owner | now stops sharing first, then existing end POST |

## 5. Interaction with existing 002 API (unchanged shapes)

- `GET /api/streams/<serial>/` — used by players to confirm `status` after a `410`.
- `POST /api/streams/<serial>/end/` — response shape unchanged; side effect added server-side: purge remaining `StreamSignal` rows for the stream.
