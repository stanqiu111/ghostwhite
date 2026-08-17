/* Signaling transport for screen-share WebRTC handshakes.
 *
 * REST + short polling against /api/streams/<serial>/signals/.
 * EXTENSION POINT: to move to WebSockets later, replace postSignal/pollSignals
 * with a socket-backed implementation — screenshare.js only uses these two
 * functions and StreamEndedError.
 */

class StreamEndedError extends Error {
  constructor() {
    super('Stream has ended');
    this.name = 'StreamEndedError';
  }
}

function signalingHeaders() {
  const headers = { 'Content-Type': 'application/json' };
  const m = document.cookie.match('(^|;)\\s*csrftoken\\s*=\\s*([^;]+)');
  if (m) headers['X-CSRFToken'] = m.pop();
  const token = localStorage.getItem('access_token');
  if (token) headers['Authorization'] = `Bearer ${token}`;
  return headers;
}

/* Send one signal. kind: join|offer|answer|candidate|bye.
   direction: to_streamer|to_viewer. Throws StreamEndedError on 410. */
async function postSignal(serial, { kind, direction, peerId, payload = {} }, { keepalive = false } = {}) {
  const res = await fetch(`/api/streams/${serial}/signals/`, {
    method: 'POST',
    credentials: 'same-origin',
    keepalive,
    headers: signalingHeaders(),
    body: JSON.stringify({ kind, direction, peer_id: peerId, payload }),
  });
  if (res.status === 410) throw new StreamEndedError();
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(data?.detail || `${res.status} ${res.statusText}`);
  }
  return res.json();
}

/* Poll (and consume) signals addressed to this role. Returns an array of
   {kind, peer_id, payload, sender_serial}. Throws StreamEndedError on 410. */
async function pollSignals(serial, role, peerId = null) {
  const params = new URLSearchParams({ role });
  if (peerId) params.set('peer_id', peerId);
  const res = await fetch(`/api/streams/${serial}/signals/?${params}`, {
    credentials: 'same-origin',
    headers: signalingHeaders(),
  });
  if (res.status === 410) throw new StreamEndedError();
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(data?.detail || `${res.status} ${res.statusText}`);
  }
  return (await res.json()).items;
}
