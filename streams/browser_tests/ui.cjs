// Real Django pages and chat; synthetic screen capture and explicitly simulated
// viewer presentation states. This is layout/UI coverage, not WebRTC delivery.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const config = JSON.parse(fs.readFileSync(0, 'utf8'));
fs.mkdirSync(config.output, { recursive: true });
const checks = [];
const pass = name => { checks.push(name); console.log('PASS', name); };
const browserErrors = [];

async function account(browser, name) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  await context.route('https://**', route => route.abort());
  const login = await context.request.post(config.base + '/api/authors/login/', {
    data: { username: name, password: config.password },
  });
  assert.equal(login.status(), 200);
  const page = await context.newPage();
  page.on('pageerror', error => browserErrors.push(error.stack || error.message));
  await page.goto(config.base + config.path);
  await page.waitForFunction(() => !document.body.classList.contains('page-entering'));
  return page;
}
async function shot(page, name) {
  await page.screenshot({ path: path.join(config.output, `${name}.png`), fullPage: true, animations: 'disabled' });
}
async function noOverflow(page) {
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'no horizontal page overflow');
}
async function textContrast(page) {
  let results;
  const deadline = Date.now() + 1500;
  do {
    results = await page.evaluate(() => {
    const luminance = color => {
      const values = color.match(/[\d.]+/g).slice(0, 3).map(value => Number(value) / 255)
        .map(value => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4);
      return values[0] * 0.2126 + values[1] * 0.7152 + values[2] * 0.0722;
    };
    return [['.stream-back-link', 'body'], ['.stream-stage-hint', '.stream-player'],
      ['.stream-chat-caption', '.stream-chat'], ['#chatLimit', '.stream-chat'],
      ['#bulletSendBtn', '#bulletSendBtn'], ['#endStreamBtn', 'body']].map(([foreground, background]) => {
      const element = document.querySelector(foreground);
      if (!element) return null;
      const light = [luminance(getComputedStyle(element).color),
        luminance(getComputedStyle(document.querySelector(background)).backgroundColor)].sort((a, b) => a - b);
      return { selector: foreground, ratio: (light[1] + 0.05) / (light[0] + 0.05) };
    }).filter(Boolean);
    });
    if (results.every(result => result.ratio >= 4.5)) return;
    // Theme switching animates existing button colours. Wait for the actual
    // contrast target rather than checking an intermediate transition frame.
    await new Promise(resolve => setTimeout(resolve, 50));
  } while (Date.now() < deadline);
  for (const result of results) assert(result.ratio >= 4.5, `${result.selector} contrast ${result.ratio}`);
}
async function send(page, content) {
  const response = await page.evaluate(async ({ serial, content }) => {
    const result = await fetch(`/api/streams/${serial}/bullets/`, {
      method: 'POST', credentials: 'same-origin', headers: bulletHeaders(), body: JSON.stringify({ content }),
    });
    return result.status;
  }, { serial: config.path.split('/').filter(Boolean).at(-1), content });
  assert.equal(response, 201);
}
async function waitChat(page, content) {
  await page.waitForFunction(text => [...document.querySelectorAll('.stream-chat-message p')].some(el => el.textContent === text), content);
}
async function simulatedViewerStage(page) {
  await page.evaluate(async () => {
    const canvas = document.createElement('canvas');
    canvas.width = 1280; canvas.height = 720;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#e8ecf3'; ctx.fillRect(0, 0, 1280, 720);
    ctx.fillStyle = '#182237'; ctx.font = '24px sans-serif'; ctx.fillText('STUDIO / INTERFACE PREVIEW', 80, 100);
    ctx.font = '64px sans-serif'; ctx.fillText('A space for ideas.', 80, 300);
    ctx.fillStyle = '#536077'; ctx.font = '26px sans-serif'; ctx.fillText('Neutral synthetic video · no private screen content', 80, 365);
    ctx.strokeStyle = '#2862d6'; ctx.lineWidth = 3; ctx.strokeRect(80, 440, 210, 140); ctx.strokeRect(330, 440, 210, 140);
    const video = document.getElementById('remoteVideo');
    video.srcObject = canvas.captureStream(1); video.hidden = false; await video.play();
    const placeholder = document.querySelector('.stream-player-placeholder');
    placeholder.dataset.playerState = 'live'; placeholder.hidden = true;
    document.getElementById('fullscreenBtn').hidden = false;
    video.dispatchEvent(new Event('streamchange'));
  });
  await page.waitForFunction(() => document.getElementById('roomStatus').textContent === 'Live');
}

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium', headless: true,
    args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream',
      '--auto-select-tab-capture-source-by-title=Commentary capture source', '--autoplay-policy=no-user-gesture-required'] });
  try {
    const source = await browser.newPage(); await source.goto(config.base + '/capture-source/');
    const owner = await account(browser, 'media-owner');
    const viewer = await account(browser, 'media-viewer-0');
    await owner.waitForFunction(() => document.getElementById('chatStatus').textContent === '');
    assert.equal(await owner.locator('#roomStatus').textContent(), 'Off air');
    assert.equal(await viewer.locator('#roomStatus').textContent(), 'Waiting for host');
    assert.equal(await owner.locator('#microphoneBtn').isDisabled(), true);
    assert.equal(await viewer.locator('#microphoneBtn').count(), 0);
    const stage = await viewer.locator('#streamPlayer').boundingBox();
    const chat = await viewer.locator('.stream-chat').boundingBox();
    assert(chat.x > stage.x + stage.width && stage.width > 850, 'prominent stage and separate desktop chat');
    await noOverflow(owner); await noOverflow(viewer);
    await textContrast(owner);
    await shot(owner, 'owner-idle-desktop-light'); await shot(viewer, 'viewer-waiting-desktop-light');
    pass('truthful idle/waiting states, role controls, desktop stage/chat layout');

    await viewer.locator('#bulletInput').fill('Hello! Testing the conversation from the viewer window.');
    await viewer.locator('#bulletSendBtn').click();
    await waitChat(owner, 'Hello! Testing the conversation from the viewer window.');
    await waitChat(viewer, 'Hello! Testing the conversation from the viewer window.');
    await send(owner, 'Welcome — this is a synthetic interface preview.');
    await waitChat(viewer, 'Welcome — this is a synthetic interface preview.');
    const hostile = '<script>window.chatExecuted=true</script>';
    await send(viewer, hostile); await waitChat(owner, hostile);
    assert.equal(await owner.locator('.stream-chat-message script').count(), 0);
    assert.equal(await owner.evaluate(() => !!window.chatExecuted), false);
    await owner.locator('#bulletToggle').uncheck();
    await send(viewer, 'Chat stays readable when comments on video are turned off.');
    await waitChat(owner, 'Chat stays readable when comments on video are turned off.');
    assert.equal(await owner.locator('.bullet-msg').count(), 0);
    await owner.locator('#bulletToggle').check();
    assert.equal(await owner.locator('.bullet-msg').count(), 0, 'enabling overlay does not replay messages');
    pass('real chat send/receive, inert text, and overlay-off/no-replay semantics');

    await owner.locator('#shareScreenBtn').focus();
    await owner.keyboard.press('Tab');
    await owner.keyboard.press('Shift+Tab');
    assert.notEqual(await owner.locator('#shareScreenBtn').evaluate(el => getComputedStyle(el).outlineStyle), 'none');
    await owner.locator('#shareScreenBtn').click();
    await owner.waitForFunction(() => window.streamBroadcaster.active);
    await owner.waitForFunction(() => document.getElementById('roomStatus').textContent === 'Live');
    assert.equal(await owner.evaluate(() => window.streamBroadcaster.microphone.stream), null);
    await owner.locator('#microphoneBtn').click();
    await owner.waitForFunction(() => document.getElementById('microphoneStatus').textContent === 'Microphone on');
    await owner.locator('#microphoneBtn').click();
    assert.equal(await owner.evaluate(() => window.streamBroadcaster.microphone.stream.getAudioTracks()[0].enabled), false);
    await owner.evaluate(() => document.documentElement.dataset.theme = 'dark');
    const primary = await owner.locator('#microphoneBtn').evaluate(el => getComputedStyle(el).backgroundColor);
    const danger = await owner.locator('#endStreamBtn').evaluate(el => getComputedStyle(el).color);
    assert.notEqual(primary, danger);
    await textContrast(owner);
    await shot(owner, 'owner-live-muted-desktop-dark');
    await owner.locator('#stopSharingBtn').click();
    await owner.waitForFunction(() => document.getElementById('roomStatus').textContent === 'Off air');
    assert.equal(await owner.locator('#microphoneBtn').isDisabled(), true);
    pass('keyboard focus, synthetic share/mute/stop controls and truthful on-air state');

    // Close signaling traffic before injecting only the viewer's presentation.
    await viewer.waitForFunction(() => document.querySelector('.stream-player-placeholder').dataset.playerState === 'waiting');
    await viewer.route('**/signals/**', route => route.abort());
    await simulatedViewerStage(viewer);
    await viewer.evaluate(() => document.documentElement.dataset.theme = 'dark');
    await shot(viewer, 'viewer-stage-desktop-dark-simulated');
    await viewer.locator('#displayModeSelect').selectOption('theater');
    assert((await viewer.locator('.stream-chat').boundingBox()).y > (await viewer.locator('#streamPlayer').boundingBox()).y);
    await viewer.locator('#displayModeSelect').selectOption('auto');
    await viewer.setViewportSize({ width: 390, height: 844 });
    await viewer.emulateMedia({ reducedMotion: 'reduce' });
    await noOverflow(viewer);
    const mobileStage = await viewer.locator('#streamPlayer').boundingBox();
    assert((await viewer.locator('.stream-chat').boundingBox()).y > mobileStage.y + mobileStage.height);
    await shot(viewer, 'viewer-mobile-dark-simulated');
    await viewer.evaluate(() => document.documentElement.dataset.theme = 'light');
    await shot(viewer, 'viewer-mobile-light-simulated');
    await owner.setViewportSize({ width: 390, height: 844 });
    await owner.emulateMedia({ reducedMotion: 'reduce' });
    await noOverflow(owner);
    await shot(owner, 'owner-idle-mobile-dark');
    pass('390px light/dark layouts, theater mode and reduced-motion rendering');

    // Exercise the actual presenter with a separate DOM for bounded history;
    // fixture messages stay in this test, never in the product template.
    await viewer.evaluate(() => {
      const chat = document.getElementById('chatMessages');
      const latest = document.getElementById('chatLatestBtn');
      const empty = document.getElementById('chatEmpty');
      const original = [...chat.children];
      const curtain = new BulletCurtain('fixture', { chat, latest, empty });
      curtain.enabled = false;
      for (let id = 1; id <= 105; id++) curtain.receive({ id, sender: { displayName: 'Fixture' }, content: `Fixture ${id}`, created_at: '2026-10-28T12:00:00Z' });
      if (chat.children.length !== 100 || chat.firstElementChild.querySelector('p').textContent !== 'Fixture 6') throw new Error('history is not bounded');
      curtain.receive({ id: 104, sender: { displayName: 'Fixture' }, content: 'duplicate' });
      if (chat.children.length !== 100 || chat.lastElementChild.querySelector('p').textContent !== 'Fixture 105') throw new Error('stale batch duplicated messages');
      chat.scrollTop = 0;
      curtain.receive({ id: 106, sender: { displayName: 'Fixture' }, content: 'New while reading' });
      if (chat.scrollTop > 100 || latest.hidden) throw new Error('new message interrupted reading');
      latest.click();
      if (!latest.hidden || chat.scrollHeight - chat.clientHeight - chat.scrollTop > 2) throw new Error('latest-message action did not scroll');
      chat.replaceChildren(...original);
      chat.scrollTop = chat.scrollHeight;
    });
    pass('bounded chat history, deduplication, reading position and latest-message action (DOM fixture)');
    await viewer.evaluate(async () => {
      for (const method of ['start', 'poll']) {
        const ui = { status: document.createElement('span'), input: document.createElement('input'),
          sendBtn: document.createElement('button'), error: document.createElement('span') };
        const curtain = new BulletCurtain('fixture', ui);
        let reject;
        curtain.fetch = () => new Promise((resolve, fail) => { reject = fail; });
        const pending = curtain[method]();
        curtain.onEnded(); reject(new Error('late network failure')); await pending;
        if (!ui.status.textContent.startsWith('Chat closed') || curtain.pollTimer !== null) throw new Error(`${method} revived closed chat`);
      }
    });
    pass('late bootstrap/poll failures cannot revive an ended chat (failure injection)');

    await viewer.route('**/bullets/**', route => route.abort());
    await viewer.waitForFunction(() => document.getElementById('chatStatus').textContent.includes('reconnecting'));
    await viewer.evaluate(() => {
      const placeholder = document.querySelector('.stream-player-placeholder');
      placeholder.dataset.playerState = 'error'; placeholder.hidden = false;
      document.getElementById('remoteVideo').hidden = true;
      document.getElementById('playerStateText').textContent = 'Connection failed.';
      document.getElementById('retryBtn').hidden = false;
      document.getElementById('fullscreenBtn').hidden = true;
    });
    await viewer.waitForFunction(() => document.getElementById('roomStatus').textContent === 'Connection issue');
    await shot(viewer, 'viewer-mobile-error-simulated');
    pass('chat network failure feedback and simulated player error presentation');
    await owner.locator('#endStreamBtn').click();
    await owner.waitForFunction(() => document.getElementById('streamPlayer')?.dataset.streamStatus === 'ended');
    assert.equal(await owner.locator('#roomStatus').textContent(), 'Ended');
    assert.equal(await owner.locator('#bulletForm').count(), 0);
    assert.equal(await owner.locator('#shareScreenBtn').count(), 0);
    await owner.setViewportSize({ width: 1440, height: 1000 });
    await owner.evaluate(() => document.documentElement.dataset.theme = 'light');
    await shot(owner, 'ended-desktop-light');
    pass('real end action removes capture/composer controls and shows closed room');
    assert.deepEqual(browserErrors, []);
  } finally {
    await browser.close();
    console.log(JSON.stringify({ passed: checks.length, checks, screenshots: config.output, browserErrors }));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
