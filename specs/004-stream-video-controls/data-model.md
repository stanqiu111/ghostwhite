# Data Model: Stream Video Controls and Bullet Curtain

**Feature**: 004-stream-video-controls | **Date**: 2026-07-06

Only one new entity. Volume/mute/display-mode/curtain-toggle are per-visit client state (spec Assumptions) — deliberately **not** persisted.

## StreamBulletMessage (new)

One short live comment ("bullet") on a stream. Persistent content — unlike `StreamSignal`, rows are **not** consumed on read, not purged when the stream ends, and have no TTL.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | BigAutoField (implicit) | PK | Doubles as the **polling cursor** — monotonic, gap-tolerant |
| `stream` | FK → `streams.Stream` | `on_delete=CASCADE`, `related_name="bullets"` | Which stream the message belongs to |
| `sender` | FK → `authors.Author` | `on_delete=CASCADE`, `related_name="+"` | Who sent it; no reverse accessor needed (matches `StreamSignal.sender`) |
| `content` | CharField(120) | required; serializer strips whitespace and rejects empty | Stored as the raw text the user typed (length-capped); **never** HTML-encoded at rest (see research R4) |
| `created_at` | DateTimeField | `auto_now_add=True` | Display/audit only — ordering and cursors use `id` |

### Meta

- `ordering = ["id"]` — insertion order; ties impossible (vs. `created_at`)
- Index: `("stream", "id")`, name `bullet_cursor_idx` — the poll query is exactly `WHERE stream_id = ? AND id > ? ORDER BY id LIMIT 50`

### Validation rules (serializer-owned, constitution IV)

- `content`: strip → must be non-empty → `len ≤ 120` (CharField max_length enforces at DB level too)
- `stream`, `sender`: injected server-side from URL + `request.user` via serializer context — **never client-writable**
- Liveness is a view-level routing concern (mirrors `StreamSignalView`): ended stream → 410 before the serializer runs; unknown → 404

### Lifecycle & state

- Created only while `stream.status == "live"`; immutable afterwards (no edit/delete endpoints in v1)
- Survives stream end (it's content, like a comment); `Stream.end()` purges **signals only** — bullets are untouched
- Cascade-deleted with its stream or sender

### Relationships

```text
Stream 1 ──── * StreamBulletMessage * ──── 1 Author
        (related_name="bullets")   (related_name="+")
```

### What is deliberately NOT modeled

- No FQID/`type` identity for bullets — they are page-local overlay content, not federated objects (contrast: `Stream` has an FQID). If federation ever needs them, an FQID can be added then (constitution VIII).
- No read receipts, likes, moderation flags, or per-user overlay preferences.

## Migration

`streams/migrations/0003_streambulletmessage.py` — single `CreateModel` + index. No changes to existing tables.
