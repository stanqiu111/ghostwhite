# Ghostwhite — Project Workflow

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [User Registration & Login](#user-registration--login)
3. [Creating & Managing Posts (Entries)](#creating--managing-posts-entries)
4. [Following & Friends](#following--friends)
5. [Likes & Comments](#likes--comments)
6. [Inbox & Feed](#inbox--feed)
7. [Node Federation (Node-to-Node)](#node-federation-node-to-node)
8. [GitHub Integration](#github-integration)
9. [Live Streams](#live-streams)
10. [Visibility Rules](#visibility-rules)
11. [ID System (FQIDs)](#id-system-fqids)

---

## Architecture Overview

```
Browser
  │
  ├── Django Templates (HTML pages)    ← /home/, /entries/<pk>/, /authors/<username>/
  │
  └── REST API (JSON)                  ← /api/...
        │
        ├── JWT Auth          ← regular users (Bearer token)
        └── Basic Auth        ← remote nodes only (username:password)

Django Apps:
  authors      → users, follows, GitHub integration, email verification
  entries      → posts, comments, likes
  nodes        → federated node registry
  inbox        → receives activity from remote nodes, notifications
  streams      → live streams, WebRTC signaling relay, bullet curtain
  utils        → FQID helpers, node communication, inbox parsing
```

---

## User Registration & Login

### Register
```
POST /api/authors/register/
{
  "username": "stan",
  "display_name": "Stan Qiu",
  "password": "...",
  "password2": "...",
  "bio": "...",
  "github_url": "..."
}
```
- Account is created with `is_active=False`, `approved=False`
- **Admin must approve** the account in `/admin/` before the user can log in

### Login
```
POST /api/authors/login/
{ "username": "stan", "password": "..." }

→ { "access": "<JWT>", "refresh": "<JWT>" }
```
- Access token expires in **1 hour**; refresh token in **7 days**
- All authenticated API calls use `Authorization: Bearer <access>`

### Refresh Token
```
POST /api/authors/token/refresh/
{ "refresh": "<JWT>" }
```

---

## Creating & Managing Posts (Entries)

### Create Entry
```
POST /api/entries/create/
{
  "title": "My Post",
  "content": "Hello world",
  "content_type": "text/plain",     ← or text/markdown
  "visibility": "public"            ← public | unlisted | friends_only
}
```
- Entry gets a FQID: `http://<host>/api/authors/<author-uuid>/entries/<entry-uuid>`
- Stored in `Entry` model with `source="manual"`
- **Triggers federation**: sends entry payload to all remote followers' inboxes

### Image Entry
- Upload an image file; server auto-encodes to base64 and sets `content_type` to `image/png;base64` or `image/jpeg;base64`
- Retrieve raw image bytes: `GET /api/authors/<author_id>/entries/<pk>/image/`

### Update Entry
```
PUT /api/entries/<pk>/update/
```
- Only the entry author can update
- Re-sends updated entry to all remote followers

### Delete Entry
```
DELETE /api/entries/<pk>/delete/
```
- **Soft delete**: sets `visibility="DELETED"`, records `deleted_at`
- Not visible to regular users; staff/admin can still see it
- Notifies remote followers to remove their cached copy

### List Entries (Feed)
```
GET /api/entries/          ← paginated, filtered by visibility
```
Filtering logic:
- **public**: visible to all authenticated users
- **unlisted**: visible to followers of the author
- **friends_only**: visible only to mutual followers (friends)
- **DELETED**: only staff/admin

---

## Following & Friends

### Follow States
```
PENDING → ACCEPTED   (approved by followee)
        → DENIED     (rejected; can retry)
```

### Send a Follow Request
```
POST /api/authors/<author_id>/follow/
```
- Creates `Follow(follower=me, following=target, status=PENDING)`
- If target is **remote**: sends follow request to target's inbox

### Accept / Deny
```
POST /api/authors/follows/<id>/decision/
{ "decision": "accept" }   ← or "deny"
```
- Only the followee can decide
- If follower is **remote**: sends decision back to their inbox

### Unfollow
```
DELETE /api/authors/<author_id>/follow/
```
- Deletes the Follow record locally
- If followee is **remote**: sends unfollow notification

### Friends (Mutual Follows)
A "friend" is someone where **both** follow each other with `status=ACCEPTED`.
Used to gate `friends_only` content visibility.

```
Follow.get_friends(author)  →  queryset of mutual followers
```

---

## Likes & Comments

### Like / Unlike an Entry
```
POST   /api/entries/<pk>/like/     ← like
DELETE /api/entries/<pk>/like/     ← unlike
```
- Creates/deletes `EntryLike(entry, author)`
- If entry author is **remote**: sends like notification to their inbox

### Like / Unlike a Comment
```
POST   /api/entries/<pk>/comments/<comment_id>/like/
DELETE /api/entries/<pk>/comments/<comment_id>/like/
```

### Add Comment
```
POST /api/entries/<pk>/addcomments/
{ "content": "Great post!" }
```
- Comment gets a FQID: `http://<host>/api/authors/<author-uuid>/commented/<comment-uuid>`
- If entry author is **remote**: sends comment to their inbox

### Edit / Delete Comment
```
PATCH  /api/entries/<pk>/comments/<comment_id>/
DELETE /api/entries/<pk>/comments/<comment_id>/
```
- PATCH sends `state="updated"` to remote node
- DELETE sends `state="deleted"` to remote node

---

## Inbox & Feed

### Receiving Remote Activity
```
POST /api/authors/<author_id>/inbox
Authorization: Basic <node-credentials>
```
Remote nodes POST activity objects here. Routed by `type` field:

| `type`    | What happens                                              |
|-----------|-----------------------------------------------------------|
| `entry`   | Create/update/soft-delete local copy of remote entry      |
| `follow`  | Create/update Follow record (pending/accepted/denied/unfollow) |
| `like`    | Create/delete EntryLike or CommentLike                    |
| `comment` | Create/update/delete Comment                              |
| `author`  | Update cached remote author profile                       |

### Notifications (for logged-in user)
```
GET /api/inbox/notifications/?limit=20
```
Returns likes and comments on **my** entries — newest first.

### Following Activity
```
GET /api/inbox/following-activity/?limit=20
```
Returns activity (entries, likes, comments) from **authors I follow** — newest first.

### Inbox Page
`/inbox/` — UI showing both streams combined.

---

## Node Federation (Node-to-Node)

### Node Registry
Nodes are registered in the `Node` model with:
- `host_url`: base URL of the remote node
- `username` / `password`: Basic Auth credentials this node uses to talk to that remote

### How Outgoing Messages Work
All federation goes through `utils/node_communication.py`:

```
Action (local user)
  ↓
View sends notification
  ↓
send_to_inbox(payload, remote_node, target_author_fqid)
  ↓
POST <remote_host>/api/authors/<author_id>/inbox
Authorization: Basic <username>:<password>
Content-Type: application/json
```

### Outgoing Payloads

**Entry:**
```json
{
  "type": "entry",
  "id": "http://...",
  "title": "...",
  "content": "...",
  "content_type": "text/plain",
  "visibility": "public",
  "author": { "id": "...", "display_name": "...", ... },
  "created_at": "..."
}
```

**Follow Request:**
```json
{
  "type": "follow",
  "state": "requesting",
  "actor": { "id": "...", "display_name": "..." },
  "object": { "id": "..." }
}
```

**Follow Decision:**
```json
{ "type": "follow", "state": "accepted", "actor": {...}, "object": {...} }
```

**Like:**
```json
{
  "type": "like",
  "author": { "id": "...", ... },
  "object": "http://.../entries/<id>/",
  "removed": false
}
```

**Comment:**
```json
{
  "type": "comment",
  "id": "http://...",
  "author": { "id": "...", ... },
  "content": "...",
  "entry": "http://.../entries/<id>/",
  "state": "updated"
}
```

### Remote Author Caching
When a remote action arrives, `get_or_create_remote_author()` is called:
1. Check if Author with that FQID already exists locally
2. If not, fetch profile from remote node
3. Create/update local Author record (marked as belonging to remote Node)
4. Used for display everywhere without hitting remote node on every request

---

## GitHub Integration

### Setup
User sets a `github_url` in their profile and creates a `GitHubIntegration` record with their GitHub username (and optionally a personal access token for higher rate limits).

### Sync
```
POST /api/authors/sync-repos/   ← triggers sync for current user
GET  /authors/sync-repos/       ← UI page
```

### What Gets Imported
GitHub public events are fetched and converted to `Entry` objects:

| GitHub Event       | Entry Content                          |
|--------------------|----------------------------------------|
| `PushEvent`        | "Pushed X commits to `repo`"           |
| `PullRequestEvent` | "Opened/closed PR #N in `repo`"        |
| `WatchEvent`       | "Starred `repo`"                       |
| `CreateEvent`      | "Created branch/tag in `repo`"         |

- `source="github"`, `source_id=<github_event_id>` (prevents duplicates)
- `visibility="public"`, `content_type="text/markdown"`
- `last_synced_at` updated after each successful sync

---

## Live Streams

Lifecycle MVP built with spec-kit (`specs/002-live-stream/`); screen-sharing added in `specs/003-screen-share/` and optional microphone commentary in `specs/005-stream-microphone/`. Video and commentary use **WebRTC** between browsers, with the server acting as a **REST signaling relay** (short polling, no Django Channels or media server). Screen sharing starts with the microphone off. No federation of streams yet, but IDs are FQID-based so it can be added without migration.

### Stream Model (`streams` app)
- FQID pk: `http://<host>/api/authors/<author-uuid>/streams/<stream-uuid>`
- `owner` (Author FK), `node` (Node FK), `title`, `description`, `status` (`live`/`ended`), `started_at`, `ended_at`
- DB partial unique constraint: **at most one live stream per owner**
- `end()` is idempotent — ending an ended stream is a no-op

### API (session or JWT auth, all require login)
```
GET  /api/streams/                 ← active (live) streams only
POST /api/streams/                 ← start a stream { "title": "...", "description": "..." }
GET  /api/streams/<uuid>/          ← retrieve (live or ended)
POST /api/streams/<uuid>/end/      ← end stream (owner only → 403 otherwise; idempotent)
```
- Validation lives in `StreamSerializer`: title required, "You already have a live stream." on a second live stream
- Response shape follows the platform contract: `type: "stream"`, `id` = FQID, `serial` = UUID
- Ending a stream also **purges all queued signaling messages** for it

### Screen-Share Signaling API (WebRTC relay)
```
POST /api/streams/<uuid>/signals/                      ← send one signal
GET  /api/streams/<uuid>/signals/?role=streamer        ← owner polls inbound signals (403 for non-owners)
GET  /api/streams/<uuid>/signals/?role=viewer&peer_id= ← viewer polls signals addressed to its peer_id
```
- POST body: `{ "kind": "join|offer|answer|candidate|bye", "direction": "to_streamer|to_viewer", "peer_id": "<≤64 chars>", "payload": { … ≤32 KB } }`
- **Owner-only broadcasting enforced server-side**: `direction=to_viewer` from a non-owner → 403 (`StreamSignalSerializer`); kind/direction coherence (`offer`→to_viewer, `join`/`answer`→to_streamer) → 400
- **Ended stream → 410 Gone** on both POST and GET; unknown stream → 404
- Polling is **consume-on-read** (each signal delivered exactly once, inside `transaction.atomic()`), plus a 5-minute TTL sweep of stale rows on every poll
- `StreamSignal` rows are ephemeral transport — FK `stream`/`sender` injected server-side, never client-writable, never exposed with FQIDs

### Bullet Curtain (danmaku) API (`specs/004-stream-video-controls/`)
```
POST /api/streams/<uuid>/bullets/               ← send { "content": "≤120 chars" } → 201
GET  /api/streams/<uuid>/bullets/?after=<id>    ← cursor poll: rows with id > after, ascending, ≤50
GET  /api/streams/<uuid>/bullets/?latest=1      ← bootstrap: 30 most recent (ascending) + cursor
```
- `StreamBulletMessage`: persistent content (stream FK, sender FK, content ≤120, created_at; index `bullet_cursor_idx`) — **NOT consumed on read** (broadcast, every watcher polls with its own id cursor) and **NOT purged on stream end** (kept as interaction history)
- Ended stream → **410** both verbs; unknown → 404; unauthenticated → 401/403; empty/oversized content → 400 (`StreamBulletMessageSerializer`)
- XSS: content stored raw and returned verbatim as JSON; rendering is `textContent`-only in `bullets.js` — never HTML

### Player Controls & Overlay (browser)
- `bullets.js` — `BulletCurtain`: 1.5 s cursor polling, 6 overlay lanes (3 on narrow screens, LRU-assigned, overflow shed from display only), CSS-transform fly-across animation, send form with ≥1 s client throttle, curtain on/off toggle (off = display only; cursor keeps advancing so re-enable shows only new messages). Overlay is `pointer-events: none` — can never block controls. Fully isolated from `screenshare.js`.
- The stream detail room also displays those real messages in a chat rail: latest 30 on load, at most 100 retained DOM messages, literal text rendering, preserved reading position, and a latest-message action. The overlay toggle does not disable chat. `stream_room.css` scopes the responsive room layout; `stream_room.js` mirrors existing media state without changing capture or signaling. No audience metric is inferred from the global live-room count.
- `player_controls.js` — volume slider + local mute appear when the owner reports microphone availability. A reserved audio track alone does not show them. Viewer preferences survive microphone changes and reconnects. If audible playback is blocked, video continues muted and an **Enable sound** action is offered. Display modes Auto/Fit/Fill (object-fit) and Theater remain CSS-only and fullscreen-compatible.

### Screen-Share Browser Flow (`streams/static/streams/`)
- `signaling.js` — transport only: `postSignal()` / `pollSignals()` with CSRF + optional JWT header; 410 → typed `StreamEndedError`. Swap this file to move to WebSockets later.
- `screenshare.js` — `Broadcaster` (owner): `getDisplayMedia({video, audio:false})` → local preview + On-air badge; one `RTCPeerConnection` per viewer (P2P mesh, Google STUN); polls `role=streamer` every 1.5 s; on `join` → offer, trickle ICE; Stop button, browser-native stop bar, End-stream button, and `beforeunload` all funnel into `stop()` (close PCs + `bye` per peer).
- `screenshare.js` — `Player` (viewer): random `peer_id`, `join` heartbeat every 10 s while waiting; state machine **waiting → connecting → live** (+ `ended`, `error` with Retry); on `bye`/PC drop while the stream is still live → back to waiting; on 410 → confirm via stream GET → ended state without reload.
- Owner controls (`Share screen`) render server-side only for the owner of a live stream.

### Optional Microphone Commentary (`specs/005-stream-microphone/`)
- `microphone.js` owns a separate microphone capture stream. After screen sharing starts, the owner explicitly selects **Enable microphone**; capture is never requested for viewers or automatically on a new broadcast.
- Each initial peer connection reserves a send-only audio transceiver. Enabling/retrying commentary uses `replaceTrack()` on that sender, preserving the video sender and avoiding renegotiation. One microphone track is shared across viewer senders; disabling it mutes both current and later viewers without another permission request.
- A reliable `commentary` data channel carries only `{type: "microphone", available: boolean}`. The owner sends the current snapshot on open and after sender changes. The existing authenticated signaling API and database schema are unchanged.
- Denial, missing/unusable devices and lost access show microphone-specific feedback while screen video continues. Recovery requires **Retry microphone**. Mute retains capture; stop/end/page departure releases it.
- Generation guards discard and release late permission grants after stop/restart. Sender replacements are serialized per peer so cleanup cannot be overwritten by an older attachment. The owner's local preview remains muted.
- Tab/system audio, recording, device menus and audio-only broadcasts are outside this feature.

### Pages
```
/streams/            ← live-now grid, empty state, "Go live" button
/streams/create/     ← start-stream form (server-rendered POST)
/streams/<uuid>/     ← detail: streamer, title, description, Live/Ended badge,
                       placeholder player <div data-stream-serial> (media extension point),
                       End button rendered server-side only for the owner
```
- "Live" button in the home header links to `/streams/`
- Ended streams disappear from the active list but their detail pages stay reachable

### Tests
`streams/tests.py` — 78 passing real-DB tests, including three microphone page/access tests. Existing coverage includes model lifecycle, API and page permissions, signaling/scoping/consume-on-read, hijack attempts, end-purge/TTL, and bullet validation/rendering.

`node --test streams/js_tests/*.test.cjs` runs 21 simulated media lifecycle/playback regressions. `python streams/browser_tests/media.py` runs the native Chromium multi-viewer media harness against temporary SQLite; `--baseline` serves pre-feature commit `1eb0a5bb933dbd7b632864da2dc2f90c3bb51e4a`'s stream template/JS without changing the checkout, and `--capture-only` exercises native synthetic capture plus explicitly labeled injected failures without requiring media transport. The harness uses SQLite IMMEDIATE transactions to avoid concurrent read-to-write lock upgrades; application database settings are unchanged.

See `specs/005-stream-microphone/validation.md` for exact outcomes. The managed cloud Chromium policy currently prevents ICE candidates, blocking actual media delivery even in the pre-feature baseline. Synthetic capture and injected failures do not establish physical microphone, permission-dialog, speaker-output, or multi-viewer transport behavior. The feature 004 T020 manual walkthrough remains outstanding where it depends on those capabilities.

`python streams/browser_tests/media.py --ui-check` verifies the live-room UI and writes neutral screenshots. Viewer live/error presentation is explicitly simulated; chat and server actions use the real isolated app. See `docs/LIVE_ROOM_UI.md` for first-version review results and remaining local QA.

---

## Visibility Rules

| Visibility     | Who can see it                                |
|----------------|-----------------------------------------------|
| `public`       | All authenticated users + remote nodes        |
| `unlisted`     | Only followers of the author                  |
| `friends_only` | Only mutual followers (both status=ACCEPTED)  |
| `DELETED`      | Only staff/admin (soft-deleted)               |

These rules are enforced in:
- `EntryListView` (feed filtering)
- `EntryRetrieveView` (single entry access)
- Comment visibility (inherits from parent entry)
- Federation send logic (only sends to eligible followers)

---

## ID System (FQIDs)

All objects use Fully Qualified IDs (FQIDs) to work across nodes.

| Object  | FQID Format                                                        |
|---------|--------------------------------------------------------------------|
| Author  | `http://<host>/api/authors/<uuid>`                                 |
| Entry   | `http://<host>/api/authors/<author-uuid>/entries/<entry-uuid>`     |
| Comment | `http://<host>/api/authors/<author-uuid>/commented/<comment-uuid>` |
| Stream  | `http://<host>/api/authors/<author-uuid>/streams/<stream-uuid>`    |

Utilities in `utils/fqid.py`:
- `build_fqid(author_id)` — build author FQID
- `build_entry_fqid(author_id, entry_uuid)` — build entry FQID
- `build_comment_fqid(author_id, comment_uuid)` — build comment FQID
- `extract_entry_id_from_fqid(fqid)` — parse UUID from FQID

The local node's `host_url` (stored in `Node` where `is_local=True`) is used as the base for all local FQIDs.
