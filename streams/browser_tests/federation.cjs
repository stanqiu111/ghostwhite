// Real two-origin pages/chat. Native synthetic transport runs only with --media.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const config = JSON.parse(fs.readFileSync(0, 'utf8'));
const checks = [], errors = [];
const pass = name => { checks.push(name); console.log('PASS', name); };

async function account(browser, role, url) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  await context.route('https://**', route => route.abort());
  await context.addInitScript(() => {
    window.mediaPeers = [];
    const Native = window.RTCPeerConnection;
    window.RTCPeerConnection = class extends Native {
      constructor(...args) { super(...args); window.mediaPeers.push(this); }
    };
  });
  const login = await context.request.post(config[role].base + '/api/authors/login/', {
    data: { username: `user-${role}`, password: config.password },
  });
  assert.equal(login.status(), 200);
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(config[role].base + url);
  return page;
}
async function stats(page) {
  return page.evaluate(async () => {
    const result = { frames: 0, energy: 0 };
    const pc = window.mediaPeers.findLast(pc => pc.connectionState === 'connected');
    if (pc) for (const stat of (await pc.getStats()).values()) {
      if (stat.type === 'inbound-rtp' && stat.kind === 'video') result.frames += stat.framesDecoded || 0;
      if (stat.type === 'inbound-rtp' && stat.kind === 'audio') result.energy += stat.totalAudioEnergy || 0;
    }
    return result;
  });
}
async function delivered(page, audible) {
  const started = Date.now();
  let before = await stats(page), quietSince = started;
  while (Date.now() - started < 6000) {
    await page.waitForTimeout(100);
    const after = await stats(page);
    const frames = after.frames - before.frames, energy = after.energy - before.energy;
    if (audible && frames > 0 && energy > 0.00001) return;
    if (!audible) {
      if (energy >= 0.000001) { before = after; quietSince = Date.now(); }
      else if (frames > 0 && Date.now() - quietSince >= 650) return;
    }
  }
  assert.fail(`Remote video/audio did not settle (audible=${audible})`);
}

(async () => {
  const args = ['--autoplay-policy=no-user-gesture-required'];
  if (config.media) args.push('--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream',
    '--auto-select-tab-capture-source-by-title=Federation capture source',
    `--use-file-for-fake-audio-capture=${config.audio}`);
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium', headless: true, args });
  try {
    const owner = await account(browser, 'a', `/streams/${config.a.stream}/`);
    const viewer = await account(browser, 'b', '/streams/');
    await viewer.locator(`[href="${config.watchPath}"]`).click();
    await viewer.waitForFunction(() => document.getElementById('roomStatus')?.textContent === 'Waiting for host');
    assert.equal(new URL(viewer.url()).origin, config.b.base);
    assert.equal(await viewer.locator('#shareScreenBtn, #microphoneBtn, #endStreamBtn').count(), 0);
    const apiBase = await viewer.locator('#streamPlayer').getAttribute('data-api-base');
    assert(apiBase.startsWith(`/api/remote-nodes/${config.b.remote}/streams/`));
    const markup = await viewer.content();
    assert(!markup.includes(config.a.secret) && !markup.includes(config.b.secret));
    pass('remote discovery opens a viewer-only room on the authenticated home origin');

    const message = '<script>window.federationBrowserProbe=true</script> browser relay';
    await viewer.locator('#bulletInput').fill(message);
    await viewer.locator('#bulletSendBtn').click();
    for (const page of [viewer, owner]) {
      await page.waitForFunction(text => [...document.querySelectorAll('.stream-chat-message p')].some(el => el.textContent === text), message);
      assert.equal(await page.evaluate(() => !!window.federationBrowserProbe), false);
    }
    pass('real browser chat crosses both servers; literal markup stays inert on both pages');

    fs.mkdirSync(config.output, { recursive: true });
    await viewer.waitForFunction(() => !document.body.classList.contains('page-entering'));
    for (const [name, width] of [['remote-desktop', 1440], ['remote-mobile', 390]]) {
      await viewer.setViewportSize({ width, height: 1000 });
      assert(await viewer.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await viewer.screenshot({ path: path.join(config.output, `${name}.png`), fullPage: true, animations: 'disabled' });
    }
    pass('remote waiting room renders at desktop/mobile widths without horizontal overflow');

    // HTTP revocation is tested against real node records in federation.py;
    // inject its terminal status here to verify browser cleanup deterministically.
    await viewer.route('**/api/remote-nodes/**', route => route.fulfill({
      status: 403, contentType: 'application/json', body: '{"detail":"Node disabled"}',
    }));
    await viewer.waitForFunction(() => document.getElementById('playerStateText').textContent.includes('Access to this stream'));
    await viewer.waitForFunction(() => document.getElementById('chatTitle').textContent === 'Chat unavailable');
    assert(await viewer.locator('#remoteVideo').evaluate(video => video.srcObject === null && video.hidden));
    assert(await viewer.locator('#bulletSendBtn').isDisabled());
    await viewer.unroute('**/api/remote-nodes/**');
    await viewer.reload();
    await viewer.waitForFunction(() => document.getElementById('roomStatus').textContent === 'Waiting for host');
    pass('injected access-revocation response closes viewer media/chat; reload recovers after access restoration');

    if (config.media) {
      const source = await browser.newPage();
      await source.goto(config.a.base + '/');
      await source.setContent('<title>Federation capture source</title><h1>Synthetic studio</h1><p id="clock"></p><script>setInterval(()=>clock.textContent=Date.now(),100)</script>');
      await owner.locator('#shareScreenBtn').click();
      await viewer.waitForFunction(() => window.mediaPeers.some(pc => pc.connectionState === 'connected'), null, { timeout: 30000 });
      await delivered(viewer, false);
      await owner.locator('#microphoneBtn').click();
      await owner.waitForFunction(() => window.streamBroadcaster.microphone.state === 'on');
      await delivered(viewer, true);
      pass('native synthetic video and microphone audio reach the viewer through cross-node signaling');
      await owner.locator('#microphoneBtn').click();
      await delivered(viewer, false);
      const late = await account(browser, 'b', config.watchPath);
      await late.waitForFunction(() => window.mediaPeers.some(pc => pc.connectionState === 'connected'), null, { timeout: 30000 });
      await delivered(late, false);
      await owner.locator('#microphoneBtn').click();
      await Promise.all([viewer, late].map(page => delivered(page, true)));
      pass('remote mute, muted late join and unmute preserve advancing video');
      await owner.locator('#stopSharingBtn').click();
      await viewer.waitForFunction(() => document.getElementById('roomStatus').textContent === 'Waiting for host');
      await owner.locator('#shareScreenBtn').click();
      await viewer.waitForFunction(() => window.mediaPeers.some(pc => pc.connectionState === 'connected'), null, { timeout: 30000 });
      await delivered(viewer, false);
      pass('remote stop/restart reconnects with microphone off');
    }
    owner.once('dialog', dialog => dialog.accept());
    await owner.locator('#endStreamBtn').click();
    await viewer.waitForFunction(() => document.getElementById('roomStatus').textContent === 'Ended');
    await viewer.waitForFunction(() => document.getElementById('bulletSendBtn').disabled);
    pass('host ending propagates to the remote viewer and closes chat');
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ browserChecks: checks.length, checks, mediaAttempted: config.media,
      browserErrors: errors, screenshots: config.output }));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
