/* Viewer player controls for stream_detail.html: volume/mute and display mode.
 *
 * Isolated from screenshare.js — it only reads the #remoteVideo element that
 * screenshare.js feeds. Volume controls stay hidden unless the received
 * stream actually carries an audio track (no fake controls on today's
 * video-only broadcasts).
 */

document.addEventListener('DOMContentLoaded', () => {
  const root = document.getElementById('streamPlayer');
  if (!root) return;

  /* ---- Display mode: Auto / Fit / Fill / Theater (CSS-only geometry) ---- */
  const modeSelect = document.getElementById('displayModeSelect');
  if (modeSelect) {
    const container = document.querySelector('.streams-container');
    modeSelect.addEventListener('change', () => {
      root.dataset.displayMode = modeSelect.value;
      if (container) container.classList.toggle('stream-theater', modeSelect.value === 'theater');
    });
  }

  /* ---- Volume / mute: shown only when an audio track exists ---- */
  const video = document.getElementById('remoteVideo');
  const group = document.getElementById('volumeControls');
  if (!video || !group) return;
  const slider = document.getElementById('volumeSlider');
  const muteBtn = document.getElementById('muteBtn');
  let lastLevel = 1;

  const syncMuteIcon = () => {
    const silent = video.muted || video.volume === 0;
    muteBtn.textContent = silent ? '🔇' : '🔊';
    muteBtn.title = silent ? 'Unmute' : 'Mute';
  };

  const checkAudio = () => {
    const tracks = video.srcObject ? video.srcObject.getAudioTracks() : [];
    group.hidden = tracks.length === 0;
  };
  // srcObject is (re)attached by screenshare.js; metadata fires on each new stream
  video.addEventListener('loadedmetadata', checkAudio);
  video.addEventListener('emptied', checkAudio);
  checkAudio();

  slider.addEventListener('input', () => {
    video.volume = parseFloat(slider.value);
    video.muted = video.volume === 0;
    if (video.volume > 0) lastLevel = video.volume;
    syncMuteIcon();
  });

  muteBtn.addEventListener('click', () => {
    if (video.muted || video.volume === 0) {
      video.muted = false;
      video.volume = lastLevel;
      slider.value = String(lastLevel);
    } else {
      lastLevel = video.volume;
      video.muted = true;
    }
    syncMuteIcon();
  });
});
