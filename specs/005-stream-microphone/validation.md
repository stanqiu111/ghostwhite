# Microphone Commentary: Validation Results

**Date:** 2026-10-28

**Status:** Implementation complete; media delivery and physical-device validation remain blocked/unrun.

**Baseline commit:** `1eb0a5bb933dbd7b632864da2dc2f90c3bb51e4a`

## Automated results

| Check | Result |
|---|---|
| Reproduced full Django baseline | 197 executed: 113 passed, 12 failures, 72 errors |
| Final full Django suite | 200 executed: 116 passed, 12 failures, 72 errors |
| Failed/error test identities | Exact set of 84 matches baseline; zero new unsuccessful cases |
| Focused Django streams suite | All 78 passed, including three new owner/viewer/ended-page tests |
| Node media/playback regressions | All 21 passed; zero skipped, including the review's delayed-sender mute regression |
| Chromium capture-only harness | All 11 checks passed (six native synthetic-capture/sender/API checks, five explicitly injected failure scenarios) |
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

## Transport blocker and T020

Both the original committed browser code (`--baseline`) and the final feature (`media.py`) failed to establish a media connection. Offer/answer exchange completed and ICE gathering completed, but the browser produced no usable connection candidates and remained in the new/connecting state. A separate native two-peer probe with no STUN server also generated zero ICE candidates.

The exact harness error was `page.waitForFunction: Timeout 30000ms exceeded` in `connected()`. Both sides reported `connectionState=new`, `iceConnectionState=new`, `iceGatheringState=complete`, `signalingState=stable`, with local/remote offer/answer present. The installed managed policy at `/etc/chromium/policies/managed/misc.json` sets `WebRtcIPHandling=disable_non_proxied_udp`, `AudioCaptureAllowed=false`, `VideoCaptureAllowed=false`, and `FullscreenAllowed=false`. Successful capture checks used synthetic test devices. Policies were not modified or overridden.

Final review confirmed no documented, already permitted transport route in this environment: the app config contains only a STUN server and no TURN relay; environment status reports no extra capabilities, runtime variables, secrets or outbound identities, with restricted package-manager network access. No further blocked transport attempt was made during review. Local-computer validation is the remaining route, not a workaround inside this runtime.

Consequently, the following are **unverified**, not passed:
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

No credentials from the temporary browser accounts are printed. The harness creates and removes its own database and generated audio fixture; the development database is untouched.
