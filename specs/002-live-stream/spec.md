# Feature Specification: Live Stream Feature

**Feature Branch**: `002-live-stream`

**Created**: 2026-07-06

**Status**: Draft

**Input**: User description: "As a user, I can start a live stream on this platform, and other users can view my live stream while it is active. MVP for local users only: a logged-in user can start a stream with title/description/status/start time/optional end time; other logged-in users see currently active streams on a streams page; users can open a stream detail page showing streamer, title, description, status; the stream owner (and only the owner) can end their stream; ended streams no longer appear as active. No remote-node federation in first pass, but design the model so federation can be added later. No WebRTC/media servers/third-party streaming yet — implement the stream lifecycle and viewing page first, with a placeholder player area and clear extension points."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Start a live stream (Priority: P1)

A logged-in user wants to go live. From the platform they open a "start stream" form, enter a title and an optional description, and submit. The platform records the stream as live with the current time as its start time, and takes the user to their stream's page, where they can see their stream is active.

**Why this priority**: Without the ability to create a stream, nothing else in the feature exists. This is the entry point of the entire lifecycle.

**Independent Test**: Log in, open the start-stream form, submit a title. Verify a stream page exists showing the stream as live with the correct owner and start time.

**Acceptance Scenarios**:

1. **Given** a logged-in user on the start-stream form, **When** they submit a title (and optional description), **Then** a stream is created with status "live", the submitting user as owner, and the current time as start time, and the user lands on that stream's detail page.
2. **Given** a logged-out visitor, **When** they attempt to open the start-stream form or submit it, **Then** they are redirected to the login page and no stream is created.
3. **Given** a logged-in user, **When** they submit the form with an empty title, **Then** the stream is not created and the form shows a validation message.

---

### User Story 2 - Discover and watch active streams (Priority: P1)

A logged-in user wants to see who is live right now. They open the streams page, which lists only currently active streams, each showing the streamer's name, the stream title, and when it started. Clicking a stream opens its detail page, which shows the streamer, title, description, live status, and a viewing area (placeholder player in the MVP).

**Why this priority**: A stream nobody can find or open delivers no value. Discovery + detail viewing completes the minimum loop that makes User Story 1 meaningful.

**Independent Test**: With one live stream in the system, log in as a different user, open the streams page, verify the stream is listed, click it, and verify the detail page shows streamer, title, description, and live status.

**Acceptance Scenarios**:

1. **Given** at least one live stream exists, **When** a logged-in user opens the streams page, **Then** each live stream appears with streamer name, title, and start time.
2. **Given** a live stream, **When** a logged-in user opens its detail page, **Then** they see the streamer's name, title, description, live status, and a player area.
3. **Given** no live streams exist, **When** a user opens the streams page, **Then** they see an empty state message (not an error).
4. **Given** a logged-out visitor, **When** they open the streams page or a stream detail page, **Then** they are redirected to the login page.

---

### User Story 3 - End a stream (owner only) (Priority: P1)

The streamer finishes their broadcast. On their own stream's detail page they see an "End stream" control that other viewers do not see. Ending the stream records the end time, changes the status to ended, and removes the stream from the active streams list. Anyone opening the ended stream's page afterward sees it marked as ended.

**Why this priority**: Without ending, every stream is live forever and the "active streams" concept is meaningless. Ownership enforcement is a security requirement, not a nice-to-have.

**Independent Test**: As the stream owner, end the stream and verify it disappears from the streams page and shows "ended" on its detail page. As a different user, verify the end control is absent and a direct end attempt is rejected.

**Acceptance Scenarios**:

1. **Given** a live stream viewed by its owner, **When** the owner activates "End stream", **Then** the stream's status becomes ended, an end time is recorded, and the stream no longer appears in the active list.
2. **Given** a live stream viewed by a non-owner, **When** they view the detail page, **Then** no end control is shown.
3. **Given** a live stream, **When** a non-owner attempts to end it directly (bypassing the UI), **Then** the attempt is rejected and the stream stays live.
4. **Given** an already-ended stream, **When** its page is opened, **Then** it displays ended status with its start and end times, and no end control.

---

### Edge Cases

- A user starts a second stream while their first is still live → the platform allows at most one live stream per user; starting a new one is blocked with a clear message while another of theirs is live.
- The owner ends an already-ended stream (double-submit, stale tab) → the second attempt is a no-op that does not change the recorded end time or produce an error page.
- A stream detail page is opened for a stream identifier that does not exist → a not-found page is shown, not a server error.
- The streams page is opened while a stream is being ended concurrently → the list simply reflects whichever state the stream is in at render time; no stale "live" entry should persist after refresh.
- Very long titles or descriptions → title length is bounded by validation; long descriptions render without breaking the page layout.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The platform MUST allow a logged-in user to create a stream by providing a required title and an optional description.
- **FR-002**: A newly created stream MUST be recorded with status "live", the creating user as owner, and the creation moment as its start time.
- **FR-003**: The platform MUST prevent a user from having more than one live stream at a time.
- **FR-004**: The platform MUST provide a streams page listing only streams whose status is live, showing each stream's owner, title, and start time.
- **FR-005**: The platform MUST provide a stream detail page showing the owner, title, description, status, start time, end time (when ended), and a placeholder player area.
- **FR-006**: The stream owner MUST be able to end their own live stream; ending records an end time and changes status to ended.
- **FR-007**: The platform MUST reject any attempt by a non-owner to end a stream, both in the UI (control hidden) and at the request level (attempt refused).
- **FR-008**: Ended streams MUST NOT appear in the active streams list, but their detail pages MUST remain reachable and show ended status.
- **FR-009**: All stream pages and actions MUST require a logged-in user; logged-out visitors are redirected to login.
- **FR-010**: Each stream MUST be identified in a way that can later be extended to a globally unique, node-qualified identity (federation-ready), without requiring identifier changes for existing streams.
- **FR-011**: Ending an already-ended stream MUST be a harmless no-op.
- **FR-012**: Stream creation MUST validate input: empty titles rejected; title length bounded.

### Key Entities

- **Stream**: A broadcast session owned by one local user. Attributes: globally-unique identifier (federation-ready), owner, title, description (optional), status (live / ended), start time, end time (empty until ended). Related to the existing user identity (Author); one owner has many streams over time but at most one live at once.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A logged-in user can go from "not streaming" to "live with a visible stream page" in a single form submission (under 30 seconds of user effort).
- **SC-002**: 100% of live streams are visible on the streams page to any logged-in user; 0% of ended streams appear there.
- **SC-003**: 100% of end-stream attempts by non-owners are rejected; 100% of end-stream actions by owners succeed on a live stream.
- **SC-004**: A viewer can get from the streams page to a specific stream's detail page in one click.
- **SC-005**: All existing platform behavior (feed, entries, profiles, inbox) continues to pass its existing test suite unchanged.

## Assumptions

- "Viewing" a stream in the MVP means opening its detail page and seeing its live metadata and a placeholder player area; no actual audio/video transport is included. The player area is an explicit extension point for a future media integration.
- Streams are visible to all logged-in local users (equivalent of "public" visibility); per-stream visibility controls (friends-only, unlisted) are out of scope for the MVP.
- Remote-node federation of streams is out of scope for the MVP, but the stream identity scheme must not preclude it (mirrors how existing content is identified platform-wide).
- Stream discovery is a dedicated streams page; surfacing live streams in the home feed or on profiles is out of scope for the MVP.
- No notifications are sent to followers when a stream starts (out of scope for MVP).
- Concurrent viewer counts, chat, reactions, and recording/replay are out of scope for the MVP.
- The existing login system is reused as-is; no new account or permission types are introduced beyond "owner of a stream".
