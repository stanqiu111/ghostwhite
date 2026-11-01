# Federated streaming validation

Date: 2026-11-01. Implementation on `work`, based on
`cb3edba4ecb84e605feaebf4ae72de201e406b68`. No deployment performed.

## Completed checks

| Check | Observed result |
| --- | --- |
| `python manage.py test streams --noinput` | 99 passed: previous 78 + 21 federation regressions |
| `node --test streams/js_tests/*.test.cjs` | 27 passed, including asymmetric host/viewer TURN refresh/renewal and revocation cleanup simulations |
| `python streams/browser_tests/federation.py --browser` | Two real processes, separate SQLite databases and HTTP origins; 5 HTTP groups and 5 browser groups passed; no browser page errors |
| `python streams/browser_tests/media.py --capture-only` | 13 passed; no server errors/slow requests |
| `python streams/browser_tests/media.py --ui-check` | 8 groups passed; no page errors, server errors or slow requests |
| Complete Django suite | 221 total: 137 passed, 12 failures, 72 errors |
| Full-suite baseline comparison | All 84 failure/error identifiers exactly match `microphone-final-suite.log`; no additions/removals |
| Schema | Fresh disposable database migrated including 0004; no pending migrations; model/migration check passed |
| Syntax/static/checks | Python/Django/JavaScript syntax checks, static collection, whitespace checks passed |

HTTP checks prove reciprocal node discovery, a home-node viewer page without
a host login, real join/offer/answer envelope relay, chat identity/literal
content, owner-role rejection, node disable/re-enable, ended state and mailbox
cleanup. The HTTP relay fixture uses opaque strings, not playable SDP.

Browser checks prove discovery/navigation on the home origin, absent host
controls/credentials, real cross-node chat rendered as inert text, desktop and
390px mobile layout, terminal access-error handling and ended-room cleanup.
The browser revocation response is explicitly injected; HTTP node-disable tests
use real node rows. Neither is a native media revocation acceptance test.

Native capture checks use synthetic browser devices and include injected error
cases. They do not prove physical devices or media transport. TURN credential
expiry/renewal checks advance/simulate state and inspect peer lifecycle; no real
TURN allocation or hour-long browser test was performed.

Cloud-local screenshots were visually inspected:
`/tmp/ghostwhite-federation-preview/remote-desktop.png` and `remote-mobile.png`.
They show truthful waiting state, remote host identity, readable chat and
accessible viewer controls without horizontal overflow. Content is synthetic.
These paths are not uploads or transfers to a local computer.

Logs are cloud-local under `/workspace/ghostwhite-setup/`:
`federation-streams-final.log`, `federation-js-final.log`,
`federation-browser-final.log`, `federation-capture.log`, `federation-ui.log`,
`federation-full-suite.log`, and `federation-static.log`.

## Review findings addressed

- Added typed bounds for remote metadata, signal recipients/payloads, chat IDs,
  cursor order and acknowledgements; non-finite/deeply recursive JSON is rejected.
- Replaced predictable mirror usernames to prevent local-name occupation from
  blocking remote users. Mirrors retain unusable passwords.
- Matched local description support instead of rejecting otherwise valid rooms.
- Added fresh TURN credentials before new peer creation and scheduled renewal
  on both host and viewer before their respective expiry, with cancellation
  when access is revoked. Disabled remote page requests return 403, not 500.
- Host signaling polls repeatedly send close instructions for disabled-node
  peers until room end, including after a lost poll response. Viewer/chat
  terminal errors stop their activity.
- Chat bootstrap cursor now comes from its returned batch, avoiding skipping a
  concurrent message inserted between separate bootstrap/cursor queries.

The HTTP client uses connect and read-inactivity timeouts, **not an absolute
request deadline**. A trusted but slow/dripping node may retain an outbound
worker longer. This limitation is explicit in the protocol/setup guide; no
unconfigured hosting-layer deadline is claimed.

## Remaining acceptance — not passed

- [ ] Native audio/video delivery across the two-node adapter. The managed
  cloud WebRTC restriction remains in force; it was not disabled or bypassed.
- [ ] Two HTTPS domains on different networks, with operator-configured TURN
  where direct connectivity fails. Node credentials must remain server-side.
- [ ] More-than-one-hour TURN allocation/credential renewal and reconnection.
- [ ] Host-side node disable actually stops an established native media peer.
- [ ] Physical microphone, permission dialogs/denial/retry, device revocation,
  audible output, browser matrix/T020 and explicit end-user timing acceptance.
- [ ] Compatibility with an actual third-party implementation of this extension.

The prior Mac result on `1f7a2c8` covers the earlier microphone implementation,
not this federation adapter. The full Django suite is not clean.

Next on an approved local machine, with existing dependencies and Chrome:

```bash
source .venv/bin/activate
python manage.py migrate
python manage.py collectstatic --noinput
python streams/browser_tests/federation.py --media
python streams/browser_tests/media.py
```

Set `CHROMIUM_PATH` to the approved browser executable if necessary. These
harnesses use their own databases. Configure actual reciprocal nodes and TURN
using [the integration guide](../../docs/FEDERATED_STREAMING.md) for the separate
cross-network and physical-device checks.
