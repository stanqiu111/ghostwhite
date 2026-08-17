# Data Model: Live Stream Feature

**Date**: 2026-07-06 | **Plan**: [plan.md](plan.md)

## Entity: Stream (`streams.Stream`)

One broadcast session owned by one local Author. Table: `streams_stream`.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `CharField(max_length=512, primary_key=True)` | PK | FQID URL: `{host}/api/authors/{author_serial}/streams/{uuid}`. Assigned in `save()` via `utils.fqid.build_stream_fqid()` when empty. Mirrors `Entry.id`. |
| `owner` | `ForeignKey(Author, on_delete=CASCADE, related_name="streams")` | required | The streamer. `AUTH_USER_MODEL` is `authors.Author`. |
| `node` | `ForeignKey(Node, on_delete=CASCADE, related_name="streams")` | required | Origin node; always the local node in MVP. Federation-readiness (mirrors `Entry.node`). |
| `title` | `CharField(max_length=200)` | required, non-blank | Validated in serializer: stripped, non-empty. |
| `description` | `TextField(blank=True, default="")` | optional | |
| `status` | `CharField(max_length=10, choices=[("live","Live"),("ended","Ended")], default="live")` | required | Only two states in MVP. |
| `started_at` | `DateTimeField(auto_now_add=True)` | set on create | Spec "start time". |
| `ended_at` | `DateTimeField(null=True, blank=True)` | null until ended | Spec "optional end time". |

### Meta

```python
class Meta:
    ordering = ["-started_at"]
    constraints = [
        models.UniqueConstraint(
            fields=["owner"],
            condition=Q(status="live"),
            name="unique_live_stream_per_owner",
        )
    ]
    indexes = [
        models.Index(fields=["status", "started_at"], name="stream_status_started_idx"),
    ]
```

### Model behavior

| Member | Behavior |
|---|---|
| `save()` | If `id` empty: generate `uuid4`, build FQID via `build_stream_fqid(owner.id, uuid)`; fall back like `Entry.save()` does. |
| `end()` | If `status == "live"`: set `status="ended"`, `ended_at=timezone.now()`, save. If already ended: no-op (idempotent, FR-011). Returns self. |
| `serial` (property) | UUID segment extracted from `id` FQID — used in URLs and API `serial` field (constitution VII). |
| `is_live` (property) | `status == "live"` — template convenience. |
| `get_absolute_url()` | `/streams/{serial}/` — reader page (mirrors `Entry.get_absolute_url`). |

### State transitions

```
 (create, serializer)          (end(), owner only)
 ───────────────────►  live  ─────────────────────►  ended
                        ▲                              │
                        └── no transition back ────────┘
                            end() on ended = no-op
```

### Validation rules (serializer — constitution IV)

1. `title`: required, stripped, 1–200 chars → 400 with message otherwise (FR-001, FR-012).
2. One live stream per owner: `Stream.objects.filter(owner=user, status="live").exists()` → 400 "You already have a live stream." (FR-003). DB partial unique constraint is the race backstop.
3. `owner`, `node`, `status`, `started_at` are never client-writable — set server-side in `create()`.

### Relationships

- `Author 1 ── * Stream` (`author.streams`) — at most one with `status="live"` (partial unique constraint).
- `Node 1 ── * Stream` (`node.streams`) — always local node in MVP.

### FQID helpers added to `utils/fqid.py`

- `build_stream_fqid(author_id, stream_uuid)` → `{host}api/authors/{author_serial}/streams/{stream_uuid}` (parallel to `build_entry_fqid`).
- `extract_stream_id_from_fqid(fqid)` → UUID string after `/streams/` (parallel to `extract_entry_id_from_fqid`).
