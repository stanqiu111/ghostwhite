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
    this.lastMessageId = 0;
    // 6 lanes on desktop, 3 on narrow viewports (locked decision)
    this.laneCount = window.matchMedia('(max-width: 640px)').matches ? 3 : 6;
    this.laneBusyUntil = new Array(this.laneCount).fill(0);
    if (ui.chat && ui.latest) {
      ui.latest.addEventListener('click', () => {
        ui.chat.scrollTop = ui.chat.scrollHeight;
        ui.latest.hidden = true;
      });
      ui.chat.addEventListener('scroll', () => {
        if (ui.chat.scrollHeight - ui.chat.clientHeight - ui.chat.scrollTop < 36) ui.latest.hidden = true;
      });
    }
  }

  async start() {
    this.ui.chat?.setAttribute('aria-busy', 'true');
    try {
      const data = await this.fetch({ latest: 1 });
      if (this.stopped) return;
      this.cursor = data.cursor;
      data.items.forEach((item) => this.receive(item)); // ≤30 real recent messages
      this.chatStatus('');
    } catch (err) {
      if (this.stopped) return;
      if (err instanceof BulletStreamEnded) { this.onEnded(); return; }
      this.chatStatus('Chat is reconnecting…');
    } finally {
      this.ui.chat?.setAttribute('aria-busy', 'false');
    }
    if (!this.stopped) this.pollTimer = setInterval(() => this.poll(), BULLET_POLL_MS);
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
      if (this.stopped) return;
    } catch (err) {
      if (this.stopped) return;
      if (err instanceof BulletStreamEnded) this.onEnded();
      else this.chatStatus('Chat is reconnecting…');
      return; // transient errors: try again next tick
    }
    this.cursor = Math.max(this.cursor, data.cursor);
    data.items.forEach((item) => this.receive(item));
    this.chatStatus('');
    // Curtain off affects the overlay only. Chat keeps receiving; overlay
    // messages are never replayed when the curtain is switched back on.
  }

  receive(item) {
    // Overlapping polls may return the same batch. Keep history and overlay
    // ordered without retaining an unbounded set of message IDs.
    if (item.id <= this.lastMessageId) return;
    this.lastMessageId = item.id;
    this.appendChat(item);
    if (this.enabled) this.display(item);
  }

  appendChat(item) {
    const { chat, empty, latest } = this.ui;
    if (!chat) return;
    const atBottom = chat.scrollHeight - chat.clientHeight - chat.scrollTop < 36;
    const message = document.createElement('article');
    message.className = 'stream-chat-message';
    const heading = document.createElement('div');
    heading.className = 'stream-chat-message-head';
    const sender = document.createElement('strong');
    sender.textContent = item.sender.displayName;
    heading.appendChild(sender);
    const created = new Date(item.created_at);
    if (!Number.isNaN(created.getTime())) {
      const time = document.createElement('time');
      time.dateTime = created.toISOString();
      time.textContent = created.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
      heading.appendChild(time);
    }
    const content = document.createElement('p');
    content.textContent = item.content;
    message.appendChild(heading);
    message.appendChild(content);
    chat.appendChild(message);
    while (chat.children.length > 100) chat.firstElementChild.remove();
    if (empty) empty.hidden = true;
    if (atBottom) chat.scrollTop = chat.scrollHeight;
    else if (latest) latest.hidden = false;
  }

  chatStatus(text) {
    if (this.ui.status) this.ui.status.textContent = text;
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
    this.chatStatus('Chat closed — this stream has ended.');
    if (this.ui.title) this.ui.title.textContent = 'Chat closed';
    if (this.ui.empty && !this.ui.empty.hidden) {
      this.ui.empty.querySelector('strong').textContent = "That's a wrap";
      this.ui.empty.querySelector('p').textContent = 'This stream has ended. Chat is no longer available.';
    }
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
    chat: document.getElementById('chatMessages'),
    empty: document.getElementById('chatEmpty'),
    latest: document.getElementById('chatLatestBtn'),
    status: document.getElementById('chatStatus'),
    title: document.getElementById('chatTitle'),
  });
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    curtain.send();
  });
  const toggle = document.getElementById('bulletToggle');
  if (toggle) {
    // Browsers restore checkbox state across a reload, so the box can come back
    // unchecked while the curtain still thinks it is enabled. The curtain must
    // default back to on every visit (FR-008) and JS state must never desync
    // from the control, so re-assert both here rather than trusting the markup.
    toggle.checked = true;
    curtain.setEnabled(true);
    toggle.addEventListener('change', () => curtain.setEnabled(toggle.checked));
  }
  curtain.start();
});
