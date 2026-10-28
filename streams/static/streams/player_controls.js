/* Viewer listening preferences are independent of temporary autoplay muting. */
class StreamPlayback {
  constructor(video, ui) {
    this.video = video;
    this.ui = ui;
    this.muted = false;
    this.volume = 1;
    this.lastLevel = 1;
    this.revision = 0;
    for (const event of ['streamchange', 'commentarychange', 'loadedmetadata', 'emptied']) {
      video.addEventListener(event, () => this.update());
    }
    ui.slider.addEventListener('input', () => {
      this.volume = parseFloat(ui.slider.value);
      this.muted = this.volume === 0;
      if (this.volume > 0) this.lastLevel = this.volume;
      this.update();
    });
    ui.muteBtn.addEventListener('click', () => {
      this.muted = !this.muted;
      if (!this.muted && this.volume === 0) this.volume = this.lastLevel;
      this.update();
    });
    ui.enableBtn.addEventListener('click', () => {
      this.muted = false;
      if (this.volume === 0) this.volume = this.lastLevel;
      this.update();
    });
    this.update();
  }

  async update() {
    const revision = ++this.revision;
    const available = this.video.dataset.audioAvailable === '1';
    const source = this.video.srcObject;
    const { group, slider, muteBtn, enableBtn, status } = this.ui;
    group.hidden = !available;
    enableBtn.hidden = true;
    status.hidden = true;
    slider.value = String(this.volume);
    const silent = this.muted || this.volume === 0;
    muteBtn.textContent = silent ? '🔇' : '🔊';
    muteBtn.title = silent ? 'Unmute' : 'Mute';
    muteBtn.setAttribute('aria-label', muteBtn.title);
    this.video.volume = this.volume;
    this.video.muted = !available || silent;
    if (!source) return;
    try {
      await this.video.play();
    } catch (error) {
      if (revision !== this.revision || source !== this.video.srcObject) return;
      // A blocked audible play must not leave the screen video paused.
      this.video.muted = true;
      enableBtn.hidden = !available || silent;
      status.textContent = error.name === 'NotAllowedError'
        ? 'Your browser paused sound. Select Enable sound to listen.'
        : 'Sound could not play. Select Enable sound to try again.';
      status.hidden = !available || silent;
      try {
        await this.video.play();
      } catch (mutedError) {
        if (revision !== this.revision || source !== this.video.srcObject) return;
        status.textContent = 'Playback could not start. Reload the page to reconnect.';
        status.hidden = false;
      }
    }
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const root = document.getElementById('streamPlayer');
  if (!root) return;

  const modeSelect = document.getElementById('displayModeSelect');
  if (modeSelect) {
    const container = document.querySelector('.streams-container');
    modeSelect.addEventListener('change', () => {
      root.dataset.displayMode = modeSelect.value;
      if (container) container.classList.toggle('stream-theater', modeSelect.value === 'theater');
    });
  }

  const video = document.getElementById('remoteVideo');
  const group = document.getElementById('volumeControls');
  if (!video || !group) return;
  new StreamPlayback(video, {
    group,
    slider: document.getElementById('volumeSlider'),
    muteBtn: document.getElementById('muteBtn'),
    enableBtn: document.getElementById('enableSoundBtn'),
    status: document.getElementById('soundStatus'),
  });
});
