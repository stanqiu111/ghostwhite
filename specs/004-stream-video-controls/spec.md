# Feature Specification: Stream Video Controls and Bullet Curtain

**Feature Branch**: `004-stream-video-controls`

**Created**: 2026-07-06

**Status**: Draft

**Input**: User description: "Stream Video Controls and Bullet Curtain — improve the stream viewer experience on the stream detail page: viewer playback controls (volume, mute), display-size modes (Auto/Fit/Fill/Theater), and a bullet curtain (danmaku) live comment overlay that viewers can toggle and post to, visible to the streamer too."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Viewer sends a bullet message that flies across the stream (Priority: P1)

While watching a live stream, a logged-in viewer types a short message into an input under the player and sends it. Within a few seconds the message glides across the video area — for them, for every other watcher, and for the streamer.

**Why this priority**: This is the feature's core value: it turns passive watching into a shared, live experience. Everything else (toggle, controls) decorates this loop.

**Independent Test**: Two browsers on the same live stream — send a message from one, see it animate across the player in both. Delivers value even with no other part of this feature built.

**Acceptance Scenarios**:

1. **Given** a live stream open in two browsers (sender + another watcher), **When** the sender submits a message, **Then** the message animates across the video area in both browsers within a few seconds.
2. **Given** a viewer submits a message, **When** it is accepted, **Then** the input clears and is ready for the next message.
3. **Given** a message containing HTML/script markup (e.g. `<script>alert(1)</script>`), **When** it is displayed on any watcher's screen, **Then** it renders as plain text — no markup executes or alters the page.
4. **Given** an empty or whitespace-only message, **When** the viewer tries to send it, **Then** it is rejected and nothing appears on screen.
5. **Given** a message longer than the allowed limit, **When** the viewer tries to send it, **Then** it is rejected with a clear indication of the limit.
6. **Given** a stream that has ended, **When** anyone attempts to send a message to it, **Then** the message is rejected and the viewer sees that the stream is over.
7. **Given** a user who is not logged in, **When** they attempt to send a message directly to the service, **Then** the message is rejected.

---

### User Story 2 - Streamer sees viewer bullet messages while broadcasting (Priority: P1)

The streamer, while sharing their screen, sees viewers' bullet messages fly across their own player area, so they can react to their audience without leaving the stream page.

**Why this priority**: Audience→streamer feedback is half the point of live comments; without it the streamer broadcasts blind.

**Independent Test**: Owner shares screen in one browser; a viewer sends a message from another; the message appears over the owner's player area.

**Acceptance Scenarios**:

1. **Given** an owner on their live stream page (sharing or not), **When** a viewer sends a bullet message, **Then** it animates across the owner's player area within a few seconds.
2. **Given** the owner is actively screen-sharing with the local preview visible, **When** bullet messages arrive, **Then** they overlay the preview without disturbing the sharing controls or the broadcast itself.

---

### User Story 3 - Viewer toggles the bullet curtain on and off (Priority: P2)

A viewer who finds the messages distracting can switch the overlay off; the video stays untouched. Switching it back on resumes display of new messages.

**Why this priority**: Comfort control — essential for acceptance of an overlay feature, but meaningless until US1 exists.

**Independent Test**: With bullets flowing, toggle off → no new messages appear; toggle on → new messages appear again.

**Acceptance Scenarios**:

1. **Given** the bullet curtain is on and messages are arriving, **When** the viewer turns it off, **Then** currently visible messages disappear or finish immediately and no new ones are shown.
2. **Given** the curtain is off, **When** the viewer turns it on, **Then** messages sent from that moment on appear; messages missed while off are not replayed.
3. **Given** the curtain is off, **When** the viewer sends a message, **Then** the message is still delivered to everyone else.

---

### User Story 4 - Viewer adjusts playback volume (Priority: P2)

A viewer can drag a volume slider and click a mute/unmute toggle on the player.

**Why this priority**: Standard player affordance viewers expect — but only when it can actually do something. Today's broadcasts carry no sound (screen video only), so the controls stay hidden rather than appearing broken; they surface automatically for any stream that carries audio.

**Independent Test**: On a current (silent) stream, verify no volume controls are shown; the readiness of the controls is verified by the hidden markup + wiring and exercised the day audio streams exist.

**Acceptance Scenarios**:

1. **Given** a stream whose video carries an audio track, **When** the viewer moves the volume slider, **Then** the player's volume follows it and the control reflects the current level.
2. **Given** audible playback at any volume, **When** the viewer clicks mute, **Then** the player is silenced and the control shows the muted state; clicking again restores the prior level.
3. **Given** a stream with no audio track (all current streams), **When** the viewer watches, **Then** no volume/mute controls are visible and video plays uninterrupted — no fake controls that appear broken.

---

### User Story 5 - Viewer picks a display mode (Priority: P3)

A viewer chooses how the video fills the player area: Auto (default), Fit (whole frame visible), Fill (cover the area, cropping edges), or Theater (enlarged player on the page).

**Why this priority**: Nice-to-have comfort feature; the default already letterboxes sensibly. True quality/resolution selection is out of scope (see Assumptions).

**Independent Test**: While watching video, switch between the four modes and observe the video geometry / player size change accordingly; the choice survives until the page is left.

**Acceptance Scenarios**:

1. **Given** a viewer watching video, **When** they select Fit, **Then** the entire video frame is visible (letterboxed if aspect differs).
2. **Given** a viewer watching video, **When** they select Fill, **Then** the video covers the player area with edges cropped as needed.
3. **Given** a viewer selects Theater, **Then** the player area enlarges on the page; selecting another mode returns it to normal size.
4. **Given** any selected mode, **When** the viewer enters and exits fullscreen, **Then** the mode is still applied correctly afterwards.

---

### Edge Cases

- Many messages arrive at once: they must distribute across the video area (multiple lanes) rather than stack unreadably on one line, and excess messages may be dropped from display rather than degrade playback.
- A message is sent moments after the stream ends: sender gets a clear "stream has ended" rejection; no message appears anywhere.
- Bullet messages while the video is not yet playing (viewer still "waiting"): messages still animate over the placeholder area — the curtain works whenever the stream is live, video or not.
- Bullet messages must never permanently block the player controls (fullscreen button, volume, retry): messages pass over transient areas but controls stay clickable — the overlay must not intercept clicks.
- Viewer opens the page mid-stream: they see a one-time backfill of at most the 30 most recent messages, then live messages only; the full history is never replayed.
- The streamer ends the stream while messages are mid-flight: watchers' players move to the ended state; in-flight animations may finish but no new messages appear.
- A user rapid-fires messages: sends are throttled to a reasonable pace on the sending side; the service enforces the length limit and authentication on every message.
- Very long single word (no spaces) at the length limit must not break the animation or overflow the screen unreadably.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Logged-in users MUST be able to send a bullet message to a live stream from the stream page; each stored message records which stream, which author, the text content, and when it was sent.
- **FR-002**: The service MUST reject bullet messages that are empty/whitespace-only or exceed 120 characters.
- **FR-003**: The service MUST reject bullet messages from unauthenticated users and messages addressed to ended or nonexistent streams (ended streams communicated distinctly from unknown ones).
- **FR-004**: All watchers of a live stream — viewers and the streamer — MUST see newly sent bullet messages animate horizontally across the player area within 5 seconds of sending, without interrupting video playback or screen sharing.
- **FR-005**: Bullet message text MUST always be rendered as inert plain text; markup or script in a message MUST never execute or affect the page for any watcher.
- **FR-006**: Each watcher MUST be able to toggle the bullet curtain overlay on/off for themselves; off hides display only — sending and delivery to others are unaffected. The toggle state applies for the duration of the visit.
- **FR-007**: Simultaneous messages MUST be laid out in multiple lanes across the player area so they remain readable, and the overlay MUST never make player controls unclickable.
- **FR-008**: Watchers joining mid-stream MUST see at most the 30 most recent messages as a one-time backfill, then only new messages; the full history is never replayed. Re-enabling the curtain shows only messages sent after re-enabling.
- **FR-009**: Viewers MUST have a volume slider and a mute/unmute toggle on the player **only when the received stream actually carries an audio track**; when there is no audio (the current norm), the controls are hidden — no inert/fake controls are shown.
- **FR-010**: Viewers MUST be able to select a display mode — Auto, Fit, Fill, Theater — changing how video occupies the player area (Theater additionally enlarges the player on the page). The selection lasts for the visit and coexists with fullscreen.
- **FR-011**: The new controls and overlay MUST match the existing stream page look and feel and MUST NOT degrade or break existing behavior: screen sharing, the waiting/connecting/live/ended/error states, fullscreen, and stream end teardown all keep working.
- **FR-012**: Automated tests MUST cover bullet message creation, authentication requirement, ended-stream rejection, length/empty validation, and that stored/delivered content is treated as plain text (escaping preserved end-to-end).

### Key Entities

- **Bullet Message**: one short live comment on a stream — belongs to a stream and an author, has text content (≤120 chars) and a creation timestamp. Unlike the ephemeral connection signals, bullet messages are ordinary stored content addressed to everyone watching.
- **Stream (existing)**: gains a one-to-many relationship to bullet messages; its live/ended status gates whether new messages are accepted.
- **Author (existing)**: the sender of each bullet message.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A bullet message sent by one watcher is visible on every other watcher's screen (including the streamer's) within 5 seconds, in a session with at least 3 concurrent watchers.
- **SC-002**: A message containing hostile markup is displayed as literal text on all screens — zero script execution — verified by test and by manual attempt.
- **SC-003**: Ended streams accept zero new bullet messages; attempts receive an unambiguous rejection.
- **SC-004**: With the curtain toggled off, zero bullet messages are displayed to that watcher while others continue to see them.
- **SC-005**: Volume, mute, display-mode, and curtain controls each respond visibly in under 1 second, and video playback continues uninterrupted through any combination of them.
- **SC-006**: All pre-existing stream behaviors (sharing, watching, retry, fullscreen, end teardown) pass the same checks as before the feature — zero regressions in the existing automated suite.

## Assumptions

- **True quality/resolution switching is out of scope.** The current broadcast fans out one identical video feed per watcher; offering per-watcher resolution choices would require re-architecting distribution (e.g. a media server). Display modes (Auto/Fit/Fill/Theater) provide the user-facing "display quality/size" control instead, as sanctioned in the feature request.
- **Current streams carry no sound.** Volume and mute controls exist in the page but are shown **only when the received stream has an audio track** — hidden otherwise, so users never meet controls that appear broken. They activate automatically if audio capture is enabled in a future feature.
- **Bullet messages are content, not transport**: they persist after the stream ends (like comments would), even though the overlay never replays history. Deleting/moderating messages is out of scope for v1.
- **No server-side rate limiting in v1** beyond authentication and the length limit; a modest client-side send throttle covers the realistic classroom-scale audience. Can be revisited if abuse appears.
- **Anyone logged in can send** — including the stream owner; there is no separate permission tier for bullet messages.
- **Overlay/off state and display mode are per-visit** (not saved to the account); defaults every page load: curtain on, mode Auto, volume 100% unmuted.
- Delivery uses the same periodic-refresh approach the stream page already relies on; watchers tolerate a few seconds of latency (SC-001's 5-second bound).
