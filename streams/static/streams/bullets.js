/* Bullet curtain (danmaku) for stream_detail.html.
 *
 * Fully isolated from screenshare.js — shares only the DOM and the
 * CSRF + optional-JWT header pattern (copied from signaling.js, not imported).
 * Transport: REST cursor polling of /api/streams/<serial>/bullets/
 * (non-consuming; each watcher keeps its own id cursor).
 *
 * XSS: message text is rendered exclusively via textContent / createTextNode.
 * No HTML-string injection APIs are allowed anywhere in this file.
 */

const BULLET_POLL_MS = 1500;
const BULLET_SEND_THROTTLE_MS = 1000;
const BULLET_LANE_BUSY_MS = 2500;

function bulletHeaders() {
  const headers = { 'Content-Type': 'application/json' };
  const m = document.cookie.match('(^|;)\\s*csrftoken\\s*=\\s*([^;]+)');
  if (m) headers['X-CSRFToken'] = m.pop();
  const token = localStorage.getItem('access_token');
  if (token) headers['Authorization'] = `Bearer ${token}`;
  return headers;
}

class BulletCurtain {
  constructor(serial, ui) {
    this.serial = serial;
    this.ui = ui;          // {overlay, form, input, sendBtn, error, toggle}
    this.cursor = 0;
    this.enabled = true;
    this.stopped = false;
    this.pollTimer = null;
    this.lastSentAt = 0;
    // 6 lanes on desktop, 3 on narrow viewports (locked decision)
    this.laneCount = window.matchMedia('(max-width: 640px)').matches ? 3 : 6;
    this.laneBusyUntil = new Array(this.laneCount).fill(0);
  }

  async start() {
    try {
      const data = await this.fetch({ latest: 1 });
      this.cursor = data.cursor;
      data.items.forEach((item) => this.display(item)); // ≤30 backfill, lanes shed overflow
    } catch (err) {
      if (err instanceof BulletStreamEnded) { this.onEnded(); return; }
      // transient bootstrap failure: poll from 0 and catch up
    }
    this.pollTimer = setInterval(() => this.poll(), BULLET_POLL_MS);
  }

  async fetch(params) {
    const qs = new URLSearchParams(params);
    const res = await window.fetch(`/api/streams/${this.serial}/bullets/?${qs}`, {
      credentials: 'same-origin',
      headers: bulletHeaders(),
    });
    if (res.status === 410) throw new BulletStreamEnded();
    if (!res.ok) throw new Error(`${res.status}`);
    return res.json();
  }

  async poll() {
    if (this.stopped) return;
    let data;
    try {
      data = await this.fetch({ after: this.cursor });
    } catch (err) {
      if (err instanceof BulletStreamEnded) this.onEnded();
      return; // transient errors: try again next tick
    }
    this.cursor = data.cursor;
    if (this.enabled) data.items.forEach((item) => this.display(item));
    // curtain off: items are discarded but the cursor advanced — no replay on re-enable
  }

  display(item) {
    const now = Date.now();
    let lane = 0;
    for (let i = 1; i < this.laneCount; i++) {
      if (this.laneBusyUntil[i] < this.laneBusyUntil[lane]) lane = i;
    }
    if (this.laneBusyUntil[lane] > now) return; // all lanes busy: shed from display only
    this.laneBusyUntil[lane] = now + BULLET_LANE_BUSY_MS;

    const msg = document.createElement('span');
    msg.className = 'bullet-msg';
    const sender = document.createElement('span');
    sender.className = 'bullet-sender';
    sender.textContent = item.sender.displayName;
    const text = document.createTextNode(item.content);
    msg.appendChild(sender);
    msg.appendChild(text);

    const duration = 9 + Math.min(item.content.length, 120) / 40; // 9–12 s by length
    msg.style.setProperty('--lane', lane);
    msg.style.setProperty('--lanes', this.laneCount);
    msg.style.setProperty('--dur', `${duration}s`);
    msg.addEventListener('animationend', () => msg.remove());
    this.ui.overlay.appendChild(msg);
  }

  setEnabled(on) {
    this.enabled = on;
    if (!on) {
      this.ui.overlay.replaceChildren(); // clear in-flight bullets immediately
      this.laneBusyUntil.fill(0);
    }
  }

  async send() {
    const content = this.ui.input.value.trim();
    if (!content || this.stopped) return;
    const now = Date.now();
    if (now - this.lastSentAt < BULLET_SEND_THROTTLE_MS) {
      this.showError('Sending too fast — try again in a moment.');
      return;
    }
    this.lastSentAt = now;
    let res;
    try {
      res = await window.fetch(`/api/streams/${this.serial}/bullets/`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: bulletHeaders(),
        body: JSON.stringify({ content }),
      });
    } catch (err) {
      this.showError('Could not send — check your connection.');
      return;
    }
    if (res.status === 410) { this.onEnded(); return; }
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      const detail = data && (data.detail || (data.content && data.content[0]));
      this.showError(detail || 'Could not send message.');
      return;
    }
    this.ui.input.value = '';
    this.hideError();
  }

  onEnded() {
    // Bullets-only shutdown: the player's own ended handling owns the big UI change
    this.stopped = true;
    clearInterval(this.pollTimer);
    this.ui.input.disabled = true;
    this.ui.sendBtn.disabled = true;
    this.ui.input.placeholder = 'Stream has ended';
    this.hideError();
  }

  showError(msg) {
    this.ui.error.textContent = msg;
    this.ui.error.hidden = false;
  }

  hideError() {
    this.ui.error.hidden = true;
  }
}

class BulletStreamEnded extends Error {}

document.addEventListener('DOMContentLoaded', () => {
  const root = document.getElementById('streamPlayer');
  const form = document.getElementById('bulletForm');
  if (!root || !form || root.dataset.streamStatus !== 'live') return;

  const curtain = new BulletCurtain(root.dataset.streamSerial, {
    overlay: document.getElementById('bulletOverlay'),
    form,
    input: document.getElementById('bulletInput'),
    sendBtn: document.getElementById('bulletSendBtn'),
    error: document.getElementById('bulletError'),
  });
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    curtain.send();
  });
  const toggle = document.getElementById('bulletToggle');
  if (toggle) toggle.addEventListener('change', () => curtain.setEnabled(toggle.checked));
  curtain.start();
});
