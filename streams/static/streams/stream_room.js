/* Presentation of existing media state; no capture or signaling changes. */
document.addEventListener('DOMContentLoaded', () => {
  const player = document.getElementById('streamPlayer');
  const status = document.getElementById('roomStatus');
  if (!player || !status) return;
  const placeholder = player.querySelector('.stream-player-placeholder');
  const onAir = document.getElementById('onAirBadge');
  const hint = document.getElementById('stageHint');
  const owner = player.dataset.isOwner === '1';
  const labels = { idle: 'Off air', waiting: 'Waiting for host', connecting: 'Connecting',
    live: 'Live', ended: 'Ended', error: 'Connection issue' };
  const hints = {
    idle: 'Share a screen or window to start. Your microphone stays off until you enable it.',
    waiting: 'The video will appear here when the host starts sharing.',
    connecting: 'Joining the broadcast. Your video will appear in a moment.',
    error: 'The connection was interrupted. Try connecting again.',
    ended: "Thanks for being here. Explore another stream when you're ready.",
  };
  function update() {
    const state = player.dataset.streamStatus === 'ended' ? 'ended'
      : owner ? (onAir && !onAir.hidden ? 'live' : 'idle')
        : placeholder.dataset.playerState;
    status.dataset.state = state;
    status.textContent = labels[state] || 'Waiting for host';
    if (hint) hint.textContent = hints[state] || '';
  }
  const observer = new MutationObserver(update);
  observer.observe(placeholder, { attributes: true, attributeFilter: ['data-player-state'] });
  observer.observe(player, { attributes: true, attributeFilter: ['data-stream-status'] });
  if (onAir) observer.observe(onAir, { attributes: true, attributeFilter: ['hidden'] });
  update();
});
