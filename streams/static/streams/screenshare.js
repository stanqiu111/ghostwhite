/* Screen-share WebRTC logic for stream_detail.html.
 *
 * Broadcaster: owner side — getDisplayMedia capture + one RTCPeerConnection
 * per viewer (P2P mesh, microphone off until the owner opts in).
 * Player: viewer side — join heartbeat, answer/ICE, and the UI state machine
 * waiting | connecting | live | ended | error.
 *
 * Transport comes from signaling.js (postSignal / pollSignals).
 */

const ICE_CONFIG = { iceServers: [{ urls: 'stun:stun.l.google.com:19302' }] };

/* ---------------- Broadcaster (owner) ---------------- */

class Broadcaster {
  constructor(serial, ui) {
    this.serial = serial;
    this.ui = ui;           // {preview, shareBtn, stopBtn, onAirBadge, errorNote, placeholder}
    this.media = null;
    this.pcs = new Map();   // peerId -> RTCPeerConnection
    // Candidates that raced ahead of the peer's answer (consume-on-read means
    // a dropped candidate is lost forever, so they must be buffered, not skipped)
    this.pendingCandidates = new Map();  // peerId -> [candidate payload]
    this.pollTimer = null;
    this.active = false;
    this.generation = 0;
    this.starting = false;
    this.polling = false;
    this.microphone = new MicrophoneController(ui.microphone);
  }

  async start() {
    if (this.active || this.starting) return;
    const generation = ++this.generation;
    this.starting = true;
    this.ui.shareBtn.disabled = true;
    try {
      const media = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false });
      if (generation !== this.generation) {
        media.getTracks().forEach(track => track.stop());
        return;
      }
      this.media = media;
    } catch (err) {
      // Permission denied / cancelled: clear hint, no broadcast (FR-002)
      if (generation === this.generation) {
        this.showError('Screen sharing was cancelled or blocked. Click "Share screen" to try again.');
      }
      return;
    } finally {
      this.starting = false;
      this.ui.shareBtn.disabled = false;
    }
    this.active = true;
    this.microphone.begin();
    this.hideError();
    // Browser-native "Stop sharing" bar funnels into the same stop()
    this.media.getVideoTracks()[0].addEventListener('ended', () => this.stop());

    this.ui.preview.srcObject = this.media;
    this.ui.preview.hidden = false;
    this.ui.placeholder.hidden = true;
    this.ui.shareBtn.hidden = true;
    this.ui.stopBtn.hidden = false;
    this.ui.onAirBadge.hidden = false;

    this.pollTimer = setInterval(() => this.poll(), 1500);
    this.poll();
  }

  async poll() {
    if (!this.active || this.polling) return;
    const generation = this.generation;
    this.polling = true;
    let items;
    try {
      items = await pollSignals(this.serial, 'streamer');
    } catch (err) {
      if (generation === this.generation && err instanceof StreamEndedError) this.stop(false);
      return; // transient errors: just try again next tick
    } finally {
      this.polling = false;
    }
    for (const s of items) {
      if (!this.active || generation !== this.generation) return;
      try {
        if (s.kind === 'join') await this.handleJoin(s.peer_id);
        else if (s.kind === 'answer') await this.handleAnswer(s.peer_id, s.payload);
        else if (s.kind === 'candidate') await this.handleCandidate(s.peer_id, s.payload);
        else if (s.kind === 'bye') this.closePeer(s.peer_id);
      } catch (err) {
        console.warn('broadcaster: signal handling failed', s.kind, err);
      }
    }
  }

  async handleJoin(peerId) {
    if (!this.active || this.pcs.has(peerId)) return;
    const pc = new RTCPeerConnection(ICE_CONFIG);
    this.pcs.set(peerId, pc);
    this.media.getVideoTracks().forEach((t) => pc.addTrack(t, this.media));
    await this.microphone.addPeer(pc, this.media);
    if (this.pcs.get(peerId) !== pc) return;
    pc.onicecandidate = (e) => {
      if (e.candidate) {
        postSignal(this.serial, {
          kind: 'candidate', direction: 'to_viewer', peerId, payload: e.candidate.toJSON(),
        }).catch(() => {});
      }
    };
    pc.onconnectionstatechange = () => {
      if (['failed', 'closed', 'disconnected'].includes(pc.connectionState)) {
        if (this.pcs.get(peerId) === pc) this.closePeer(peerId, false);
      }
    };
    const offer = await pc.createOffer();
    if (this.pcs.get(peerId) !== pc) return;
    await pc.setLocalDescription(offer);
    if (this.pcs.get(peerId) !== pc) return;
    await postSignal(this.serial, {
      kind: 'offer', direction: 'to_viewer', peerId,
      payload: { type: pc.localDescription.type, sdp: pc.localDescription.sdp },
    });
  }

  async handleAnswer(peerId, payload) {
    const pc = this.pcs.get(peerId);
    if (!pc) return;
    await pc.setRemoteDescription(new RTCSessionDescription(payload));
    // Flush candidates that arrived before the answer
    const queued = this.pendingCandidates.get(peerId) || [];
    this.pendingCandidates.delete(peerId);
    for (const c of queued) {
      await pc.addIceCandidate(new RTCIceCandidate(c)).catch(() => {});
    }
  }

  async handleCandidate(peerId, payload) {
    const pc = this.pcs.get(peerId);
    if (pc && pc.remoteDescription) {
      await pc.addIceCandidate(new RTCIceCandidate(payload));
    } else {
      // No answer yet — addIceCandidate would throw and the candidate would be lost
      const queued = this.pendingCandidates.get(peerId) || [];
      queued.push(payload);
      this.pendingCandidates.set(peerId, queued);
    }
  }

  closePeer(peerId, sendBye = true) {
    this.pendingCandidates.delete(peerId);
    const pc = this.pcs.get(peerId);
    if (!pc) return;
    this.pcs.delete(peerId);
    this.microphone.removePeer(pc);
    try { pc.close(); } catch (e) { /* already closed */ }
    if (sendBye) {
      postSignal(this.serial, { kind: 'bye', direction: 'to_viewer', peerId },
        { keepalive: true }).catch(() => {});
    }
  }

  stop(sendByes = true) {
    ++this.generation;
    this.active = false;
    this.microphone.stop();
    clearInterval(this.pollTimer);
    for (const peerId of [...this.pcs.keys()]) this.closePeer(peerId, sendByes);
    if (this.media) {
      this.media.getTracks().forEach((t) => t.stop());
      this.media = null;
    }
    this.ui.preview.srcObject = null;
    this.ui.preview.hidden = true;
    this.ui.placeholder.hidden = false;
    this.ui.shareBtn.hidden = false;
    this.ui.stopBtn.hidden = true;
    this.ui.onAirBadge.hidden = true;
  }

  showError(msg) {
    this.ui.errorNote.textContent = msg;
    this.ui.errorNote.hidden = false;
  }

  hideError() {
    this.ui.errorNote.hidden = true;
  }
}

/* ---------------- Player (viewer) ---------------- */

class Player {
  constructor(serial, ui) {
    this.serial = serial;
    this.ui = ui;           // {video, placeholder, stateText, retryBtn}
    this.peerId = null;
    this.pc = null;
    // Candidates that arrived before the offer (poll order can put them first;
    // consume-on-read means dropping one loses it forever)
    this.pendingCandidates = [];
    this.state = 'waiting';
    this.joinTimer = null;
    this.pollTimer = null;
    this.stopped = false;
  }

  start() {
    this.peerId = crypto.randomUUID();
    this.setState('waiting');
    this.sendJoin();
    this.joinTimer = setInterval(() => {
      if (this.state === 'waiting') this.sendJoin();     // heartbeat while waiting
    }, 10000);
    this.schedulePoll();
  }

  schedulePoll() {
    if (this.stopped) return;
    const delay = this.state === 'live' ? 3000 : 1000;
    this.pollTimer = setTimeout(async () => {
      await this.poll();
      this.schedulePoll();
    }, delay);
  }

  sendJoin() {
    postSignal(this.serial, { kind: 'join', direction: 'to_streamer', peerId: this.peerId })
      .catch((err) => { if (err instanceof StreamEndedError) this.onEnded(); });
  }

  async poll() {
    if (this.stopped) return;
    let items;
    try {
      items = await pollSignals(this.serial, 'viewer', this.peerId);
    } catch (err) {
      if (err instanceof StreamEndedError) this.onEnded();
      return;
    }
    for (const s of items) {
      try {
        if (s.kind === 'offer') await this.handleOffer(s.payload);
        else if (s.kind === 'candidate') await this.handleCandidate(s.payload);
        else if (s.kind === 'bye') this.resetToWaiting();
      } catch (err) {
        console.warn('player: signal handling failed', s.kind, err);
        this.setState('error');
      }
    }
  }

  async handleOffer(payload) {
    this.setState('connecting');
    this.closePC();
    const pc = new RTCPeerConnection(ICE_CONFIG);
    this.pc = pc;
    pc.ontrack = (e) => {
      if (this.pc !== pc || this.stopped) return;
      this.ui.video.srcObject = e.streams[0];
      this.ui.video.dispatchEvent(new Event('streamchange'));
    };
    pc.ondatachannel = (e) => {
      if (e.channel.label !== 'commentary') return;
      e.channel.onmessage = (message) => {
        if (this.pc !== pc || this.stopped) return;
        let data;
        try { data = JSON.parse(message.data); } catch { return; }
        if (data?.type === 'microphone' && typeof data.available === 'boolean') {
          this.setAudioAvailable(data.available);
        }
      };
    };
    pc.onconnectionstatechange = () => {
      if (this.pc !== pc) return;
      if (pc.connectionState === 'connected') this.setState('live');
      else if (['disconnected', 'failed', 'closed'].includes(pc.connectionState)) {
        if (!this.stopped && this.state !== 'ended') this.resetToWaiting();
      }
    };
    pc.onicecandidate = (e) => {
      if (e.candidate) {
        postSignal(this.serial, {
          kind: 'candidate', direction: 'to_streamer', peerId: this.peerId,
          payload: e.candidate.toJSON(),
        }).catch(() => {});
      }
    };
    await pc.setRemoteDescription(new RTCSessionDescription(payload));
    // Flush candidates that raced ahead of the offer
    const queued = this.pendingCandidates.splice(0);
    for (const c of queued) {
      await pc.addIceCandidate(new RTCIceCandidate(c)).catch(() => {});
    }
    const answer = await pc.createAnswer();
    await pc.setLocalDescription(answer);
    await postSignal(this.serial, {
      kind: 'answer', direction: 'to_streamer', peerId: this.peerId,
      payload: { type: pc.localDescription.type, sdp: pc.localDescription.sdp },
    });
  }

  async handleCandidate(payload) {
    if (this.pc && this.pc.remoteDescription) {
      await this.pc.addIceCandidate(new RTCIceCandidate(payload));
    } else {
      // No offer processed yet — buffer instead of dropping
      this.pendingCandidates.push(payload);
    }
  }

  closePC() {
    if (this.pc) {
      const pc = this.pc;
      this.pc = null;
      try { pc.close(); } catch (e) { /* already closed */ }
    }
    this.ui.video.srcObject = null;
    this.setAudioAvailable(false);
    this.ui.video.dispatchEvent(new Event('streamchange'));
  }

  setAudioAvailable(available) {
    this.ui.video.dataset.audioAvailable = available ? '1' : '0';
    this.ui.video.dispatchEvent(new Event('commentarychange'));
  }

  resetToWaiting() {
    this.closePC();
    this.pendingCandidates = [];
    // Fresh peer_id: the broadcaster ignores joins for peer_ids still in its
    // map, so re-joining under the old id can be silently dropped until the
    // broadcaster notices its stale connection failed
    this.peerId = crypto.randomUUID();
    this.setState('waiting');
    this.sendJoin();
  }

  retry() {
    this.resetToWaiting();
  }

  async onEnded() {
    // Confirm via the stream API, then shut everything down
    try {
      const res = await fetch(`/api/streams/${this.serial}/`, {
        credentials: 'same-origin', headers: signalingHeaders(),
      });
      const data = await res.json().catch(() => null);
      if (data && data.status && data.status !== 'ended') return; // transient
    } catch (e) { /* treat as ended */ }
    this.stopped = true;
    clearInterval(this.joinTimer);
    clearTimeout(this.pollTimer);
    this.closePC();
    this.setState('ended');
  }

  setState(state) {
    this.state = state;
    const { video, placeholder, stateText, retryBtn, fullscreenBtn } = this.ui;
    placeholder.dataset.playerState = state;
    video.hidden = state !== 'live';
    placeholder.hidden = state === 'live';
    retryBtn.hidden = state !== 'error';
    if (fullscreenBtn) fullscreenBtn.hidden = state !== 'live';
    const copy = {
      waiting: 'Waiting for streamer…',
      connecting: 'Connecting…',
      ended: 'This stream has ended',
      error: 'Connection failed.',
    };
    if (copy[state]) stateText.textContent = copy[state];
  }
}

/* ---------------- Page wiring ---------------- */

document.addEventListener('DOMContentLoaded', () => {
  const root = document.getElementById('streamPlayer');
  if (!root) return;
  const serial = root.dataset.streamSerial;
  const isOwner = root.dataset.isOwner === '1';
  const isLive = root.dataset.streamStatus === 'live';

  if (isOwner && isLive) {
    const broadcaster = new Broadcaster(serial, {
      preview: document.getElementById('localPreview'),
      shareBtn: document.getElementById('shareScreenBtn'),
      stopBtn: document.getElementById('stopSharingBtn'),
      onAirBadge: document.getElementById('onAirBadge'),
      errorNote: document.getElementById('shareError'),
      placeholder: document.querySelector('.stream-player-placeholder'),
      microphone: {
        button: document.getElementById('microphoneBtn'),
        status: document.getElementById('microphoneStatus'),
        error: document.getElementById('microphoneError'),
      },
    });
    window.streamBroadcaster = broadcaster; // end-stream handler stops it first
    document.getElementById('shareScreenBtn').addEventListener('click', () => broadcaster.start());
    document.getElementById('stopSharingBtn').addEventListener('click', () => broadcaster.stop());
    document.getElementById('microphoneBtn').addEventListener('click', () => {
      if (['on', 'muted'].includes(broadcaster.microphone.state)) broadcaster.microphone.toggleMute();
      else broadcaster.microphone.enable();
    });
    window.addEventListener('beforeunload', () => broadcaster.stop(true)); // best-effort byes
    window.addEventListener('pagehide', () => broadcaster.stop(true));
  } else if (!isOwner && isLive) {
    const player = new Player(serial, {
      video: document.getElementById('remoteVideo'),
      placeholder: document.querySelector('.stream-player-placeholder'),
      stateText: document.getElementById('playerStateText'),
      retryBtn: document.getElementById('retryBtn'),
      fullscreenBtn: document.getElementById('fullscreenBtn'),
    });
    document.getElementById('retryBtn').addEventListener('click', () => player.retry());

    // Full-screen the whole player container (video keeps its aspect ratio)
    const fsBtn = document.getElementById('fullscreenBtn');
    const toggleFullscreen = () => {
      if (document.fullscreenElement || document.webkitFullscreenElement) {
        (document.exitFullscreen || document.webkitExitFullscreen).call(document);
      } else {
        (root.requestFullscreen || root.webkitRequestFullscreen).call(root);
      }
    };
    fsBtn.addEventListener('click', toggleFullscreen);
    document.getElementById('remoteVideo').addEventListener('dblclick', toggleFullscreen);
    document.addEventListener('fullscreenchange', () => {
      const active = !!document.fullscreenElement;
      fsBtn.textContent = active ? '⤡' : '⛶';
      fsBtn.title = active ? 'Exit full screen' : 'Full screen';
    });

    player.start();
  }
});
