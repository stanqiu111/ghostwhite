# Microphone UI and Media Contract

## Owner
Only a live stream's owner receives microphone controls. Enable microphone is disabled before screen sharing and while a permission request is unresolved. States are Off, Requesting microphone, Microphone on, Muted and Microphone unavailable. The button becomes Mute microphone, Unmute microphone or Retry microphone as appropriate. Status/error text is accessible and does not rely on color. Mute retains capture; stopping releases it.

## Existing signaling
POST/GET /api/streams/<serial>/signals/ and its join/offer/answer/candidate/bye payloads remain unchanged. Initial SDP includes video, a reserved send-only audio transceiver, and a reliable data channel. Existing owner authorization determines the broadcaster endpoint.

## Direct metadata
Channel label: `commentary`. Owner sends JSON `{"type":"microphone","available":true|false}`. True means a microphone is attached, including while muted. A snapshot is sent when the channel opens; sender changes send the current state after replacement. Viewers ignore unknown/malformed messages. Viewers cannot change owner capture through this channel.

## Local playback integration
Player marks remote video's data-audio-available as 1 or 0 and dispatches commentarychange; it dispatches streamchange when attaching/resetting the remote stream. Controls observe these events and loadedmetadata. The same remote video element retains local volume/mute preference through reconnects. Enable sound is a viewer gesture, never a microphone permission request.

## Stop and race semantics
Stop invalidates permission requests before releasing tracks and peers. Late permission grants are stopped, even after a newer broadcast starts. Per-peer sender updates are ordered; obsolete peers cannot publish state or affect a new session. Screen video continues during microphone errors.
