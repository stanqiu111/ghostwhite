# Inbox API Flow

## Overview

The inbox endpoint (`POST /api/authors/{author_id}/inbox/`) lets nodes talk to each other.

**Two directions:**
- **Incoming**: Other nodes send us notifications when their users do something (like, comment, follow, etc.)
- **Outgoing**: We send notifications to other nodes when our users do something

**How it works:**
1. User does something on one node
2. That node sends a POST to the other node's inbox
3. The receiving node saves the data locally
4. It shows up in their UI

---

## 1. Who Sends Requests?

Other nodes (not our frontend) send POST requests to our inbox when:
- Their user comments on our post
- Their user likes our post/comment
- Their user follows our author
- Their user creates/updates/deletes entries we should see

---

## 2. How We Send Notifications

We use helper functions in `utils/node_communication.py`:

- `send_entry_to_remote_nodes(entry)` - Sends entry to remote followers
- `send_like_to_remote_node(like, entry)` - Sends like to entry/comment author
- `send_comment_to_remote_node(comment, entry)` - Sends comment to entry author
- `send_comment_like_to_remote_node(comment_like)` - Sends like to comment author
- `send_follow_request_to_remote_node(follow)` - Sends follow request to followee
- `send_follow_decision_to_remote_node(follow, decision)` - Sends accept/deny to follower

**How they work:**
1. Build the payload (data to send)
2. Find the target node and author
3. Call `send_to_inbox()` which:
   - Builds the URL: `{node_url}/api/authors/{author_id}/inbox/`
   - Sends POST with HTTP Basic Auth
   - Logs errors but doesn't crash

**Who gets notified:**
- **Entries**: All remote followers (based on visibility)
- **Likes**: Entry/comment author (if remote)
- **Comments**: Entry author (if remote)
- **Follow requests**: The followee (person being followed)
- **Follow decisions**: The follower (person who made the request)

---

## 3. What Our Inbox Does

### Authentication

- Uses HTTP Basic Auth (username/password in header)
- Looks up the `Node` object with matching credentials
- Only nodes can call this endpoint (not regular users)

### Routing

The inbox looks at the `type` field and calls the right handler:
- `"entry"` → `_handle_entry()`
- `"follow"` → `_handle_follow()`
- `"like"` → `_handle_like()`
- `"comment"` → `_handle_comment()`

### What Each Handler Does

1. Gets the remote author (creates if needed)
2. Finds the entry/comment (if referenced)
3. Creates/updates local database records
4. Returns success or error

---

## 4. Key Helper Functions

### `get_remote_author_from_json_data(actor_data)`

Gets or creates a remote author in our database. We need this because:
- We need to store remote users locally
- So we can show their name/avatar
- So we can link to their profile
- So we can track who did what

**How it works:**
1. Gets author ID from the data
2. Parses it to get UUID and node URL
3. Finds or creates the Node
4. Finds or creates the Author with that UUID
5. Updates name/github if changed

### `find_entry_by_url(entry_url)`

Finds an entry by its URL. Tries:
1. Look up by `source_url` (for remote entries we already have)
2. Parse the URL to get entry ID and author ID
3. Look up by those IDs

### `find_comment_by_url(comment_url)`

Same as `find_entry_by_url` but for comments.

---

## 5. When We Notify Other Nodes

### Entries

- **Create**: After saving, send to all remote followers
- **Update**: After saving, send updated entry
- **Delete**: After soft-deleting, send with `visibility="DELETED"`

### Likes

- **Like**: Send to entry/comment author (if remote)
- **Unlike**: Send with `removed=True` to entry/comment author

### Comments

- **Create**: Send to entry author (if remote)
- **Update**: Send with `state="updated"` to entry author
- **Delete**: Send with `state="deleted"` to entry author

### Follows

- **Request**: Create `Follow(status=PENDING)`, send to followee
- **Accept**: Update to `ACCEPTED`, send to follower
- **Deny**: Update to `DENIED`, delete locally, send to follower
- **Unfollow**: Delete locally (no notification)

**Important**: When denying, we delete the relationship locally so rejected requests don't clutter the database. The requester's side keeps it as `DENIED` so they know they were rejected.

---

## 6. Follow Request Flow

### Local User Requests to Follow Remote User

1. User A (local) clicks follow on User B (remote)
2. We create `Follow(follower=A, following=B, status=PENDING)`
3. We send notification to User B's inbox
4. User B's node creates the same relationship
5. User B sees the request

### Remote User Requests to Follow Local User

1. User A (remote) requests to follow User B (local)
2. User A's node sends notification to our inbox
3. We create `Follow(follower=A, following=B, status=PENDING)`
4. User B sees the request

### Accepting a Request

1. User B accepts User A's request
2. We update: `status=ACCEPTED, approved=True`
3. We send notification to User A's inbox
4. User A's node updates their relationship to `ACCEPTED`
5. Both sides now show "Following"

### Rejecting a Request

1. User B rejects User A's request
2. We update: `status=DENIED, approved=False`
3. We **delete the relationship locally**
4. We send notification to User A's inbox
5. User A's node updates their relationship to `DENIED`
6. User A can request again later

### Edge Cases

**Unfollow then follow again:**
- Old relationship might still exist on remote node
- When new request arrives, reset `ACCEPTED` → `PENDING`

**Reject then request again:**
- Local side: Reset `DENIED` → `PENDING` and send notification
- Remote side: Reset `DENIED` → `PENDING` when request arrives

**Important points:**
- Each node keeps its own copy of the relationship
- When accepting, both sides update to `ACCEPTED`
- When rejecting, followee deletes locally, follower keeps as `DENIED`
- When retrying, always send notification to remote node

---

## 7. Error Handling

**Sending:**
- Errors are logged but don't stop the user's action
- If notification fails, the create/update/delete still works

**Receiving:**
- Returns 200/201 on success
- Returns 400 for bad data
- Returns 404 if entry/comment not found
- Errors are logged but don't crash the server

---

## 8. Recipient Selection

**Entries:**
- `PUBLIC`: All remote followers
- `FRIENDS_ONLY`: Only mutual followers
- `UNLISTED`: All remote followers (not public)
- `DELETED`: All remote followers (they already got it)

**Likes/Comments:**
- Always sent to the author (if remote)

**Follows:**
- Requests → sent to followee
- Decisions → sent to follower

---

## 9. Example Flow

**Remote user comments on your post:**

1. Remote user comments (on their node)
2. Their node builds payload with comment data
3. Their node POSTs to your inbox with HTTP Basic Auth
4. Our inbox authenticates and routes to `_handle_comment()`
5. Handler gets/creates remote author
6. Handler finds your entry
7. Handler creates Comment in our database
8. You visit inbox page → frontend calls `GET /api/inbox/notifications/`
9. Backend returns the comment
10. Frontend shows "X commented on your post"

---

## 10. Main Files

**`inbox/views.py`**
- `InboxPostView` - Main inbox endpoint
- `_handle_entry()`, `_handle_follow()`, `_handle_like()`, `_handle_comment()` - Handlers

**`utils/node_communication.py`**
- `send_to_inbox()` - Sends POST to remote inbox
- `send_entry_to_remote_nodes()`, `send_like_to_remote_node()`, etc. - Notification functions
- `get_or_create_remote_author()` - Creates/updates remote authors

**`utils/inbox_parsing.py`**
- `get_remote_author_from_json_data()` - Gets remote author from payload
- `parse_follow_state_from_payload()` - Maps state strings to constants

**`utils/fqid.py`**
- `find_entry_by_url()`, `find_comment_by_url()` - Find objects by URL
- `build_fqid()`, `parse_author_fqid()`, etc. - FQID helpers

**`utils/serializers.py`**
- `serialize_author_for_node_communication()` - Converts Author to API format

**`nodes/authentication.py`**
- `NodeBasicAuthentication` - HTTP Basic Auth for nodes
- `NodeAuthenticated` - Permission class

**`entries/views.py`**
- Entry views call `send_entry_to_remote_nodes()` after create/update/delete
- Like views call `send_like_to_remote_node()` after like/unlike
- Comment views call `send_comment_to_remote_node()` after create/update/delete

**`authors/views.py`**
- `FollowRequestView` - Creates follow requests, calls `send_follow_request_to_remote_node()`
- `FollowDecisionView` - Accepts/denies, calls `send_follow_decision_to_remote_node()`