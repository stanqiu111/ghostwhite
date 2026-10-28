# Microphone Commentary Validation

## Local setup and run

On the user's local computer, use Python 3.12, Node 24/npm, and a supported desktop Chrome/Chromium browser with microphone and WebRTC access. From the checked-out feature branch (`work`):

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
npm ci
export DJANGO_DEBUG=1
python manage.py migrate --noinput
python manage.py createsuperuser
python manage.py runserver 127.0.0.1:8000
```

Open http://127.0.0.1:8000/authors/auth/. Use separate browser profiles for the owner and viewers; create/approve viewer accounts in `/admin/` (`approved` and `is_active` must be true). Use headphones for viewers on the broadcaster's computer. Loopback HTTP supports capture; access from a second computer requires an existing trusted HTTPS setup. No production deployment is needed.

## Automated checks

From the repository root with the virtual environment active:
```bash
source .venv/bin/activate
export DJANGO_DEBUG=1
python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py check
node --test streams/js_tests/*.test.cjs
python manage.py test streams --noinput
python streams/browser_tests/media.py
python manage.py test --noinput
```

The browser harness uses existing Playwright and /usr/bin/chromium (CHROMIUM_PATH may select an approved installed browser), a temporary real SQLite database, migrated local node and test accounts. It does not modify db.sqlite3. Native media APIs and peer connections use synthetic devices and a generated tone; energy/frame assertions test delivery when transport is available. Failure injections are labeled separately. Results are recorded in [validation.md](validation.md).

Additional modes:
```bash
python streams/browser_tests/media.py --baseline
python streams/browser_tests/media.py --capture-only
```

`--baseline` serves the stream template/JS from fixed pre-feature commit `1eb0a5bb933dbd7b632864da2dc2f90c3bb51e4a` in the temporary server without resetting the checkout. That commit must be present locally (use a full clone/history). `--capture-only` checks native capture/senders and browser UI with labeled fault injection; it does not claim media delivery. The temporary SQLite database uses Django's supported IMMEDIATE transaction mode to prevent concurrent signaling-poll lock upgrades.

This cloud Chromium installation enforces `WebRtcIPHandling=disable_non_proxied_udp` and produces no ICE candidates, even in a standalone local two-peer probe. `AudioCaptureAllowed`, `VideoCaptureAllowed` and `FullscreenAllowed` are also false. No permitted transport route is configured here. Do not override managed policy or substitute an executable/network route to evade it. Passing capture-only checks cannot complete transport validation.

## Remaining acceptance (local computer)

Set `CHROMIUM_PATH` to the installed Chrome/Chromium executable. For example, on macOS:
```bash
export CHROMIUM_PATH='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
python streams/browser_tests/media.py --baseline
python streams/browser_tests/media.py
```
On Linux the default is `/usr/bin/chromium`. Expected: both commands exit zero; the baseline establishes existing video/bullet/fullscreen behavior and the feature run reports received audio energy, advancing video frames, five-viewer mute/unmute and late joins, autoplay recovery, stop/restart/end, and controls with commentary active. These use synthetic capture and still do not establish physical devices or permission dialogs.

After automated transport succeeds, complete these manual checks in the supported desktop browsers and record browser/version and outcomes in validation.md:
- [ ] Start: no microphone prompt; explicit enable delivers speech to five viewers within 5 seconds; a late viewer hears speech within 10 seconds. Owner preview stays silent.
- [ ] Mute/unmute: controls and sound change within 1 second; late join while muted is silent; muted speech never replays. Local viewer volume/mute stays independent across recovery and reconnect.
- [ ] Permission/device: deny and dismiss, then explicitly retry after allowing access; unplug/revoke while active and muted. Feedback appears within 2 seconds and video continues. No automatic reacquisition.
- [ ] Cleanup: page stop, browser stop, end, navigate/reload/close, and a grant arriving after stop/restart all release capture within 1 second; restart stays off.
- [ ] Playback and existing controls: genuine autoplay blocking offers Enable sound while video continues; run [feature 004 S1–S4](../004-stream-video-controls/quickstart.md) with commentary active before marking T020 complete.

Do not equate synthetic capture or injected faults with physical-device/permission-dialog validation. The pre-feature full-suite baseline is 197 tests: 113 pass, 12 failures, 72 errors; all 75 stream tests pass.
