# Tasks: Optional Microphone Commentary

**Input:** spec.md, plan.md, research.md, data-model.md, contracts/microphone.md, quickstart.md.
**Tests:** Requested in the continuation; use real SQLite for Django/browser tests and explicitly labeled media simulations for asynchronous failure cases.

## Phase 1: Setup
- [X] T001 Inspect existing streams code and record the proposed architecture in specs/005-stream-microphone/plan.md and research.md.
- [X] T002 Reproduce the full Django baseline and record results in specs/005-stream-microphone/validation.md.

## Phase 2: Foundation
- [X] T003 Document transient state and unchanged public API in specs/005-stream-microphone/data-model.md and contracts/microphone.md; no migrations required.
- [X] T004 Add capture/sender test doubles and lifecycle harness in streams/js_tests/microphone.test.cjs; verify new assertions fail before implementation.

## Phase 3: US1 — Enable commentary (P1)
**Goal/test:** Existing and newly joining viewers receive audio after owner opt-in; the existing video peer remains connected.
- [X] T005 [US1] Add default-off and opt-in regression tests in streams/js_tests/microphone.test.cjs and owner/viewer/ended-page tests in streams/tests.py.
- [X] T006 [US1] Implement capture/controller and reserved sender/data-channel integration in streams/static/streams/microphone.js and screenshare.js.
- [X] T007 [US1] Add accessible owner controls in streams/templates/streams/stream_detail.html and streams/static/streams/streams.css.

## Phase 4: US2 — Broadcaster mute (P1)
**Goal/test:** Existing and late viewers hear silence during mute; unmute does not request permission again.
- [X] T008 [US2] Add shared-track mute/late-join tests in streams/js_tests/microphone.test.cjs.
- [X] T009 [US2] Implement mute/unmute state and controls in streams/static/streams/microphone.js.

## Phase 5: US3 — Failure and recovery (P1)
**Goal/test:** Denial, unavailable hardware and loss preserve video; only explicit retry reacquires commentary.
- [X] T010 [US3] Add denial/retry, unsupported device and ended-track regression cases in streams/js_tests/microphone.test.cjs.
- [X] T011 [US3] Implement failure feedback, ended handling and ordered sender replacement in streams/static/streams/microphone.js.

## Phase 6: US4 — Stop and permission races (P1)
**Goal/test:** Stop/end/page departure release microphone capture, including stale permission results after restart.
- [X] T012 [US4] Add deferred-permission and stop/restart regression cases in streams/js_tests/microphone.test.cjs.
- [X] T013 [US4] Integrate generation guards and unconditional cleanup in streams/static/streams/microphone.js and screenshare.js.

## Phase 7: US5 — Viewer playback (P2)
**Goal/test:** Audio becomes available mid-stream; local preferences remain local; blocked audio falls back to video with Enable sound.
- [X] T014 [US5] Implement explicit audio availability and playback-policy handling in streams/static/streams/player_controls.js and stream_detail.html.
- [X] T015 [US5] Add meaningful playback state/regression tests in streams/js_tests/playback.test.cjs.

## Phase 8: Integration and validation
- [X] T016 Add isolated Django/native Chromium multi-viewer media validation in streams/browser_tests/media.py and media.cjs.
- [X] T017 Run final Node, Django, migration/static and browser checks; record precise results and baseline comparison in specs/005-stream-microphone/validation.md.
- [X] T018 Update WORKFLOW.md and specs/005-stream-microphone/quickstart.md with final behavior and human validation limits, including overlapping feature 004 T020 coverage.
- [X] T021 Conduct independent focused review, fix immediate-mute and pinned-baseline defects, strengthen harness assertions and rerun affected checks.
- [X] T022 Correct Mac-discovered harness assertions, isolate genuine autoplay observation from test-generated activation, improve test-server diagnostics, and run available checks before the next local acceptance run.
- [X] T023 Verify the unchanged shipped harness on Mac at `1f7a2c8e3640e6bc872292603a9f648ff51428a4`: server check, baseline (3 checks), and feature (15 checks) passed, including synthetic transport and genuine incoming-stream autoplay; record the attributed result in validation.md.

## Dependencies and execution order
T001–T004 precede implementation. US1 establishes the transport; US2–US4 extend the same controller sequentially. US5 depends on the availability contract. T016–T018 follow the integrated implementation. Tests precede their corresponding code changes. No schema, package or deployment changes are planned.

## Parallel opportunities
Research of transport and browser capabilities is independent. US1 template tests and US2–US4 Node tests can be reviewed independently, but controller edits are sequential. US5 playback tests and the browser harness concern separate files after the media contract is stable.

## Implementation strategy
First prove opt-in audio with video preserved, then mute/error/cleanup behavior, then viewer playback and real-media checks. Complete all authorized phases; do not deploy or stop at the plan handoff. Mark tasks complete only after their stated work and verification finish.

## Verification status
All implementation and automated-check tasks above are complete. Managed cloud Chromium still blocks transport, but the unchanged shipped harness passed on the Mac with five-viewer synthetic delivery, genuine incoming-stream autoplay recovery, and lifecycle cleanup. The exact tested commit and attributed evidence are in validation.md. Physical hardware, real permission/device interactions, the manual supported-browser matrix/T020, and explicit end-user timing acceptance remain open.

- [ ] T019 Complete the remaining physical-device, real permission/device interaction, manual browser matrix/T020, and explicit timing validation from specs/005-stream-microphone/quickstart.md; record results in validation.md. The automated native delivery portion is complete under T023.
