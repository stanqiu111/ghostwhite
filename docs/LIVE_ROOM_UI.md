# Live-room UI review

This UI pass is based on `40321818c5eda0787b72660b325f852b803d07b8` on `work`.
Desktop and mobile visual review passed. This version is ready for local QA;
the review does not establish end-to-end media acceptance or authorize deployment.

## Layout and behavior

- A flexible 16:9 stage and 320px chat rail share a room up to 1600px wide.
  Narrow layouts place chat after the stage/channel identity and before the
  description. Theater mode expands the stage and moves chat below it.
- The existing ÉTHÉRÉ header, Inter stack, blue accent, red on-air state, and
  light/dark tokens are retained. New styles load only on the stream detail
  page; stream list/create pages and global theme files are unchanged.
- Owner screen-sharing, microphone, and end controls form one console.
  Primary, disabled, and destructive controls remain distinct in dark mode.
- Room presentation follows the existing media UI: off air, waiting for host,
  connecting, live, connection issue, and ended. A server-side open room is
  not labeled as actively broadcasting before capture/connection begins.
- There is no authoritative audience-count API. No audience count or other
  metric was invented. The existing global header's room count is not reused
  as a viewer count.
- Chat uses the existing bullet API and real sender/content/timestamps. It
  starts with the latest 30 messages and retains at most 100 DOM messages.
  Content uses text nodes; stale batches are deduplicated and the polling
  cursor stays monotonic. Reading position is preserved, with a latest-message
  action. Disabling the video overlay leaves chat active and never replays
  old overlay messages when enabled again.
- Loading, reconnecting, closed-chat, and send-error feedback are visible.
  An independent review found a late-error race that could revive closed-chat
  wording; stopped guards and deferred-error regressions now cover it.

Existing capture, mute, autoplay recovery, volume, display-mode, overlay and
fullscreen IDs/conditions remain. There are no production backend, model,
signaling, microphone-controller, or playback-controller changes.

## Files

- `streams/templates/streams/stream_detail.html`: stage, channel identity,
  role-specific console, and conversation layout.
- `streams/static/streams/stream_room.css`: detail-only responsive/themed styles.
- `streams/static/streams/stream_room.js`: presentation of existing media state.
- `streams/static/streams/bullets.js`: persistent chat alongside the existing overlay.
- `streams/browser_tests/ui.cjs` and `media.py`: isolated visual/UI checks.

## Verification

| Check | Result |
|---|---|
| Django streams suite | 78 passed |
| Existing microphone/playback JavaScript regressions | 21 passed |
| Native browser capture/UI regression harness | 13 checks passed; zero server errors/slow requests |
| New UI browser harness | 8 groups passed; no page errors or horizontal overflow at tested widths |
| Syntax, Django check, static collection, diff whitespace | Passed; 183 collected static assets |
| Independent review | No remaining blocking finding after the closed-chat race fix |
| Rendered visual review | Desktop and 390px mobile screenshots inspected; primary actions visible, readable light/dark text, no clipping or horizontal overflow |

The UI harness covers owner/viewer conditions, real chat send/receive, literal
markup rendering, overlay toggle/no replay, keyboard focus, selected text
contrast of at least 4.5:1 in both themes, native synthetic sharing/mute/stop,
1440px and 390px layouts, reduced motion, history bounds/deduplication/scroll,
late-error cleanup, reconnect feedback, and real stream ending.

The full Django suite was not rerun for this scoped UI pass; its previously
recorded 12 failures and 72 errors remain documented in the
[microphone validation report](../specs/005-stream-microphone/validation.md).

## Reproduce and inspect

With the existing Python environment and Node dependencies installed:

```bash
source .venv/bin/activate
python manage.py collectstatic --noinput
python streams/browser_tests/media.py --ui-check
python streams/browser_tests/media.py --capture-only
node --test streams/js_tests/*.test.cjs
python manage.py test streams --noinput
```

The harness uses a temporary real SQLite database and neutral test accounts;
it does not touch the development database. Set `CHROMIUM_PATH` to an approved
installed Chrome/Chromium executable as needed. Screenshots are written to
`/tmp/ghostwhite-ui-preview` (override with `STREAM_UI_OUTPUT`). Principal files:

- `owner-idle-desktop-light.png`
- `owner-live-muted-desktop-dark.png`
- `viewer-waiting-desktop-light.png`
- `viewer-stage-desktop-dark-simulated.png`
- `owner-idle-mobile-dark.png`
- `viewer-mobile-light-simulated.png` and `viewer-mobile-dark-simulated.png`
- `viewer-mobile-error-simulated.png`
- `ended-desktop-light.png`

The active viewer stage and player-error screenshots explicitly simulate UI
state with a neutral canvas stream. They are not evidence of delivered media.
Owner capture uses Chromium synthetic devices; chat messages are actual test
API submissions, including a literal script probe. No private screen content
or real personal messages are used.

Cloud logs are under `/workspace/ghostwhite-setup/`: `ui-review.log`,
`ui-media-regression.log`, `ui-streams.log`, and `ui-js.log`.

## Remaining local QA

Coordinate local QA of the new layout with the full media harness on the Mac, where WebRTC is
permitted. The previous Mac result applies to the earlier microphone commit,
not this UI revision. Managed cloud WebRTC policy remains unchanged. Physical
microphone/permission interactions, the manual supported-browser matrix/T020,
and explicit end-user timing acceptance remain pending.
