# Federated live streams

User scope: two Ghostwhite nodes must interoperate; publish the contract for
third-party implementations. No production deployment or paid service setup.

## Design

- Each node owns its streams. Do not copy foreign streams into the database.
- An authenticated local viewer browses connected nodes and watches a remote
  stream on their home node. A same-origin server proxy relays discovery,
  metadata, viewer signaling and chat using server-only node credentials.
- A dedicated federation API trusts an active, enabled, registered remote
  node to attest only author FQIDs belonging to that node. It never grants
  broadcaster/create/end privileges. Existing session/JWT APIs remain.
- A new StreamPeer table binds each stream/peer mailbox to one Author. Remote
  mirrors have unusable passwords; federation does not create login accounts.
- Requests target only configured nodes and fixed endpoint paths, with connect/
  read-inactivity timeouts, capped body size and no redirects (not a hard total
  duration deadline). Failure of one node does not block local
  streams. Remote text is escaped/textContent-rendered.
- Screen and microphone media stay in the existing WebRTC connection. Add
  configurable STUN/TURN ICE servers, including optional short-lived TURN REST
  credentials. No blanket CORS, iframe exceptions, or browser node passwords.

## Work and acceptance

- [x] Schema/migration and real database mailbox isolation tests.
- [x] Federation auth, discovery, metadata, signaling, chat, revocation tests.
- [x] Home-node proxy and remote listing/viewer pages; session/JWT and CSRF.
- [x] Configurable ICE; preserve capture/mute/autoplay/cleanup behavior.
- [x] Two isolated nodes with separate databases/HTTP origins: discovery,
      relay, chat, errors, node disable and end lifecycle.
- [x] Existing stream/JavaScript/browser capture/UI regressions.
- [x] Protocol/setup documentation and focused security review.
- [ ] Actual cross-node audio/video delivery in an environment permitting
      WebRTC; cross-network TURN and physical-device acceptance separately.

The cloud's managed WebRTC restriction must remain respected. HTTP federation
and simulated/native capture checks cannot establish delivered media.
