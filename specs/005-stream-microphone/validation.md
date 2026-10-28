# Microphone Commentary: Validation Results

**Date:** 2026-10-28

**Status:** Implementation complete; local diagnostic copies exercised media delivery, but the corrected committed harness still requires a local rerun. Physical-device, genuine incoming-autoplay and timing acceptance remain pending.

**Baseline commit:** `1eb0a5bb933dbd7b632864da2dc2f90c3bb51e4a`

## Automated results

| Check | Result |
|---|---|
| Reproduced full Django baseline | 197 executed: 113 passed, 12 failures, 72 errors |
| Final full Django suite | 200 executed: 116 passed, 12 failures, 72 errors |
| Failed/error test identities | Exact set of 84 matches baseline; zero new unsuccessful cases |
| Focused Django streams suite | All 78 passed, including three new owner/viewer/ended-page tests |
| Node media/playback regressions | All 21 passed; zero skipped, including the review's delayed-sender mute regression |
| Chromium capture-only harness after Mac harness fixes | All 13 checks passed: six native synthetic-capture/sender/API checks, exact bullet rendering, native file-autoplay preflight, and five explicitly injected failure scenarios |
| Isolated server concurrency check | 72 polls across six concurrent loops plus 10 total logins passed; maximum client duration 732 ms; zero server errors or requests at least 3 seconds |
| JavaScript syntax | microphone.js, screenshare.js, player_controls.js and media.cjs passed |
| Django system and migration checks | check, makemigrations --check --dry-run, migrate --check passed; no schema changes |
| Static collection / diff whitespace | collectstatic --noinput and git diff --check passed; 181 static assets retained |

Tests were added before the corresponding code: the 15 microphone cases initially failed because the controller did not exist; the five playback cases initially failed because StreamPlayback did not exist. Two of the three new Django page tests failed before the controls were added. The ended-page absence case already passed.

The unchanged legacy failures comprise 31 NoReverseMatch errors, 41 duplicate-local-node fixture errors, and 12 assertion failures against stale paths/payloads. The final full suite is **not green**.

## What native browser checks established

Chromium 154.0.8037.57 with Playwright 1.61.0 used real getDisplayMedia/getUserMedia, RTCPeerConnection, sender replacement, HTML media playback and Django signaling. Hardware sources were Chromium synthetic devices; no physical microphone or screen picker was used.

Six checks without injected application failures established:
1. Screen capture starts with microphone off; explicit enable captures a live microphone; the owner preview stays muted.
2. After a real SDP exchange, a native sender accepts the microphone while retaining the same peer and video track. This establishes sender replacement, not delivered media.
3. Existing and late native senders reference a disabled microphone track while the broadcaster is muted.
4. Mute/unmute toggles that native track without stopping native screen capture.
5. Stop while muted ends native microphone capture; a new share defaults to microphone off.
6. The real end-stream API action ends the stream and removes broadcast controls.

Five fault-injected browser scenarios established:
- Rejected audible play falls back to native muted video; Enable sound restores native playback.
- An injected ended-device event preserves native screen capture and explicit retry reacquires a native microphone.
- Injected permission denial preserves video; explicit retry uses native capture.
- A deliberately delayed result wrapping native microphone capture is released after stop.
- An injected display-capture-ended event releases the native microphone.

These supplement the Node simulations for denial classes, unsupported capture, duplicate requests, stop/restart races, muted device loss, sender update ordering and viewer preference retention. They do not prove physical unplug/revocation or a genuine permission-dialog interaction.

After the Mac harness corrections, the capture-only run also verified the real bullet API/DOM preserves the exact message text beside the sender label with no script node/execution. A native file-audio preflight observed `NotAllowedError` with `navigator.userActivation.hasBeenActive=false`; this validates the non-activating observation method, not incoming WebRTC autoplay.

## Transport blocker and T020

Both the original committed browser code (`--baseline`) and the final feature (`media.py`) failed to establish a media connection. Offer/answer exchange completed and ICE gathering completed, but the browser produced no usable connection candidates and remained in the new/connecting state. A separate native two-peer probe with no STUN server also generated zero ICE candidates.

The exact harness error was `page.waitForFunction: Timeout 30000ms exceeded` in `connected()`. Both sides reported `connectionState=new`, `iceConnectionState=new`, `iceGatheringState=complete`, `signalingState=stable`, with local/remote offer/answer present. The installed managed policy at `/etc/chromium/policies/managed/misc.json` sets `WebRtcIPHandling=disable_non_proxied_udp`, `AudioCaptureAllowed=false`, `VideoCaptureAllowed=false`, and `FullscreenAllowed=false`. Successful capture checks used synthetic test devices. Policies were not modified or overridden.

Final review confirmed no documented, already permitted transport route in this environment: the app config contains only a STUN server and no TURN relay; environment status reports no extra capabilities, runtime variables, secrets or outbound identities, with restricted package-manager network access. No further blocked transport attempt was made during review. Local-computer validation is the remaining route, not a workaround inside this runtime.

Consequently, the following were **not established by the recorded cloud run**:
- Received audio energy, audible speech and uninterrupted video across five viewers.
- Delivered silence/resumption for current and late viewers, and end-to-end timing.
- Real incoming-stream autoplay restrictions (local synthetic streams can receive a capture exemption; rejection handling was injected).
- Transport-dependent multi-browser bullet/overlay, fullscreen and lifecycle checks in feature 004 T020.
- Physical device disconnect, actual microphone permission prompts, audible echo and the manual supported-browser matrix.

T020 remains unchecked. Its overlapping native screen-capture/start/stop and owner-preview paths were exercised; this is not completion of its multi-browser walkthrough.

## Focused implementation review

An independent reviewer examined lifecycle generations, sender ordering, repeated toggles, muted late joiners, disconnect/retry, stale channel messages, and playback preferences. Two defects were fixed:
- A pending flag covered sender attachment as well as permission, disabling Mute while fast viewers could already receive audio. It now clears once capture resolves. A regression first failed, then passed with a delayed sender and 21 repeated toggles; the slow viewer receives the same disabled track.
- The browser baseline read HEAD and would silently become the feature after commit. It now pins the documented pre-feature commit.

The harness now stays within five active viewers, repeats bullet/display/fullscreen checks with commentary active, and explicitly checks display-track identity/liveness through mute/unmute. Transport-dependent additions remain unrun here. Review found no further introduced production defect. The inherited Player.poll/handleOffer race with an in-flight offer after end/reset predates this feature and remains a separate follow-up; these checks do not establish that every existing reconnect race is resolved.

The temporary test server uses SQLite IMMEDIATE transactions. The initial baseline run exposed read-to-write lock-upgrade contention with concurrent signaling polls; changing only the test database's supported transaction mode removed that setup failure. Application database configuration is unchanged.

## Local feedback and harness corrections

The Mac validation thread reported that diagnostic copies exercised five-viewer synthetic transport and stop/restart. Those copies are useful evidence, not a passing run of the shipped harness or physical/timing acceptance. Chrome 156 exposed these harness defects:
- Bullet content was compared against the entire element, including its sender label. The assertion now checks the exact final text node and separately checks that no script element or script execution occurs.
- A deliberately locally muted viewer was incorrectly required to accumulate incoming energy. The harness now checks its native mute/volume state and advancing frames, checks energy for the other listening viewers, then explicitly unmutes and proves energy for that viewer before restoring its preference. Browser RTP statistics may differ for muted sinks.
- The autoplay setup used Playwright evaluations that can grant user activation. The installed Playwright implementation sends `userGesture:true` for these evaluations. The corrected setup observes native play outcomes without replacing promises, records activation, and uses CDP `userGesture:false` until rejection is established. A native file-audio preflight is separate from genuine incoming-stream coverage. Missing native denial stays a failed acceptance check; lifecycle checks continue and the run still exits nonzero.

A late Mac login timed out after 30 seconds in a run that also reported SQLite locking at signaling's IMMEDIATE transaction. Causality was not established. The harness now uses Django's standard threaded server (worker connection cleanup), closes fixture connections, enables WAL only for its temporary database, and logs slow/error request timing. The new `--server-check` exercises concurrent real signaling polls and late logins without media. Normal Django request cleanup already existed, so the server change alone is not proof of the timeout's root cause. No production database configuration changed.

Verification of the corrected harness in the cloud: JavaScript/Python syntax and all 21 application JavaScript regressions passed; capture-only passed all 13 checks with zero server errors/slow requests (113 requests total). The server-only check passed all 82 requests with maximum server duration 0.711 seconds. Its empty signaling queues exercise transaction contention, not delivery; neither run proves default application SQLite settings are contention-free. Independent review found no blocking defect in the revised harness. Full transport was not retried in the restricted cloud environment.

These corrections require a clean local rerun of `--baseline` and full mode. T019 and feature 004 T020 remain open; physical permission/device behavior and the timing thresholds are not inferred from bounded functional polling.

## Exact remaining action

In an approved environment permitting local WebRTC transport (or providing an approved compatible relay), from the repository root run:
```bash
source .venv/bin/activate
python streams/browser_tests/media.py --baseline
python streams/browser_tests/media.py
```
Then complete the physical-device and multi-browser walkthrough in [quickstart.md](quickstart.md), including feature 004 T020. Do not evade managed browser policy or treat a passing `--capture-only` run as proof of transport.

Locally repeatable checks in the current environment:
```bash
node --test streams/js_tests/*.test.cjs
python manage.py test streams --noinput
python streams/browser_tests/media.py --capture-only
```

## Retained logs
Current-instance evidence is under /workspace/ghostwhite-setup/:
- microphone-baseline.log and microphone-final-suite.log
- microphone-streams.log, microphone-js-final.log and microphone-js-review.log
- media-baseline.log, media-final.log, media-capture.log and media-capture-review.log
- media-server-fix.log, media-capture-harness-fix.log and media-harness-js.log

No credentials from the temporary browser accounts are printed. The harness creates and removes its own database and generated audio fixture; the development database is untouched.
