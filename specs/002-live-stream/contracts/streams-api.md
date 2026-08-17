# API Contract: Streams

**Date**: 2026-07-06 | **Plan**: [../plan.md](../plan.md)

All endpoints accept **both** Django session auth and JWT `Bearer` auth (constitution II).
All object shapes follow constitution VII: `id` is the full FQID URL, `serial` is the UUID shorthand.

## Stream object (response shape)

```json
{
  "type": "stream",
  "id": "http://127.0.0.1:8000/api/authors/6d195ae4-.../streams/9f2c41aa-...",
  "serial": "9f2c41aa-...",
  "owner": {
    "type": "author",
    "id": "http://127.0.0.1:8000/api/authors/6d195ae4-...",
    "displayName": "stan",
    "...": "existing AuthorSerializer shape"
  },
  "title": "Friday night coding",
  "description": "Building the streams app live",
  "status": "live",
  "startedAt": "2026-07-06T20:00:00Z",
  "endedAt": null,
  "webUrl": "http://127.0.0.1:8000/streams/9f2c41aa-.../"
}
```

## Endpoints

### 1. List active streams

```
GET /api/streams/
```

| | |
|---|---|
| Auth | required (session or JWT) → 401 otherwise |
| Returns | 200 — `{"type": "streams", "items": [Stream, ...]}` only `status="live"`, newest first |
| Notes | One query with `select_related("owner")`. Ended streams never appear (FR-004, FR-008). |

### 2. Create (start) a stream

```
POST /api/streams/
Content-Type: application/json
{"title": "Friday night coding", "description": "optional"}
```

| Status | When |
|---|---|
| 201 → Stream object | valid title, no live stream for this user |
| 400 `{"title": [...]}` | missing/blank/too-long title (FR-012) |
| 400 `{"detail": "You already have a live stream."}` | owner already live (FR-003) |
| 401 | not authenticated (FR-009) |

Server sets `owner=request.user`, `node=local`, `status="live"`, `startedAt=now`. Client cannot set them.

### 3. Retrieve a stream

```
GET /api/streams/<uuid:serial>/
```

| Status | When |
|---|---|
| 200 → Stream object | exists (live **or** ended — detail stays reachable, FR-008) |
| 401 | not authenticated |
| 404 | unknown serial |

### 4. End a stream

```
POST /api/streams/<uuid:serial>/end/
```

| Status | When |
|---|---|
| 200 → Stream object (`status="ended"`, `endedAt` set) | caller is owner; idempotent — repeat calls return 200 with the original `endedAt` (FR-011) |
| 403 `{"detail": "Only the stream owner can end this stream."}` | authenticated non-owner (FR-007) |
| 401 | not authenticated |
| 404 | unknown serial |

## Template pages (server-rendered, session auth)

| Route | View behavior |
|---|---|
| `GET /streams/` | List active streams. Unauthenticated → redirect `authors_pages:auth_page` (FR-009). |
| `GET /streams/create/` | Start-stream form. Unauthenticated → redirect login. |
| `POST /streams/create/` | Form submit → create via serializer → redirect to detail page. Invalid → re-render form with errors. |
| `GET /streams/<uuid:serial>/` | Detail: owner, title, description, status, times, placeholder player. Context includes `is_owner` (constitution V); End button rendered only for owner. Unknown serial → 404. |
