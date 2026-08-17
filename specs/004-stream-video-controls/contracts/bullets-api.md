# API Contract: Bullet Messages

**Feature**: 004-stream-video-controls | **Date**: 2026-07-06

One URL, two verbs, registered in `streams/urls.py`:

```text
/api/streams/<uuid:pk>/bullets/
```

`<uuid:pk>` is the stream **serial** (UUID shorthand), same convention as `/signals/` and `/end/`.

## §1 Authentication (both verbs)

- `authentication_classes = [JWTAuthentication, SessionAuthentication]` (constitution II)
- `permission_classes = [IsAuthenticated]`
- Unauthenticated → **401** (JWT clients) or **403** (session/CSRF path) — tests accept either, matching the existing suite.

## §2 Common error routing (both verbs)

| Condition | Status | Body |
|---|---|---|
| Unknown stream uuid | **404** | DRF default detail |
| Stream ended | **410** | `{"detail": "Stream has ended."}` |

The 410 check runs before any other processing (mirrors `StreamSignalView`).

## §3 POST — send a bullet message

Request (JSON):

```json
{ "content": "hello from the audience!" }
```

| Rule | Failure status |
|---|---|
| `content` present, non-empty after strip | 400 |
| `content` ≤ 120 chars (after strip) | 400 |
| Any authenticated user may post (owner included) | — |

`stream` and `sender` are server-injected; any client-supplied values for them are ignored.

Response **201**:

```json
{
  "type": "bullet",
  "id": 42,
  "content": "hello from the audience!",
  "sender": {"serial": "<author-uuid>", "displayName": "alice"},
  "created_at": "2026-07-06T20:00:00Z"
}
```

Content round-trips **verbatim** — `<script>alert(1)</script>` in yields the identical JSON string out (rendering safety is the client's `textContent` duty; see research R4).

## §4 GET — cursor poll

Query parameters (exactly one mode):

| Mode | Params | Returns |
|---|---|---|
| Poll | `after=<int>` | Up to **50** bullets with `id > after`, ordered by `id` ascending |
| Bootstrap | `latest=1` | The **30 most recent** bullets (ascending) + current cursor |

Poll response **200**:

```json
{
  "type": "bullets",
  "items": [
    {"id": 43, "content": "hi!", "sender": {"serial": "…", "displayName": "bob"}, "created_at": "…"}
  ],
  "cursor": 43
}
```

- `cursor` = highest `id` in `items`, or the request's `after` when `items` is empty (client always stores `cursor` back).
- Reads are **non-consuming** — every watcher polls independently with their own cursor.
- More than 50 pending → client naturally catches up on subsequent polls (or jumps: display shedding is a client concern).

Bootstrap response **200**:

```json
{ "type": "bullets", "items": [/* up to 30 most recent, ascending by id */], "cursor": 41 }
```

`cursor` = current max bullet id for the stream (0 if none). Implements FR-008: one-time backfill of recent context, then live-only polling — never full history.

Missing/invalid `after` (non-integer, negative) and absent `latest` → **400**.

## §5 Client behavior contract (bullets.js)

- Poll every **1.5 s** while the stream page is open and the stream is live; stop on 410 and disable the send input with an "ended" hint — do **not** touch the player state machine (that belongs to screenshare.js).
- Render message text via `textContent` only. No `innerHTML`, no attribute interpolation of user content.
- Overlay is `pointer-events: none`; curtain toggle only gates **display** — polling continues (cheap, keeps cursor warm) but arriving items are discarded while off.
- Send: POST on form submit; on 201 clear the input; on 400 show the serializer message; throttle sends client-side to ≥1 s apart.
- Reuses the CSRF-cookie + optional-JWT `Authorization` header pattern from `signaling.js` (copied, not imported — modules stay isolated).
