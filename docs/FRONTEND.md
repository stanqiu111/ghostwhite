# Frontend guide

[Documentation index](README.md) · [Shipping](SHIPPING.md) · [Live rooms](LIVE_ROOM_UI.md)

Ghostwhite serves Django templates with plain CSS and JavaScript. There is no
frontend bundler or npm build step. `npm ci` installs the Playwright test tooling.

## Where to edit

| Area | Templates | Styles / behavior |
| --- | --- | --- |
| Shared navigation | `authors/templates/partials/header.html` | `static/css/main.css`, `static/js/common.js` |
| Landing, network, feed | `authors/templates/` | `authors/static/authors/{landing,network,home}.css` |
| Authentication, settings, nodes, staff | `authors/templates/authors/` | Matching files in `authors/static/authors/` |
| Profiles | `authors/templates/authors/profile_page.html` | `authors/static/authors/profile.css` |
| Composer and entry detail | `entries/templates/entries/` | `entries/static/entries/{create_entry,entry_detail}.css` |
| Notifications | `inbox/templates/inbox/inbox.html` | `inbox/static/inbox/inbox.css` |
| Stream directory and creation | `streams/templates/streams/` | `streams/static/streams/streams.css` |
| Live room | `streams/templates/streams/stream_detail.html` | `stream_room.css`, `screenshare.js`, `player_controls.js`, `stream_room.js`, `microphone.js`, `bullets.js` in `streams/static/streams/` |

Page styles are scoped by a body class. Keep page layout in its app's CSS,
shared navigation in `main.css`, and theme values in `theme.css`. Preserve live
video nodes, IDs, `[hidden]` behavior, chat cursor and microphone lifecycle hooks.

## Theme and spacing

Load `main.css`, page CSS, then `theme.css`. Load `common.js` in the head so it
sets `html[data-theme]` before paint. A stored `theme` preference wins; without
one, the OS preference applies. Theme changes synchronize between tabs.

Use `--gw-bg`, `--gw-surface`, `--gw-surface-2`, `--gw-text`, `--gw-text-dim`,
`--gw-border` and the accent/status tokens. A primary control pairs
`--gw-accent` with `--gw-on-accent`. Fixed dark video/code surfaces must define
their own readable foregrounds. Avoid an extra layer of dark-only component
overrides or JS that writes hardcoded colors.

Use the 4 px spacing scale. Content generally has 24 px desktop gutters and
16 px phone gutters, with 24–32 px between sections. The shared header stays
edge-to-edge and wraps its controls/search on narrow screens. Let long URLs,
entry text and grid columns shrink/wrap. Compose, read, browse and settings
pages retain layouts suited to their purpose; do not wrap every section in a
large decorative card.

Use native labeled controls, visible focus and the existing reduced-motion
preference. Keep ordinary text at least 4.5:1 and large text at least 3:1.
Check hover, disabled, selected, empty, error and mobile states as well.

## Content and assets

`static/js/marked.min.js` and `purify.min.js` are intentionally vendored runtime
libraries. Markdown should go through `renderSafeMarkdown()` in `common.js`;
if either library fails to load, it returns escaped text. Use `textContent` for
plain text and chat. Never insert untrusted Markdown directly with `innerHTML`.

The retired placeholder `entries/static/entries/markdown-editor.min.js`, its
stale source map, and unused `esbuild` / npm `marked` dependencies were removed.
The actual vendored renderer remains. Migrations and earlier specifications are
not disposable build output.

## Verification

From the repository root, with the Python virtual environment active:

```bash
npm ci
python manage.py check
python manage.py collectstatic --noinput
python streams/browser_tests/media.py --frontend-check
python streams/browser_tests/media.py --ui-check
node --test streams/js_tests/*.test.cjs
```

Set `CHROMIUM_PATH` to an installed, permitted Chrome/Chromium if it is not
`/usr/bin/chromium`. The frontend runner uses an isolated temporary SQLite
database and synthetic accounts/content. It renders 17 routes at 1440 and
390 px in both themes, checks horizontal overflow, solid-color text contrast
and browser exceptions. Additional checks exercise hover/error states, comment
editing, safe Markdown, keyboard focus and theme persistence. It writes screenshots plus `audit.json` beneath
`$STREAM_UI_OUTPUT/frontend` (default `/tmp/ghostwhite-ui-preview/frontend`).
`--audit` records failures without asserting success, for an explicit baseline.

Review the screenshots too: computed contrast does not cover text over images,
gradients, visited-link styling, or the usability of a composition. Browser UI
checks do not establish WebRTC transport, physical microphone behavior or
cross-browser acceptance. Those remain separate in the linked validation records.

## Review record — 2026-11-01

The cleanup was reviewed independently. Findings in Save, Follow, Unfollow,
comment-action hover states and login errors were fixed with explicit theme
color pairs. The mobile profile now has a device viewport, full-width fields,
and shorter empty sections. Entry sharing normalizes the API's uppercase
visibility values; comment editing and tab visibility use explicit hidden state.

| Check | Result |
| --- | --- |
| Whole-site frontend runner | 110 audited states: 68 page/theme/width combinations plus 42 hover/error/editor states; no horizontal overflow, measured contrast failures or browser exceptions. |
| Additional frontend interactions | Actual local comment save, likes/share visibility, sanitized Markdown and escaped fallback, OS preference, stored preference, cross-tab changes and focus passed. Remote follow/pending/unfollow color checks use synthetic DOM states, not remote follow delivery. |
| Existing live-room UI runner | 8 groups passed, including chat, role differences, keyboard focus, reduced motion, simulated capture and ended/error states. |
| JavaScript stream tests | 27 passed; simulations of lifecycle and playback behavior. |
| Native capture-only browser runner | 13 passed with synthetic devices and injected errors; no physical microphone or end-to-end transport claim. |
| Two-node federation runner with `--browser` | 5 HTTP and 5 browser checks passed, using separate local servers; media transport was not attempted. |
| Full Django suite | 221 tests: 137 passed, 12 failures, 72 errors. All 84 unsuccessful test identities match the recorded `228bee1` baseline; no new failures. |
| Configuration, assets and dependencies | Django check, collectstatic, JS syntax, pip check, npm clean install/audit, relative documentation links and diff whitespace checks passed. npm audit found 0 vulnerabilities. |

The unavailable-peer fixture intentionally returns HTTP 503 (four responses
across the two themes); the Markdown probes intentionally request missing images.
These exercise error presentation and inert markup. Screenshots were visually
reviewed for feed, profile, composer, entry, node, settings and live-room layouts.
Re-run the commands above to generate fresh evidence; local `/tmp` screenshots
are not published or transferred to another machine automatically.

Managed Chromium still blocks WebRTC media transport in this cloud environment.
Physical-device, real permission-interaction, browser-matrix/T020 and explicit
end-user timing acceptance remain pending in the feature records. This frontend
review does not mark those acceptance tasks complete.
