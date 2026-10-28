# Research: Microphone Commentary

## Audio transport
**Decision:** Reserve one send-only audio transceiver before each initial offer; replace its track after explicit microphone permission. Use a reliable `commentary` data channel carrying an availability boolean, with a snapshot on open and updates after attachment/detachment.
**Rationale:** Current Player.handleOffer closes its connection; addTrack + renegotiation would interrupt video and require offer/answer race handling. The reserved lane sends no captured microphone audio before opt-in.
**Alternatives:** Dynamic renegotiation adds unnecessary negotiation state; polling microphone state through Django adds persistence/API work for ephemeral media. Track-count detection is wrong because the reserved receiver exists before capture.

## Lifecycle and permission races
**Decision:** Keep display and microphone capture separate. Use a generation per broadcast and a single pending microphone request; stop invalidates requests even when capture is pending. Release obsolete granted streams immediately. Serialize sender replacements per peer so loss/retry cannot install an older track after a newer one.
**Rationale:** Permission completion is asynchronous and cannot be canceled reliably. Muting a shared track immediately affects current and late viewers.
**Alternatives:** Re-request on every mute creates prompts and delays; coupling display and microphone failures would break the optional feature.

## Viewer playback
**Decision:** A single playback controller retains the viewer's requested mute/volume separately from a temporary browser-policy mute. Begin video silently without commentary; attempt sound when available, fall back to muted video and offer Enable sound on rejection.
**Rationale:** Autoplay restrictions and a reserved audio lane can block the old autoplay-only player. Microphone changes must not reset viewer preferences.
**Alternatives:** Relying solely on loadedmetadata misses later availability; forcing unmute on every state change overrides viewer choice.

## Validation capability
Research agents inspected the existing app and successfully probed native getDisplayMedia/getUserMedia in /usr/bin/chromium 154 through Playwright 1.61. Headless synthetic capture needs no install or Xvfb. Test transport with native peer connections, a generated audio tone and incoming RTP energy/video-frame statistics; distinguish this from physical microphone and permission-dialog validation. Fault injection covers deterministic denial, late grants and device loss separately.
