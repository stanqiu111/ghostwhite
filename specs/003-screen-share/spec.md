# Feature Specification: Screen-Sharing for Live Streams

**Feature Branch**: `003-screen-share`

**Created**: 2026-07-06

**Status**: Draft

**Input**: User description: "Real screen-sharing for live streams (builds on the 002-live-stream lifecycle MVP). As a streamer, I can click 'Share Screen' on my active stream's page and my screen is broadcast. As a viewer on the stream detail page, I can watch the streamer's shared screen while the stream is active. Viewers see clear UI states: waiting for streamer, connecting, live, ended, error. Only the stream owner can broadcast into their stream. Screen sharing stops when the owner ends the stream or stops sharing. Existing placeholder player remains as waiting/fallback state. Local-first, small scale, browser-to-browser video, no paid services, no recording/replay, must not break the lifecycle MVP."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Streamer shares their screen (Priority: P1)

The owner of a live stream opens their stream's page and clicks "Share Screen". The browser asks which screen/window to share and for permission. Once granted, the streamer sees a local preview of what they are broadcasting and an indication that they are on air. Clicking "Stop sharing" (or the browser's native stop control) ends the broadcast but keeps the stream itself live.

**Why this priority**: Without a broadcasting streamer there is nothing to watch; this is the source of all video in the feature.

**Independent Test**: As a stream owner on your live stream page, click Share Screen, grant permission, and verify the local preview shows your screen and the page indicates broadcasting. Click Stop sharing and verify the preview stops while the stream stays live.

**Acceptance Scenarios**:

1. **Given** the owner is on their own live stream page, **When** they click "Share Screen" and grant browser permission, **Then** a live preview of the chosen screen appears in the player area and the page shows an "on air" indication.
2. **Given** the owner is broadcasting, **When** they click "Stop sharing" or use the browser's native stop control, **Then** the broadcast stops, the player returns to the waiting state, and the stream remains live.
3. **Given** the owner denies the browser's permission prompt, **When** the prompt closes, **Then** the page shows a clear error/hint state and no broadcast starts.
4. **Given** a non-owner is on someone else's live stream page, **When** the page renders, **Then** no "Share Screen" control is visible to them.

---

### User Story 2 - Viewer watches the shared screen (Priority: P1)

A logged-in viewer opens a live stream's page. If the streamer is not yet sharing, the viewer sees a "waiting for streamer" state (the existing placeholder). When the streamer starts sharing, the viewer's player transitions through "connecting" and then shows the streamer's screen live. If the connection fails, the viewer sees an error state with a retry option.

**Why this priority**: Equal-priority counterpart of User Story 1 — a broadcast nobody can watch has no value. Together they form the complete watching loop.

**Independent Test**: With the streamer broadcasting in one browser, open the stream page as a different user in another browser and verify the shared screen plays. Stop sharing and verify the viewer returns to the waiting state.

**Acceptance Scenarios**:

1. **Given** a live stream whose owner is not sharing, **When** a viewer opens the stream page, **Then** the player area shows the waiting/placeholder state.
2. **Given** a live stream whose owner is sharing, **When** a viewer opens the stream page (or is already on it), **Then** within a few seconds the player shows "connecting" and then the live screen content.
3. **Given** a viewer is watching, **When** the streamer stops sharing (but not the stream), **Then** the viewer's player returns to the waiting state without a page reload.
4. **Given** a viewer is watching, **When** the connection cannot be established or drops, **Then** the player shows an error state with a way to retry.
5. **Given** multiple viewers (a handful) on the same stream, **When** the owner is sharing, **Then** all of them can watch simultaneously.

---

### User Story 3 - Broadcast integrity and lifecycle integration (Priority: P1)

Only the stream owner can broadcast into their stream — another user cannot inject video into someone else's stream, even by crafting requests directly. When the owner ends the stream, any active broadcast stops and viewers see the ended state. All existing lifecycle behavior (start, list, detail, end, permissions) continues to work unchanged.

**Why this priority**: Security and regression safety are non-negotiable; a feature that lets others hijack a stream or that breaks the MVP is worse than no feature.

**Independent Test**: Attempt to send broadcast-setup messages into another user's stream via direct requests and verify they are rejected. End a stream mid-broadcast and verify viewers see the ended state. Run the existing stream test suite and verify it still passes.

**Acceptance Scenarios**:

1. **Given** a live stream owned by user A, **When** user B attempts to initiate a broadcast into it (bypassing the UI), **Then** the attempt is rejected and viewers never receive video from B.
2. **Given** the owner is broadcasting, **When** the owner ends the stream, **Then** the broadcast stops, watching viewers transition to the ended state, and the stream no longer appears in the active list.
3. **Given** the screen-sharing feature is deployed, **When** the existing stream lifecycle test suite runs, **Then** it passes unchanged.
4. **Given** a viewer's page is open on an ended stream, **When** they arrive or remain there, **Then** they see the ended state and no connection attempts continue.

---

### Edge Cases

- Streamer refreshes or closes their tab mid-broadcast → viewers return to the waiting state (broadcast presence is tied to the streamer's page being open); the stream itself stays live until explicitly ended.
- A viewer joins mid-broadcast → they still get the current live video (join is not limited to viewers present at share start).
- Streamer clicks "Share Screen" twice / rapid start-stop → no duplicate broadcasts; the latest action wins.
- Two tabs open by the owner → only one active broadcast at a time; starting a share in a second tab replaces or is blocked, never doubles.
- Viewer's browser does not support screen-share playback → the player shows an unsupported/error state rather than breaking the page.
- Signaling messages for a stream that has ended → ignored/rejected server-side; no stale connections are set up.
- Streamer's chosen window is minimized or its content pauses → viewers simply see whatever the browser captures; no special handling required in v1.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The stream owner MUST see a "Share Screen" control on their own live stream's page; non-owners and ended streams MUST NOT show it.
- **FR-002**: Activating "Share Screen" MUST use the browser's native screen-capture permission flow; denial MUST leave the page in a clear non-broadcasting state with feedback.
- **FR-003**: While broadcasting, the owner MUST see a local preview and an explicit on-air indication, plus a "Stop sharing" control.
- **FR-004**: Logged-in viewers on a live stream's page MUST automatically receive the broadcast when the owner is sharing, without a manual page reload.
- **FR-005**: The viewer's player MUST expose distinct visible states: waiting for streamer (existing placeholder), connecting, live, ended, and error (with retry).
- **FR-006**: The platform MUST reject broadcast-initiation and connection-setup messages from anyone other than the stream owner, enforced server-side (not just hidden UI).
- **FR-007**: All connection-setup exchanges MUST be scoped to a specific stream and MUST require a logged-in user.
- **FR-008**: When the owner stops sharing, viewers MUST return to the waiting state; when the owner ends the stream, viewers MUST transition to the ended state and connection setup for that stream MUST stop being accepted.
- **FR-009**: Video MUST travel directly between the streamer's and viewers' browsers (peer-to-peer); the server participates only in connection setup.
- **FR-010**: The feature MUST support at least 5 simultaneous viewers per stream at course-project scale.
- **FR-011**: The existing stream lifecycle behavior and its test suite MUST remain green; the placeholder player remains the waiting/fallback state.
- **FR-012**: Server-side connection-setup exchanges MUST be covered by automated tests (permissions, stream scoping, ended-stream rejection).

### Key Entities

- **Broadcast session** (transient): the period during which a stream's owner is sharing; tied to the owner's open page; at most one active per stream; not persisted as history.
- **Connection-setup message** (short-lived): a small addressed message exchanged between streamer and a specific viewer through the server to establish a direct connection (e.g., join/offer/answer/candidate); scoped to one stream; irrelevant once the stream ends.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A streamer can go from clicking "Share Screen" to broadcasting in under 15 seconds (dominated by the browser's permission prompt).
- **SC-002**: A viewer on a live stream page sees the shared screen within 10 seconds of the streamer starting to share, without reloading.
- **SC-003**: 100% of broadcast-initiation attempts by non-owners are rejected server-side.
- **SC-004**: At least 5 concurrent viewers can watch one stream simultaneously in a local/LAN setting.
- **SC-005**: When sharing stops or the stream ends, 100% of connected viewers leave the live state within 10 seconds.
- **SC-006**: The full existing stream test suite passes unchanged; zero regressions attributable to this feature.

## Assumptions

- "Local-first" means the feature must work between browsers on the same machine or LAN without external infrastructure; cross-network reachability beyond what free public connectivity-discovery services provide (e.g., NAT traversal relays) is out of scope for v1.
- Direct browser-to-browser transport is acceptable at this scale (one streamer, ≤ ~5 viewers); a media/relay server is explicitly out of scope for v1 and would only be revisited if viewer counts grow beyond what a single uploader can serve.
- Audio is whatever the browser's screen capture provides if the user opts in; no separate microphone support in v1.
- No recording, replay, chat, or viewer-count display in v1.
- Broadcast presence is ephemeral: it is not stored as history and does not survive the streamer closing their page; the stream lifecycle (live/ended) remains the only persisted state, per the 002 data model.
- Modern evergreen desktop browsers (Chrome/Edge/Firefox current versions) are the target; mobile broadcasting is out of scope (mobile viewing works where the browser supports it).
- Free public infrastructure (e.g., public connectivity-discovery endpoints) may be used; no paid third-party services.
