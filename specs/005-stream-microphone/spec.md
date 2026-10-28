# Feature Specification: Optional Microphone Commentary for Live Streams

**Feature Branch**: `work` (existing task branch)

**Feature Directory**: `specs/005-stream-microphone`

**Created**: 2026-10-27

**Status**: Implemented — media transport and physical-device validation pending; see [validation.md](validation.md)

**Input**: User description: "Add optional microphone commentary to live screen sharing, with broadcaster mute controls and graceful handling of denied microphone permission."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Add commentary to an active screen share (Priority: P1)

A stream owner starts sharing their screen with the microphone off. When they choose to enable commentary, they grant microphone permission if requested and can speak to their audience. Viewers already watching and viewers who join later hear the commentary alongside the shared screen.

**Why this priority**: Speaking while demonstrating something on screen is the core benefit. Screen sharing must remain usable without microphone access.

**Independent Test**: Start a screen share as its owner, confirm no microphone prompt appears, then enable the microphone. A viewer already watching and a second viewer joining afterward can hear a spoken phrase while seeing the screen.

**Acceptance Scenarios**:

1. **Given** an owner starts a fresh screen share, **When** video begins, **Then** the microphone is off, no microphone permission is requested, and the owner can continue broadcasting video only.
2. **Given** an owner is sharing their screen, **When** they explicitly enable the microphone and grant any required permission, **Then** the owner sees "Microphone on" and existing viewers hear newly spoken commentary without reloading.
3. **Given** commentary is enabled, **When** another viewer joins and permits sound playback if their browser requires it, **Then** they hear current commentary and see the shared screen without the owner restarting the broadcast.
4. **Given** screen sharing has not started or its permission was denied, **When** the owner views the stream page, **Then** enabling commentary is unavailable and microphone capture cannot start.
5. **Given** a viewer is watching someone else's stream, **When** they open the player, **Then** they have no broadcaster microphone controls and are never asked for microphone permission. Attempts to contribute commentary as a non-owner are rejected.

---

### User Story 2 - Mute and unmute outgoing commentary (Priority: P1)

The broadcaster can briefly stop their commentary for everyone while continuing to share their screen, then resume with one action.

**Why this priority**: The broadcaster needs immediate, unambiguous control over what their audience hears.

**Independent Test**: With two viewers connected, speak while toggling mute and unmute. Both viewers lose and regain commentary while video continues; a viewer joining during mute hears no commentary.

**Acceptance Scenarios**:

1. **Given** the microphone is on, **When** the broadcaster selects "Mute microphone", **Then** their state changes to "Muted", no newly spoken commentary reaches any viewer after the mute transition, and video continues.
2. **Given** the broadcaster is muted, **When** a new viewer joins, **Then** that viewer sees the screen but hears no broadcaster commentary.
3. **Given** the broadcaster is muted and microphone access remains available, **When** they select "Unmute microphone", **Then** commentary resumes for all connected viewers without another permission request or restarting the screen share.
4. **Given** the broadcaster spoke while muted, **When** they unmute, **Then** none of that muted-period speech is replayed.
5. **Given** an owner uses only a keyboard, **When** they operate the microphone controls, **Then** enable, mute, unmute, and retry actions are reachable and their names and current state are understandable without relying on color.

---

### User Story 3 - Continue sharing when the microphone is unavailable (Priority: P1)

An owner who declines microphone permission, lacks a usable microphone, or loses microphone access continues their video broadcast. They receive a clear explanation and can retry after fixing the problem.

**Why this priority**: Optional commentary must never become a prerequisite for the existing screen-sharing workflow.

**Independent Test**: Deny permission during a live screen share, verify video continues, then allow access and explicitly retry. Repeat with a missing or disconnected microphone and verify the same video-only fallback.

**Acceptance Scenarios**:

1. **Given** an owner requests commentary, **When** they deny or dismiss microphone permission, **Then** the page explains that commentary is unavailable and screen sharing continues without requiring a reload.
2. **Given** a microphone permission request is still awaiting a decision, **When** viewers watch the broadcast, **Then** video continues and the owner sees "Requesting microphone"; repeated clicks do not open duplicate requests.
3. **Given** the browser does not offer microphone capture, the device has no microphone, or the microphone cannot be opened, **When** the owner attempts to enable commentary, **Then** they see an explanation and can keep sharing video.
4. **Given** commentary could not be enabled, **When** the owner resolves the permission or device problem and selects "Retry microphone", **Then** commentary can start on the current screen share without disconnecting viewers.
5. **Given** commentary is active or muted, **When** the microphone disconnects or permission is revoked, **Then** commentary stops, the owner sees "Microphone unavailable", and video continues.
6. **Given** access was denied or lost, **When** the owner takes no further action, **Then** the app neither repeatedly requests permission nor automatically resumes commentary.
7. **Given** microphone access is unavailable, **When** the owner inspects the controls, **Then** the page offers recovery guidance rather than presenting a working unmute action.

---

### User Story 4 - Stop microphone use with the broadcast (Priority: P1)

Microphone use ends when screen sharing ends. Returning to the page or starting a new share requires a fresh, deliberate choice to enable commentary.

**Why this priority**: Broadcasters must not keep transmitting commentary after they believe they have stopped sharing.

**Independent Test**: Enable commentary and stop sharing using each supported stop action. Verify that this broadcast no longer uses the microphone, viewers hear no further commentary, and restarting sharing leaves the microphone off.

**Acceptance Scenarios**:

1. **Given** commentary is on or muted, **When** the owner stops sharing using the page control or the browser's native stop-sharing control, **Then** video and commentary stop, microphone use by this broadcast ends, and the stream itself remains live in its existing waiting state.
2. **Given** commentary is on or muted, **When** the owner ends the stream, closes the broadcasting page, navigates away, or reloads it, **Then** microphone use by that broadcast ends. Ending the stream shows viewers the ended state; the other actions preserve the existing stream lifecycle.
3. **Given** the owner stopped sharing or ended the stream while a microphone permission request was pending, **When** permission is subsequently granted, **Then** commentary does not start and the obsolete request leaves no microphone in use.
4. **Given** a previous broadcast used commentary, **When** the owner starts another screen share, **Then** its microphone starts off even if the browser remembers the previous permission grant.

---

### User Story 5 - Control listening without affecting the broadcast (Priority: P2)

Each viewer can adjust the commentary's volume or mute it locally. A browser that requires an explicit action before playing sound explains how to enable it, while continuing to display video.

**Why this priority**: The existing viewer sound controls need to work with real commentary and browser playback restrictions.

**Independent Test**: Join an audible stream with two viewers. Mute one viewer, verify the other still hears the broadcaster, then exercise the browser's sound-playback restriction and enable sound explicitly.

**Acceptance Scenarios**:

1. **Given** a viewer receives commentary, **When** they change volume or mute the player, **Then** only their own listening experience changes; the broadcaster and other viewers are unaffected.
2. **Given** a viewer is already watching a video-only share, **When** the broadcaster enables commentary, **Then** the viewer gains usable sound controls without reloading.
3. **Given** the viewer's browser blocks automatic sound playback, **When** commentary becomes available, **Then** the viewer sees an "Enable sound" action, video continues, and selecting that action permits listening where the browser allows it.
4. **Given** a viewer muted their player or chose a lower volume, **When** the broadcaster mutes, unmutes, or recovers microphone access, **Then** that viewer's local audio preference is preserved for the current page visit.
5. **Given** the owner is broadcasting commentary, **When** they view their own local preview, **Then** that preview does not play their microphone back to them.
6. **Given** a broadcast has never enabled commentary, **When** a viewer watches it, **Then** the existing video-only experience remains intact and no unusable sound controls are presented.

### Edge Cases

- Microphone permission remains unanswered indefinitely: video continues; stopping the broadcast remains available.
- A permission result arrives after stopping, navigating away, ending the stream, or starting a newer broadcast: it cannot activate commentary for an obsolete or different broadcast.
- A viewer joins while the broadcaster is muted: the viewer receives no commentary until the broadcaster deliberately unmutes.
- The broadcaster rapidly repeats enable, mute, unmute, or retry: the displayed state settles on the latest valid action without duplicate commentary or microphone requests.
- Microphone access disappears while muted: the state becomes unavailable; unmuting cannot silently reacquire permission.
- A viewer reconnects while commentary is active: they receive the current commentary state and retain their local mute/volume choice if the page has not been reloaded.
- Browser or operating-system permission remains blocked after retry: show applicable recovery guidance and keep video working without a prompt loop.
- A browser cannot play commentary despite the viewer's sound-enabling action: display an audio-specific explanation and continue video where supported.
- The broadcaster stops sharing while muted: microphone use must still end.
- Fullscreen, display modes, bullet comments, and their controls continue working during microphone state changes.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Only the owner of an active screen share MUST be able to contribute microphone commentary to that broadcast, using the stream's existing access rules. Viewers MUST NOT receive broadcaster microphone controls or microphone permission prompts.
- **FR-002**: Every new screen-sharing session MUST start with commentary off. Microphone access MUST be requested only after the owner explicitly enables it on that active session, even when permission was previously granted.
- **FR-003**: Starting video, continuing video, and stopping sharing MUST remain available independently of an unanswered, denied, dismissed, or unsuccessful microphone request.
- **FR-004**: Once enabled, current commentary MUST reach both existing viewers and later joiners without restarting the broadcast or requiring a page reload, subject to viewer sound-playback permission.
- **FR-005**: The owner MUST be able to mute outgoing commentary for all viewers and unmute it without interrupting video. Viewers joining while muted MUST hear no commentary; speech from the muted period MUST NOT be replayed.
- **FR-006**: The broadcaster MUST see distinct states for microphone off, requesting access, microphone on, muted, and unavailable. Controls MUST reflect valid actions, remain keyboard-operable, and identify their action and state in text or an accessible name rather than color alone.
- **FR-007**: Permission denial or dismissal, unsupported capture, a missing or unusable device, and loss of access MUST produce microphone-specific feedback and a video-only fallback. Recovery guidance MUST match the known cause, or state that access could not be obtained when the cause is unknown.
- **FR-008**: The broadcaster MUST be able to explicitly retry microphone access during the same screen share after resolving a problem. The app MUST NOT loop permission requests or automatically resume commentary after denial or loss of access.
- **FR-009**: Microphone access lost while commentary is on or muted MUST leave the microphone unavailable while video continues. Successful explicit recovery MUST restore commentary for existing and newly joining viewers.
- **FR-010**: Stopping screen sharing through either stop control, ending the stream, or leaving/reloading/closing the broadcasting page MUST stop commentary and end microphone use by that broadcast, including when it was muted.
- **FR-011**: Delayed permission results and repeated actions MUST NOT create duplicate microphone requests or commentary sources, restart a stopped broadcast, or enable commentary in a different sharing session. Microphone access obtained for an obsolete request MUST be released.
- **FR-012**: Viewers MUST have usable local volume and mute controls when commentary is available, including when enabled after they joined. Their local settings MUST remain independent of broadcaster mute state and survive microphone changes or reconnection during the same page visit.
- **FR-013**: When a viewer's browser requires interaction before playing sound, the player MUST offer an explicit sound-enabling action while keeping video visible. If sound still cannot play, the player MUST explain the audio problem without unnecessarily stopping video.
- **FR-014**: The broadcaster's own preview MUST NOT play their microphone audio back to them. The feature MUST preserve the existing video-only experience, stream lifecycle and access rules, waiting/connecting/live/ended/error states, retry, fullscreen, display modes, and bullet-comment behavior.
- **FR-015**: Commentary and microphone control state MUST be confined to the current broadcast. This feature MUST NOT record or retain commentary, nor save microphone-enabled state for future broadcasts.

### Key Entities

- **Broadcast session**: the existing period of screen sharing by a stream owner; provides the lifecycle boundary for optional commentary.
- **Microphone commentary state**: the owner's current off, requesting, on, muted, or unavailable state, belonging to one broadcast session rather than a saved account preference.
- **Viewer listening preference**: local volume and mute choices for the current page visit, independent of the broadcaster's outgoing commentary state.

## Success Criteria *(mandatory)*

### Measurable Outcomes

The timing and audience-size checks below use the existing small-audience setting: one broadcaster and up to five viewers on a functioning local network, supported desktop browsers, and audible viewer playback enabled where required. Time spent waiting for a person to answer a permission or sound-playback prompt is excluded.

- **SC-001**: In a session with five connected viewers, all five can hear a newly spoken test phrase within 5 seconds after the owner successfully enables microphone commentary, while screen video continues.
- **SC-002**: A viewer joining an audible broadcast can see the screen and hear current commentary within 10 seconds after joining and completing any required sound-playback action.
- **SC-003**: Broadcaster mute/unmute controls update their displayed state within 1 second, and all connected viewers observe the outgoing sound change within 1 second. A viewer joining during mute hears no muted-period speech.
- **SC-004**: Each exercised microphone failure case—denial, dismissal, unsupported capture, missing/unusable device, disconnection, and revoked access—preserves video without a reload and presents applicable feedback within 2 seconds after the failure becomes known. A pending permission request does not pause video.
- **SC-005**: In every stop, end, page-departure, and late-permission-result scenario, this broadcast stops using the microphone within 1 second of the stop event or obsolete permission result, and viewers receive no newly captured commentary afterward.
- **SC-006**: In every exercised video-only start, restart, and viewer-join scenario, there are zero unintended microphone requests and no automatic activation based solely on a remembered permission.
- **SC-007**: One viewer's mute/volume changes leave the other viewers' sound unchanged; viewers can recover from browser-blocked sound with the visible action when playback is permitted. The broadcaster hears no microphone playback from their own preview.
- **SC-008**: All previously passing stream checks still pass, including the multi-browser walkthrough for screen sharing, connection retry, end/stop behavior, fullscreen, display modes, and bullet comments. New browser checks demonstrate permission fallback, commentary delivery, mute behavior, explicit recovery, and microphone release.

## Assumptions

- Microphone enablement is offered after screen sharing starts. Commentary is optional for every broadcast and defaults to off.
- Muting means stopping outgoing commentary; it may keep the microphone in use for the current broadcast so unmuting does not require another permission prompt. Stopping sharing or leaving the broadcast releases that use. The interface must distinguish "Muted" from microphone off or unavailable.
- The browser or operating system controls permission decisions. The app provides guidance and an explicit retry action; it cannot override a user's denied permission.
- Existing logged-in viewing and owner-only broadcasting rules apply. Both existing sign-in paths remain supported.
- Scope is the broadcaster's default microphone only. Tab/system audio, audio mixing, device-selection menus, automatic device switching, audio-only broadcasts, co-hosts, recording/replay, and transcription are excluded.
- Existing supported desktop browsers and the current small-audience deployment are the target. Mobile broadcasting and broader cross-network reachability are not introduced by this feature.
- Microphone state is temporary. This feature introduces no user-facing audio history or saved microphone preference.
- The existing stream controls and screen-sharing workflow are prerequisites. The outstanding multi-browser validation in [feature 004, task T020](../004-stream-video-controls/tasks.md) must establish a baseline before claiming that those behaviors have no regressions.
- This feature extends the video-only assumptions of features 003 and 004 specifically to allow optional microphone commentary. Their other stream lifecycle, permission, and viewer-control requirements remain in effect.
