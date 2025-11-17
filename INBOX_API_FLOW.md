# Inbox API Flow

The inbox endpoint (`POST /api/authors/{author_id}/inbox/`) is how nodes communicate with each other. ( under [authors/urls.py](https://github.com/uofa-cmput404/f25-project-ghostwhite/blob/staging/authors/urls.py#L22))

Two directions:
- Incoming: other nodes send us notifications when their users do something
- Outgoing: we send notifications to other nodes when our users do something

Basic flow:
1. User does something on one node
2. That node sends a POST to the other node's inbox
3. Receiving node saves the data locally
4. Shows up in their UI

## Who Sends Requests?

Other nodes (not our frontend) send POST requests to our inbox when:
- Their user comments on our post
- Their user likes our post/comment
- Their user follows our author
- Their user creates/updates/deletes entries we should see

## Sending Notifications

Helper functions in [utils/node_communication.py](https://github.com/uofa-cmput404/f25-project-ghostwhite/blob/staging/utils/node_communication.py):
- `send_entry_to_remote_nodes(entry)` - sends entry to remote followers
- `send_like_to_remote_node(like, entry)` - sends like to entry/comment author
- `send_comment_to_remote_node(comment, entry)` - sends comment to entry author
- `send_comment_like_to_remote_node(comment_like)` - sends like to comment author
- `send_follow_request_to_remote_node(follow)` - sends follow request to followee
- `send_follow_decision_to_remote_node(follow, decision)` - sends accept/deny to follower

They build the payload - theese payloads schema can be found under [API OBJECTS](https://uofa-cmput404.github.io/general/project.html#api-objects), find the target node/author, then call `send_to_inbox()` which builds the URL and sends POST with HTTP Basic Auth. Errors are logged but don't crash.

Who gets notified:
- Entries: all remote followers (based on visibility)
- Likes: entry/comment author (if remote)
- Comments: entry author (if remote)
- Follow requests: the followee
- Follow decisions: the follower

## Receiving Inbox Requests

Authentication uses HTTP Basic Auth - looks up the `Node` object with matching credentials. Only nodes can call this endpoint.

Routing: inbox looks at the `type` field and calls the right handler:
- `"entry"` → `_handle_entry()`
- `"follow"` → `_handle_follow()`
- `"like"` → `_handle_like()`
- `"comment"` → `_handle_comment()`

Each handler gets the remote author (creates if needed), finds the entry/comment if referenced, creates/updates local records, and returns success or error.

## Helper Functions

`get_remote_author_from_json_data(actor_data)` - gets or creates a remote author. We store remote users locally so we can show their name/avatar, link to their profile, and track who did what.

It gets author ID from data, parses to get UUID and node URL, finds/creates the Node, finds/creates the Author with that UUID, and updates name/github if changed.

`find_entry_by_url(entry_url)` - finds entry by URL. Tries looking up by `source_url` first (for remote entries we already have), then parses URL to get entry ID and author ID and looks up by those.

`find_comment_by_url(comment_url)` - same as `find_entry_by_url` but for comments.

## When We Notify

Entries:
- Create: after saving, send to all remote followers
- Update: after saving, send updated entry
- Delete: after soft-deleting, send with `visibility="DELETED"`

Likes:
- Like: send to entry/comment author (if remote)
- Unlike: send with `removed=True` to entry/comment author

Comments:
- Create: send to entry author (if remote)
- Update: send with `state="updated"` to entry author
- Delete: send with `state="deleted"` to entry author

Follows:
- Request: create `Follow(status=PENDING)`, send to followee
- Accept: update to `ACCEPTED`, send to follower
- Deny: update to `DENIED`, delete locally, send to follower
- Unfollow: delete locally (no notification)

When denying, we delete the relationship locally so when they send a new request, it wont conflict with what we have in the database. The requester's side keeps it as `DENIED` so they know they were rejected.

## Follow Request Flow

Local user requests to follow remote user:
1. User A (local) clicks follow on User B (remote)
2. Create `Follow(follower=A, following=B, status=PENDING)` - by [calling send_follow_request_to_remote_node()](https://github.com/uofa-cmput404/f25-project-ghostwhite/blob/0f879d499feb21c8a6fe62a42b84671baf409017/authors/views.py#L361)
3. Send notification to User B's inbox - user B will receive this through inbox url and will handle it in [handle follow](https://github.com/uofa-cmput404/f25-project-ghostwhite/blob/0f879d499feb21c8a6fe62a42b84671baf409017/inbox/views.py#L279), since this is a pending request so is_decision wll be False and we save the instance to database ( [here](https://github.com/uofa-cmput404/f25-project-ghostwhite/blob/0f879d499feb21c8a6fe62a42b84671baf409017/inbox/views.py#L311-L315) )
4. User B's node creates the same relationship 
5. User B sees the request

Remote user requests to follow local user:
1. User A (remote) requests to follow User B (local)
2. User A's node sends notification to our inbox
3. Create `Follow(follower=A, following=B, status=PENDING)`
4. User B sees the request

Accepting:
1. User B accepts User A's request
2. Update: `status=ACCEPTED, approved=True`
3. Send notification to User A's inbox - since this is a decision ( they are not sending a follow request, they are making a decision like accepting or rejecting the request, we will update the current instance to have the desired status)
4. User A's node updates their relationship to `ACCEPTED`
5. Both sides show "Following"

Rejecting:
1. User B rejects User A's request
2. Update: `status=DENIED, approved=False`
3. Delete the relationship locally
4. Send notification to User A's inbox
5. User A's node updates their relationship to `DENIED`
6. User A can request again later

Edge cases:
- If we are unfollowing then following again:
  For example userA (our node) unfollows user B (remote), we first delete the relationship locally then we call inbox to notify user B, user B will check if status is unfollow ( [here](https://github.com/uofa-cmput404/f25-project-ghostwhite/blob/e45ab6bdeffcbf95189419d700de4d0173f920bf/inbox/views.py#L290), then they will delete the follow on their end) 
- when we send a new request after being rejected: userA (local) requests to follow userB (remote), we create a follow with status pending in our local database, then call inbox to let userB(remote) know. UserB will receive the notification and create a local follow instance with status = pending in their database so they can see. After displaying the request, userB rejects the reuqest -> this will set status of local instance to DENIED and delete the instance locally and call inbox to notify userA. UserA after receiving the notification, we update the status to be DENIED ( We dont delete here because we need to know if we have been rejected ). if userA requests again, they will update their local record ( if exisst) to be PENDING and notify userB, userB will create a new instance in their db with status PENDING.

Each node keeps its own copy of the relationship. When accepting, both sides update to `ACCEPTED`. When rejecting, followee deletes locally, follower keeps as `DENIED`. When retrying, always send notification to remote node.

## Who will receive the notification

Entries:
- `PUBLIC`: all remote followers
- `FRIENDS_ONLY`: only mutual followers
- `UNLISTED`: all remote followers (not public)
- `DELETED`: all remote followers (they already got it)

Likes/Comments: always sent to the author (if remote)

Follows: requests → sent to followee, decisions → sent to follower

## Example

Remote user comments on your post:
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

## Files

`inbox/views.py` - `InboxPostView` (main inbox endpoint), handlers: `_handle_entry()`, `_handle_follow()`, `_handle_like()`, `_handle_comment()`

`utils/node_communication.py` - `send_to_inbox()` (sends POST to remote inbox), notification functions like `send_entry_to_remote_nodes()`, `send_like_to_remote_node()`, etc., `get_or_create_remote_author()` (creates/updates remote authors)

`utils/inbox_parsing.py` - `get_remote_author_from_json_data()` (gets remote author from payload), `parse_follow_state_from_payload()` (maps state strings to constants)

`utils/fqid.py` - `find_entry_by_url()`, `find_comment_by_url()` (find objects by URL), `build_fqid()`, `parse_author_fqid()`, etc. (FQID helpers)

`utils/serializers.py` - `serialize_author_for_node_communication()` (converts Author to API format)

`nodes/authentication.py` - `NodeBasicAuthentication` (HTTP Basic Auth for nodes), `NodeAuthenticated` (permission class)

`entries/views.py` - entry views call `send_entry_to_remote_nodes()` after create/update/delete, like views call `send_like_to_remote_node()` after like/unlike, comment views call `send_comment_to_remote_node()` after create/update/delete

`authors/views.py` - `FollowRequestView` (creates follow requests, calls `send_follow_request_to_remote_node()`), `FollowDecisionView` (accepts/denies, calls `send_follow_decision_to_remote_node()`)
