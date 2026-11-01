# Implementation Plan: Optional Microphone Commentary

**Branch**: `work` | **Date**: 2026-10-28 | **Spec**: [spec.md](spec.md)

## Summary
Add opt-in microphone commentary to an active screen share. Reserve a send-only audio transceiver in each initial peer connection and attach/detach the microphone with replaceTrack; mute using the shared track's enabled state. Send commentary availability over a reliable data channel on the same authenticated owner/viewer connection. Video requires no renegotiation. A separate microphone controller owns permission races and capture cleanup; a viewer playback controller owns local volume, mute and autoplay recovery.

## Technical Context
- Language/version: Python 3.12, Django 5.1.1, browser JavaScript, Node 24.
- Dependencies: existing DRF, native WebRTC/media APIs and Playwright 1.61; no application dependencies added.
- Storage: existing SQLite/PostgreSQL unchanged. Commentary state is transient; no migration.
- Testing: Node test runner for simulated lifecycle errors, Django real-DB template/auth checks, Playwright with native Chromium capture/peer connections and synthetic devices.
- Platform: supported desktop browsers; available automated media target is Chromium 154.
- Performance: preserve spec's five-viewer scope, enable within 5 s, mute/unmute within 1 s, join within 10 s.
- Constraints: no tab audio, recording, device picker, audio-only mode, new service, new API schema or persistent microphone preferences.

## Constitution Check
All gates pass before and after design:
1. Model-first: state model documented in data-model.md; no persisted data/schema changes.
2. Dual auth: retain session/JWT signaling; microphone controls use existing server-rendered is_owner context.
3. Real database: Django/browser integration uses real isolated SQLite; simulated media tests do not mock database calls.
4. Validation: existing server serializer ownership and signaling validation are unchanged.
5. Relationship state: owner controls are conditional in Django templates.
6. CSS: new controls use streams/static/streams/streams.css; no inline styles.
7. Public contract: existing FQIDs/REST responses unchanged; direct media metadata is documented separately.
8. Simplicity: one reserved sender per peer avoids a renegotiation protocol. No feature flags or compatibility layer.

## Project Structure
Documentation: spec.md, plan.md, research.md, data-model.md, contracts/microphone.md, quickstart.md, tasks.md, validation.md.

Source:
- streams/static/streams/microphone.js — capture lifecycle, sender replacement, metadata.
- streams/static/streams/screenshare.js — reserve audio, peer integration, stale-session guards and teardown.
- streams/static/streams/player_controls.js — viewer listening preference and autoplay recovery.
- streams/templates/streams/stream_detail.html and streams/static/streams/streams.css — owner controls and viewer feedback.
- streams/tests.py — real-DB owner/viewer/ended-page coverage.
- streams/js_tests/microphone.test.cjs — simulated capture/sender lifecycle regressions.
- streams/browser_tests/media.py and media.cjs — isolated Django + real browser media harness.

## Execution
1. Record baseline and write lifecycle regression tests.
2. Implement microphone controller and peer integration, then owner controls.
3. Implement viewer audio availability/playback handling.
4. Run focused/full Django suites, Node checks and browser media scenarios; preserve baseline failures.
5. Document exact simulated, native synthetic-media and remaining manual outcomes. Complete overlapping T020 checks without claiming its human walkthrough is finished.

## Complexity Tracking
No constitution exceptions. Reserved audio requires explicit availability metadata because a negotiated receiver track alone does not mean microphone capture has started.
