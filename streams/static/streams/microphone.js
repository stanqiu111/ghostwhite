/* Optional owner microphone capture. Display capture has a separate lifecycle. */
class MicrophoneController {
  constructor(ui) {
    this.ui = ui;
    this.active = false;
    this.generation = 0;
    this.pending = null;
    this.stream = null;
    this.state = 'off';
    this.peers = new Map();
    this.setState('off');
  }

  begin() {
    this.stop();
    this.active = true;
    this.setState('off');
  }

  async enable() {
    if (!this.active || this.pending || this.stream) return;
    if (!navigator.mediaDevices?.getUserMedia) {
      this.unavailable('Microphone capture is not supported here. Use a supported browser on a secure page; screen sharing can continue.');
      return;
    }
    const generation = this.generation;
    const request = {};
    this.pending = request;
    this.setState('requesting');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      // Permission has settled. A slow sender must not disable Mute while
      // another viewer is already receiving this live track.
      if (this.pending === request) this.pending = null;
      if (!this.active || generation !== this.generation) {
        stream.getTracks().forEach(track => track.stop());
        return;
      }
      const track = stream.getAudioTracks()[0];
      if (!track || track.readyState === 'ended') {
        stream.getTracks().forEach(item => item.stop());
        this.unavailable('No usable microphone was returned. Check your device, then retry. Screen sharing can continue.');
        return;
      }
      this.stream = stream;
      track.enabled = true;
      const lost = () => {
        if (this.stream === stream) {
          this.unavailable('Microphone access was lost. Check the device and permission, then retry. Screen sharing can continue.');
        }
      };
      track.addEventListener('ended', lost);
      track.addEventListener('mute', lost);
      this.setState('on');
      await this.syncPeers();
    } catch (error) {
      if (!this.active || generation !== this.generation) return;
      const messages = {
        NotAllowedError: 'Microphone permission was not granted. Allow it in your browser settings, then retry.',
        SecurityError: 'Microphone access is blocked by your browser. Check its permissions, then retry.',
        NotFoundError: 'No microphone was found. Connect a microphone, then retry.',
        NotReadableError: 'The microphone could not be opened. Check the device or other apps using it, then retry.',
        AbortError: 'Microphone access was interrupted. Check your device, then retry.',
      };
      this.unavailable(`${messages[error.name] || 'Microphone access could not be obtained. Check the device and permission, then retry.'} Screen sharing can continue.`);
    } finally {
      // Keep a single outstanding browser request, even across stop/restart.
      if (this.pending === request) this.pending = null;
      this.render();
    }
  }

  toggleMute() {
    const track = this.stream?.getAudioTracks()[0];
    if (!this.active || !track || track.readyState === 'ended') return;
    track.enabled = !track.enabled;
    this.setState(track.enabled ? 'on' : 'muted');
  }

  async addPeer(pc, displayStream) {
    // Negotiate the audio lane once, without requesting or capturing a microphone.
    const sender = pc.addTransceiver('audio', { direction: 'sendonly', streams: [displayStream] }).sender;
    const channel = pc.createDataChannel('commentary');
    const peer = { pc, sender, channel, update: Promise.resolve() };
    this.peers.set(pc, peer);
    channel.onopen = () => this.syncPeer(peer);
    await this.syncPeer(peer);
  }

  removePeer(pc) {
    const peer = this.peers.get(pc);
    if (!peer) return;
    this.peers.delete(pc);
    peer.channel.onopen = null;
    peer.channel.close();
  }

  syncPeers() {
    return Promise.all([...this.peers.values()].map(peer => this.syncPeer(peer)));
  }

  syncPeer(peer) {
    // Serialize replacements so an older grant cannot win a race against cleanup.
    peer.update = peer.update.then(async () => {
      if (this.peers.get(peer.pc) !== peer) return;
      const stream = this.stream;
      try {
        await peer.sender.replaceTrack(stream?.getAudioTracks()[0] || null);
        if (this.peers.get(peer.pc) !== peer || stream !== this.stream) return;
        if (peer.channel.readyState === 'open') {
          peer.channel.send(JSON.stringify({ type: 'microphone', available: !!stream }));
        }
      } catch (error) {
        if (stream && stream === this.stream && this.peers.get(peer.pc) === peer
            && !['closed', 'failed', 'disconnected'].includes(peer.pc.connectionState)) {
          this.unavailable('Commentary could not be connected. Retry the microphone; screen sharing can continue.');
        }
      }
    });
    return peer.update;
  }

  release() {
    const stream = this.stream;
    this.stream = null;
    if (stream) stream.getTracks().forEach(track => track.stop());
  }

  unavailable(message) {
    this.release();
    this.setState('unavailable', message);
    this.syncPeers();
  }

  stop() {
    ++this.generation;
    this.active = false;
    this.release();
    this.setState('off');
    this.syncPeers();
  }

  setState(state, message = '') {
    this.state = state;
    this.ui.error.textContent = message;
    this.ui.error.hidden = !message;
    this.render();
  }

  render() {
    const labels = {
      off: ['Microphone off', 'Enable microphone'],
      requesting: ['Requesting microphone', 'Requesting microphone…'],
      on: ['Microphone on', 'Mute microphone'],
      muted: ['Muted', 'Unmute microphone'],
      unavailable: ['Microphone unavailable', 'Retry microphone'],
    };
    const [status, action] = labels[this.state];
    this.ui.status.textContent = status;
    this.ui.button.textContent = action;
    this.ui.button.disabled = !this.active || !!this.pending;
  }
}
