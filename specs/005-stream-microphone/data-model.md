# Data Model: Microphone Commentary

No database changes or migrations. Existing Stream, StreamSignal and author ownership remain unchanged.

## Broadcast session
Existing display stream plus monotonically increasing local generation. A stop/restart invalidates outstanding capture and peer setup operations.

## Microphone controller
- active: whether screen sharing is active.
- state: off, requesting, on, muted, unavailable.
- capture: separate microphone MediaStream or null.
- pending request: one in-flight getUserMedia operation, tied to its generation.
- peers: reserved audio senders, ordered update chains and reliable metadata channels.
Transitions: begin → off; explicit enable/retry → requesting → on or unavailable; on ↔ muted; ended/revoked → unavailable; stop → off. A stale result stops its tracks and does not change the current session. No automatic recovery.

## Viewer listening state
Availability supplied by the owner; requested volume and mute retained for the page visit; temporary autoplay-blocked state is separate. Connection reset clears availability but preserves preference. Commentary is not recorded or saved.
