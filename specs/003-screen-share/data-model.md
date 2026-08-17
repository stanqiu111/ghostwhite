# Data Model: Screen-Sharing for Live Streams

**Date**: 2026-07-06 | **Plan**: [plan.md](plan.md)

`Stream` (002) is **unchanged** — no migration risk to the shipped lifecycle. One new ephemeral entity.

## Entity: StreamSignal (`streams.StreamSignal`)

A short-lived, addressed signaling message (WebRTC handshake payload) relayed through the server between the broadcaster and one viewer. Table: `streams_streamsignal`. Rows live seconds-to-minutes: **deleted when read by their addressee**, purged when the stream ends, TTL-swept after 5 minutes.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `BigAutoField` | PK | Internal only — never exposed in API shapes (signals have no FQID; they are transport, not content). |
| `stream` | `ForeignKey(Stream, on_delete=CASCADE, related_name="signals")` | required | Scopes every signal to exactly one stream (FR-007). |
| `sender` | `ForeignKey(Author, on_delete=CASCADE, related_name="+")` | required | Set from `request.user`; used to enforce the direction rule. |
| `direction` | `CharField(max_length=12, choices=[("to_streamer","To streamer"),("to_viewer","To viewer")])` | required | Who may read it. `to_viewer` rows may only be **created** by `stream.owner` (serializer-enforced). |
| `peer_id` | `CharField(max_length=64)` | required | Client-generated UUIDv4 naming one viewer connection; capability token for viewer polls (research R5). |
| `kind` | `CharField(max_length=12, choices=[("join","Join"),("offer","Offer"),("answer","Answer"),("candidate","Candidate"),("bye","Bye")])` | required | Protocol verbs. |
| `payload` | `JSONField(default=dict, blank=True)` | ≤ 32 KB serialized (serializer-enforced) | SDP for offer/answer, ICE candidate dict for candidate, `{}` for join/bye. |
| `created_at` | `DateTimeField(auto_now_add=True)` | | Drives the 5-minute TTL sweep. |

### Meta

```python
class Meta:
    ordering = ["created_at"]          # handshake messages must arrive in order
    indexes = [
        models.Index(
            fields=["stream", "direction", "peer_id"],
            name="signal_route_idx",   # the poll query
        ),
    ]
```

### Validation rules (serializer — constitution IV)

1. `kind` ∈ choices; `peer_id` non-empty, ≤ 64 chars.
2. **Direction rule**: `direction == "to_viewer"` requires `sender == stream.owner` → `PermissionDenied` (403). (FR-006)
3. **Kind/direction coherence**: `offer` must be `to_viewer`; `join`/`answer` must be `to_streamer`; `candidate`/`bye` may go either way (subject to rule 2).
4. **Liveness**: stream must have `status == "live"` → otherwise the view returns `410 Gone`. (FR-008)
5. `payload` serialized size ≤ 32 KB (an SDP is ~5–15 KB; caps abuse).
6. `stream`, `sender` are never client-writable — injected server-side from URL and `request.user`.

### Delivery / consumption semantics (view layer)

| Poll | Query | Access rule |
|---|---|---|
| Broadcaster: `role=streamer` | `filter(stream=s, direction="to_streamer")` | caller must be `stream.owner`, else 403 |
| Viewer: `role=viewer&peer_id=X` | `filter(stream=s, direction="to_viewer", peer_id=X)` | any authenticated user holding the peer_id |

Both polls **delete the returned rows atomically** (`select → serialize → delete` inside a transaction). Each poll also opportunistically deletes signals for that stream older than 5 minutes. Ending a stream deletes all of its remaining signals.

### Message flow (one viewer connection)

```
Viewer                         Server (StreamSignal)                    Broadcaster
  │  POST join {peer_id}  ──────►  to_streamer row                          │
  │        (heartbeat every 10 s while waiting)                             │
  │                                to_streamer rows  ◄──── poll (consume) ──┤
  │                                                     creates RTCPeerConnection,
  │                                                     adds display tracks
  │                                to_viewer offer   ◄──── POST offer ──────┤
  ├── poll (consume) ──────►  offer {sdp}                                   │
  │  setRemote, createAnswer                                                │
  │  POST answer {sdp} ──────►  to_streamer row  ◄──────── poll ────────────┤
  │  POST candidate* ────────►  to_streamer rows ◄──────── poll ────────────┤
  ├── poll ◄──────────────────  to_viewer candidate* ◄──── POST candidate* ─┤
  │                                                                         │
  │◄════════════════ P2P DTLS/SRTP video (no server) ══════════════════════►│
  │                                                                         │
  │  (stop) ◄─────────────────  to_viewer bye  ◄────────── POST bye ────────┤
```

### Relationships

- `Stream 1 ── * StreamSignal` (`stream.signals`) — all deleted on stream end; CASCADE covers stream deletion.
- `Author 1 ── * StreamSignal` (sender; no reverse accessor needed → `related_name="+"`).
