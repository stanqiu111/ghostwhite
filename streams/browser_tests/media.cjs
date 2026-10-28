// Native WebRTC integration using Chromium synthetic devices and real Django signaling.
const { chromium, request } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const config = JSON.parse(fs.readFileSync(0, 'utf8'));
const executablePath = process.env.CHROMIUM_PATH || '/usr/bin/chromium';
const args = [
  '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream',
  '--auto-select-tab-capture-source-by-title=Commentary capture source',
  `--use-file-for-fake-audio-capture=${config.audio}`,
];
const results = [];
const failures = [];
function pass(name, details) {
  results.push({ name, details });
  console.log(`PASS ${name}${details ? ': ' + JSON.stringify(details) : ''}`);
}
async function account(browser, name, observePlayback = false) {
  const context = await browser.newContext();
  // Only local application requests are needed for the integration test.
  await context.route('https://**', route => route.abort());
  await context.addInitScript(() => {
    window.mediaPeers = [];
    // Record native peer connections for RTP statistics; no behavior is stubbed.
    const NativePeer = window.RTCPeerConnection;
    window.RTCPeerConnection = class extends NativePeer {
      constructor(...args) { super(...args); window.mediaPeers.push(this); }
    };
  });
  if (observePlayback) await context.addInitScript(() => {
    window.nativePlayResults = [];
    const nativePlay = HTMLMediaElement.prototype.play;
    HTMLMediaElement.prototype.play = function (...args) {
      const attempt = { id: this.id, muted: this.muted, volume: this.volume,
        activated: navigator.userActivation.hasBeenActive,
        active: navigator.userActivation.isActive, outcome: 'pending' };
      window.nativePlayResults.push(attempt);
      const promise = nativePlay.apply(this, args);
      // Observe the original promise; do not inject or replace its outcome.
      promise.then(() => { attempt.outcome = 'resolved'; }, error => {
        attempt.outcome = 'rejected'; attempt.error = error.name;
      });
      return promise;
    };
  });
  const started = Date.now();
  const response = await context.request.post(config.base + '/api/authors/login/', {
    data: { username: name, password: config.password },
  }).catch(error => {
    throw new Error(`Test login ${name} failed after ${Date.now() - started}ms (${error.name}); inspect server request diagnostics, not credentials`);
  });
  assert.equal(response.status(), 200, `test account login ${name}, ${Date.now() - started}ms`);
  const page = await context.newPage();
  page.on('pageerror', error => console.error('Browser error:', error.message));
  page.on('console', message => {
    if (message.type() === 'warning') console.error('Browser warning:', message.text());
  });
  await page.goto(config.base + config.path);
  return page;
}
async function connected(page) {
  await page.waitForFunction(() => window.mediaPeers.some(pc => pc.connectionState === 'connected'), null, { timeout: 30000 });
  await page.waitForFunction(() => {
    const video = document.getElementById('remoteVideo');
    return !video.hidden && video.readyState >= 2 && !video.paused;
  }, null, { timeout: 15000 });
}
async function stats(page) {
  return page.evaluate(async () => {
    const pc = window.mediaPeers.findLast(pc => pc.connectionState === 'connected');
    const totals = { energy: 0, samples: 0, frames: 0 };
    if (pc) for (const stat of (await pc.getStats()).values()) {
      if (stat.type !== 'inbound-rtp') continue;
      if (stat.kind === 'audio') {
        totals.energy += stat.totalAudioEnergy || 0;
        totals.samples += stat.totalSamplesReceived || 0;
      }
      if (stat.kind === 'video') totals.frames += stat.framesDecoded || 0;
    }
    return totals;
  });
}
async function measure(page, mode) {
  // Poll for observed delivery, or a continuous quiet window after buffered
  // audio drains. This is a functional check, not the spec's one-second SLA.
  const started = Date.now();
  let windowStart = started;
  let before = await stats(page);
  let after = before;
  while (Date.now() - started < 5000) {
    await new Promise(resolve => setTimeout(resolve, 100));
    after = await stats(page);
    const energy = after.energy - before.energy;
    const frames = after.frames - before.frames;
    if (mode === 'local-muted') {
      assert.equal(await page.locator('#remoteVideo').evaluate(v => v.muted && v.volume === 0.35), true);
      // Inbound RTP energy can grow even with a muted local sink, depending on
      // the browser. The native element's mute state establishes local silence.
      if (frames > 0 && Date.now() - windowStart >= 650) {
        return { energy, frames, localMuted: true, elapsedMs: Date.now() - started };
      }
    } else if (mode === true && frames > 0 && energy > 0.00001) {
      return { energy, frames, elapsedMs: Date.now() - started };
    } else if (mode === false) {
      if (energy >= 0.000001) {
        before = after; windowStart = Date.now();
      } else if (frames > 0 && Date.now() - windowStart >= 650) {
        return { energy, frames, elapsedMs: Date.now() - started };
      }
    }
  }
  assert.fail(`media ${mode} did not settle within 5000ms: ${JSON.stringify({ before, after })}`);
}
async function bulletChecks(owner, viewers) {
  const sender = viewers[0];
  const text = `<script>window.bulletExecuted=true</script> ${Date.now()}`;
  await sender.locator('#bulletInput').fill(text);
  await sender.locator('#bulletSendBtn').click();
  for (const page of [owner, ...viewers]) {
    await page.waitForFunction(text => [...document.querySelectorAll('.bullet-msg')].some(el =>
      el.lastChild?.nodeType === Node.TEXT_NODE && el.lastChild.textContent === text), text);
    assert.equal(await page.evaluate(() => !!window.bulletExecuted), false);
    assert.equal(await page.locator('.bullet-msg script').count(), 0);
  }
}
async function basicChecks(owner, viewers, commentary = false) {
  await bulletChecks(owner, viewers);
  const sender = viewers[0];
  await sender.locator('#bulletToggle').uncheck();
  await sender.waitForFunction(() => document.querySelectorAll('.bullet-msg').length === 0);
  for (const mode of ['fit', 'fill', 'theater', 'auto']) {
    await sender.locator('#displayModeSelect').selectOption(mode);
    assert.equal(await sender.locator('#streamPlayer').getAttribute('data-display-mode'), mode);
  }
  await sender.locator('#fullscreenBtn').click();
  await sender.waitForFunction(() => !!document.fullscreenElement);
  await sender.evaluate(() => document.exitFullscreen());
  await sender.locator('#bulletToggle').check();
  pass(`T020 overlap (${commentary ? 'commentary active' : 'video only'}): multi-viewer/owner bullets, inert markup, toggle, display modes and fullscreen`);
}

async function captureChecks(owner, browser) {
  await owner.locator('#shareScreenBtn').click();
  await owner.waitForFunction(() => window.streamBroadcaster.active);
  const viewer = await account(browser, 'media-viewer-0');
  await owner.waitForFunction(() => [...window.streamBroadcaster.pcs.values()].some(pc =>
    pc.remoteDescription?.type === 'answer' && pc.signalingState === 'stable'));
  await owner.evaluate(() => {
    // A previously closed playback-fixture page may have left an unanswered
    // join in the relay. Select the viewer whose native handshake completed.
    window.preMicrophonePeer = [...window.streamBroadcaster.pcs.values()].find(pc =>
      pc.remoteDescription?.type === 'answer' && pc.signalingState === 'stable');
    window.preMicrophoneVideo = window.preMicrophonePeer.getSenders().find(sender => sender.track?.kind === 'video').track;
  });
  assert.equal(await owner.locator('#microphoneStatus').textContent(), 'Microphone off');
  assert.equal(await owner.evaluate(() => window.streamBroadcaster.microphone.stream), null);
  await owner.locator('#microphoneBtn').click();
  await owner.waitForFunction(() => document.getElementById('microphoneStatus').textContent === 'Microphone on');
  assert.equal(await owner.evaluate(() => {
    const broadcaster = window.streamBroadcaster;
    return broadcaster.microphone.stream.getAudioTracks()[0].readyState === 'live'
      && broadcaster.media.getVideoTracks()[0].readyState === 'live'
      && broadcaster.ui.preview.muted;
  }), true);
  pass('native synthetic screen/microphone capture is opt-in; owner preview stays muted');
  await owner.waitForFunction(() => window.preMicrophonePeer.getSenders().some(sender =>
    sender.track === window.streamBroadcaster.microphone.stream.getAudioTracks()[0]));
  const peerAfterEnable = await owner.evaluate(() => {
    const pc = window.preMicrophonePeer;
    return { registered: [...window.streamBroadcaster.pcs.values()].includes(pc),
      signaling: pc.signalingState,
      audio: pc.getSenders().find(sender => sender.track?.kind === 'audio')?.track.readyState,
      sameVideo: pc.getSenders().find(sender => sender.track?.kind === 'video')?.track === window.preMicrophoneVideo };
  });
  assert.deepEqual(peerAfterEnable, { registered: true, signaling: 'stable', audio: 'live', sameVideo: true });
  pass('native SDP-negotiated sender accepts microphone without replacing peer or video (transport remains unverified)');
  await owner.locator('#microphoneBtn').click();
  assert.equal(await owner.evaluate(() => window.streamBroadcaster.microphone.stream.getAudioTracks()[0].enabled), false);
  const lateViewer = await account(browser, 'media-viewer-1');
  await owner.waitForFunction(() => [...window.streamBroadcaster.pcs.values()].filter(pc =>
    pc.remoteDescription?.type === 'answer' && pc.signalingState === 'stable').length === 2);
  assert.equal(await owner.evaluate(() => [...window.streamBroadcaster.pcs.values()].every(pc =>
    pc.getSenders().find(sender => sender.track?.kind === 'audio').track.enabled === false)), true);
  pass('existing and late native senders both use the disabled microphone track while muted');
  await bulletChecks(owner, [viewer, lateViewer]);
  pass('real bullet relay preserves exact text beside sender label; markup is inert');
  await viewer.context().close(); await lateViewer.context().close();
  await owner.locator('#microphoneBtn').click();
  assert.equal(await owner.evaluate(() => window.streamBroadcaster.microphone.stream.getAudioTracks()[0].enabled
    && window.streamBroadcaster.media.getVideoTracks()[0] === window.preMicrophoneVideo
    && window.preMicrophoneVideo.readyState === 'live'), true);
  pass('native microphone mute/unmute changes outgoing track without stopping screen capture');

  await owner.evaluate(() => {
    const track = window.streamBroadcaster.microphone.stream.getAudioTracks()[0];
    track.stop(); track.dispatchEvent(new Event('ended'));
  });
  assert.equal(await owner.locator('#microphoneStatus').textContent(), 'Microphone unavailable');
  assert.equal(await owner.evaluate(() => window.streamBroadcaster.media.getVideoTracks()[0].readyState), 'live');
  await owner.locator('#microphoneBtn').click();
  await owner.waitForFunction(() => document.getElementById('microphoneStatus').textContent === 'Microphone on');
  pass('injected device-loss event preserves native screen capture; explicit retry reacquires native microphone');

  await owner.evaluate(() => { window.heldTrack = window.streamBroadcaster.microphone.stream.getAudioTracks()[0]; });
  await owner.locator('#microphoneBtn').click();
  await owner.locator('#stopSharingBtn').click();
  assert.equal(await owner.evaluate(() => window.heldTrack.readyState), 'ended');
  await owner.locator('#shareScreenBtn').click();
  await owner.waitForFunction(() => window.streamBroadcaster.active);
  assert.equal(await owner.locator('#microphoneStatus').textContent(), 'Microphone off');
  pass('stop while muted releases native microphone; new share defaults off');

  await owner.evaluate(() => {
    window.originalGetUserMedia = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    navigator.mediaDevices.getUserMedia = async () => { throw new DOMException('Injected denial', 'NotAllowedError'); };
  });
  await owner.locator('#microphoneBtn').click();
  await owner.waitForFunction(() => document.getElementById('microphoneStatus').textContent === 'Microphone unavailable');
  assert.equal(await owner.evaluate(() => window.streamBroadcaster.media.getVideoTracks()[0].readyState), 'live');
  assert.match(await owner.locator('#microphoneError').textContent(), /permission was not granted/);
  await owner.evaluate(() => { navigator.mediaDevices.getUserMedia = window.originalGetUserMedia; });
  await owner.locator('#microphoneBtn').click();
  await owner.waitForFunction(() => document.getElementById('microphoneStatus').textContent === 'Microphone on');
  pass('injected permission denial leaves video running; retry uses native capture');
  await owner.locator('#stopSharingBtn').click();
  await owner.locator('#shareScreenBtn').click();
  await owner.waitForFunction(() => window.streamBroadcaster.active);
  await owner.evaluate(() => {
    navigator.mediaDevices.getUserMedia = async constraints => {
      const stream = await window.originalGetUserMedia(constraints);
      window.delayedTrack = stream.getAudioTracks()[0];
      return new Promise(resolve => { window.releaseGrant = () => resolve(stream); });
    };
  });
  await owner.locator('#microphoneBtn').click();
  await owner.waitForFunction(() => !!window.releaseGrant);
  await owner.locator('#stopSharingBtn').click();
  await owner.evaluate(() => { window.releaseGrant(); navigator.mediaDevices.getUserMedia = window.originalGetUserMedia; });
  await owner.waitForFunction(() => window.delayedTrack.readyState === 'ended');
  assert.equal(await owner.locator('#microphoneStatus').textContent(), 'Microphone off');
  pass('delayed grant injection after stop releases the actual captured microphone');

  await owner.locator('#shareScreenBtn').click();
  await owner.waitForFunction(() => window.streamBroadcaster.active);
  await owner.locator('#microphoneBtn').click();
  await owner.waitForFunction(() => document.getElementById('microphoneStatus').textContent === 'Microphone on');
  await owner.evaluate(() => {
    window.nativeStopTrack = window.streamBroadcaster.microphone.stream.getAudioTracks()[0];
    const display = window.streamBroadcaster.media.getVideoTracks()[0];
    display.stop(); display.dispatchEvent(new Event('ended'));
  });
  assert.equal(await owner.evaluate(() => window.nativeStopTrack.readyState), 'ended');
  pass('injected browser capture-ended event releases native microphone');

  await owner.locator('#shareScreenBtn').click();
  await owner.waitForFunction(() => window.streamBroadcaster.active);
  await owner.locator('#microphoneBtn').click();
  await owner.waitForFunction(() => document.getElementById('microphoneStatus').textContent === 'Microphone on');
  await owner.locator('#endStreamBtn').click();
  await owner.waitForFunction(() => document.getElementById('streamPlayer').dataset.streamStatus === 'ended');
  assert.equal(await owner.locator('#microphoneBtn').count(), 0);
  pass('real end-stream API action removes broadcast controls');
}

async function localPlaybackChecks(browser) {
  const viewer = await account(browser, 'media-viewer-6');
  // Incoming media fixture: native canvas/audio tracks, not a WebRTC transport test.
  await viewer.evaluate(() => {
    const canvas = document.createElement('canvas');
    const paint = canvas.getContext('2d');
    window.paintTimer = setInterval(() => {
      paint.fillStyle = Date.now() % 2 ? 'red' : 'blue'; paint.fillRect(0, 0, 300, 150);
    }, 100);
    const audio = new AudioContext();
    const tone = audio.createOscillator();
    const destination = audio.createMediaStreamDestination();
    tone.connect(destination); tone.start();
    window.playbackAudio = audio;
    const stream = canvas.captureStream(5);
    stream.addTrack(destination.stream.getAudioTracks()[0]);
    const video = document.getElementById('remoteVideo');
    video.srcObject = stream; video.hidden = false; video.dataset.audioAvailable = '1';
    video.dispatchEvent(new Event('streamchange'));
    video.dispatchEvent(new Event('commentarychange'));
  });
  await viewer.waitForFunction(() => document.getElementById('remoteVideo').readyState >= 2);
  // Locally generated streams can receive Chromium's active-capture autoplay
  // exemption. Inject only the denial here; the full transport test above uses
  // genuine incoming media in a separate browser with restrictive autoplay.
  await viewer.evaluate(() => {
    const video = document.getElementById('remoteVideo');
    window.nativePlayback = video.play.bind(video);
    video.play = function () {
      if (!this.muted) return Promise.reject(new DOMException('Injected autoplay denial', 'NotAllowedError'));
      return window.nativePlayback();
    };
    video.dispatchEvent(new Event('commentarychange'));
  });
  await viewer.locator('#enableSoundBtn').waitFor({ state: 'visible' });
  assert.equal(await viewer.locator('#remoteVideo').evaluate(v => v.muted && !v.paused), true);
  await viewer.evaluate(() => { document.getElementById('remoteVideo').play = window.nativePlayback; });
  await viewer.locator('#enableSoundBtn').click();
  await viewer.waitForFunction(() => !document.getElementById('remoteVideo').muted && !document.getElementById('remoteVideo').paused);
  pass('injected autoplay denial preserves native synthetic video; Enable sound restores native playback');
  await viewer.context().close();
}

async function withoutGesture(session, fn) {
  const result = await session.send('Runtime.evaluate', {
    expression: `(${fn.toString()})()`, userGesture: false,
    awaitPromise: true, returnByValue: true,
  });
  assert.equal(result.exceptionDetails, undefined, 'non-activating browser observation failed');
  return result.result.value;
}

async function nativeAutoplayPreflight(browser) {
  // This checks ordinary native file playback policy, not incoming WebRTC.
  const page = await browser.newPage();
  await page.goto(config.base + '/capture-source/');
  const session = await page.context().newCDPSession(page);
  try {
    const result = await withoutGesture(session, async () => {
      const audio = new Audio('/test-tone.wav');
      document.body.appendChild(audio);
      try { await audio.play(); return { outcome: 'resolved', activated: navigator.userActivation.hasBeenActive }; }
      catch (error) { return { outcome: error.name, activated: navigator.userActivation.hasBeenActive }; }
    });
    assert.deepEqual(result, { outcome: 'NotAllowedError', activated: false },
      'restricted browser must reject native file audio without activation');
    pass('native file-autoplay preflight rejects sound without activation (not WebRTC coverage)');
  } finally {
    await session.detach(); await page.context().close();
  }
}

async function incomingAutoplayChecks(browser) {
  const page = await account(browser, 'media-viewer-6', true);
  const session = await page.context().newCDPSession(page);
  let state;
  try {
    const deadline = Date.now() + 30000;
    while (Date.now() < deadline) {
      // Playwright evaluate()/waitForFunction() supply userGesture:true.
      // Do not use them (or locator waits) before native denial is observed.
      state = await withoutGesture(session, () => {
        const video = document.getElementById('remoteVideo');
        return { activated: navigator.userActivation.hasBeenActive,
          attempts: window.nativePlayResults, available: video.dataset.audioAvailable,
          muted: video.muted, paused: video.paused, ready: video.readyState,
          visible: !video.hidden, enableVisible: !document.getElementById('enableSoundBtn').hidden,
          peers: window.mediaPeers.map(pc => ({ connection: pc.connectionState, ice: pc.iceConnectionState })) };
      });
      assert.equal(state.activated, false, `autoplay setup gained activation: ${JSON.stringify(state)}`);
      const denied = state.attempts.some(attempt => attempt.id === 'remoteVideo'
        && !attempt.muted && !attempt.activated && attempt.error === 'NotAllowedError');
      if (denied && state.enableVisible && state.muted && !state.paused && state.ready >= 2 && state.visible) break;
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    assert(state?.attempts.some(attempt => attempt.id === 'remoteVideo' && !attempt.muted
      && !attempt.activated && attempt.error === 'NotAllowedError')
      && state.enableVisible && state.muted && !state.paused && state.ready >= 2 && state.visible,
    `Genuine incoming-stream autoplay denial/recovery prerequisite was not established: ${JSON.stringify(state)}`);
    // Only this explicit click grants the viewer activation.
    await page.locator('#enableSoundBtn').click();
    await page.waitForFunction(() => !document.getElementById('remoteVideo').muted && !document.getElementById('remoteVideo').paused);
    pass('observed native incoming-stream NotAllowedError preserves video; Enable sound recovers', await measure(page, true));
  } finally {
    await session.detach(); await page.context().close();
  }
}

async function serverChecks() {
  const contexts = [];
  const latencies = [];
  async function login(name) {
    const client = await request.newContext({ baseURL: config.base });
    contexts.push(client);
    const started = Date.now();
    const response = await client.post('/api/authors/login/', { data: { username: name, password: config.password } });
    assert.equal(response.status(), 200, `concurrent login ${name}`);
    latencies.push(Date.now() - started);
    return client;
  }
  try {
    const owner = await login('media-owner');
    const viewers = await Promise.all([0, 1, 2, 3, 4].map(i => login(`media-viewer-${i}`)));
    const serial = config.path.split('/').filter(Boolean).at(-1);
    const clients = [owner, ...viewers];
    await Promise.all([
      ...clients.map(async (client, index) => {
        for (let round = 0; round < 12; round++) {
          const query = index === 0 ? 'role=streamer' : `role=viewer&peer_id=load-viewer-${index}`;
          const started = Date.now();
          const response = await client.get(`/api/streams/${serial}/signals/?${query}`);
          assert.equal(response.status(), 200, `concurrent signaling poll ${index}/${round}`);
          latencies.push(Date.now() - started);
        }
      }),
      (async () => { for (let round = 0; round < 4; round++) await login('media-viewer-6'); })(),
    ]);
    pass('isolated SQLite concurrent signaling and late-login requests succeed', {
      requests: latencies.length, maxMs: Math.max(...latencies),
    });
  } finally {
    await Promise.all(contexts.map(context => context.dispose()));
  }
}

(async () => {
  if (config.serverCheck) {
    try { await serverChecks(); }
    finally { console.log(JSON.stringify({ serverCheck: true, passed: results.length, results })); }
    return;
  }
  const browser = await chromium.launch({ executablePath, headless: true, args: [...args, '--autoplay-policy=no-user-gesture-required'] });
  let restrictedBrowser;
  try {
    const source = await browser.newPage(); await source.goto(config.base + '/capture-source/');
    const owner = await account(browser, 'media-owner');
    if (config.captureOnly) {
      restrictedBrowser = await chromium.launch({ executablePath, headless: true,
        args: ['--autoplay-policy=document-user-activation-required', '--disable-features=PreloadMediaEngagementData,MediaEngagementBypassAutoplayPolicies'] });
      await nativeAutoplayPreflight(restrictedBrowser);
      await localPlaybackChecks(restrictedBrowser);
      await captureChecks(owner, browser);
      return;
    }
    const viewers = await Promise.all([0, 1].map(i => account(browser, `media-viewer-${i}`)));
    await owner.locator('#shareScreenBtn').click();
    try {
      await Promise.all(viewers.map(connected));
    } catch (error) {
      for (const [role, page] of [['owner', owner], ...viewers.map(p => ['viewer', p])]) {
        console.error('Connection diagnostic:', role, await page.evaluate(() => ({
          state: document.querySelector('.stream-player-placeholder')?.dataset.playerState,
          shareError: document.getElementById('shareError')?.textContent,
          active: window.streamBroadcaster?.active,
          peers: window.mediaPeers.map(pc => ({ state: pc.connectionState, ice: pc.iceConnectionState,
            gathering: pc.iceGatheringState, signaling: pc.signalingState,
            local: pc.localDescription?.type, remote: pc.remoteDescription?.type,
            senders: pc.getSenders().length, receivers: pc.getReceivers().length })),
        })));
      }
      throw error;
    }
    pass('native screen capture and real Django signaling connect two viewers', await measure(viewers[0], false));
    await basicChecks(owner, viewers);
    if (config.baseline) {
      await owner.locator('#stopSharingBtn').click();
      await Promise.all(viewers.map(p => p.waitForFunction(() => document.querySelector('.stream-player-placeholder').dataset.playerState === 'waiting')));
      pass('baseline stop returns viewers to waiting');
      return;
    }

    await viewers[0].evaluate(() => {
      window.originalPeer = window.mediaPeers.findLast(pc => pc.connectionState === 'connected');
      window.originalVideoTrack = document.getElementById('remoteVideo').srcObject.getVideoTracks()[0];
    });
    assert.equal(await owner.locator('#microphoneStatus').textContent(), 'Microphone off');
    assert.equal(await viewers[0].locator('#volumeControls').isVisible(), false);
    await owner.locator('#microphoneBtn').click();
    await owner.waitForFunction(() => document.getElementById('microphoneStatus').textContent === 'Microphone on');
    await Promise.all(viewers.map(p => p.waitForFunction(() => document.getElementById('remoteVideo').dataset.audioAvailable === '1')));
    assert.equal(await viewers[0].evaluate(() => window.originalPeer.connectionState === 'connected'
      && document.getElementById('remoteVideo').srcObject.getVideoTracks()[0] === window.originalVideoTrack), true);
    pass('microphone enables on existing peers without replacing video', await measure(viewers[0], true));
    await basicChecks(owner, viewers, true);
    const additional = await Promise.all([2, 3, 4].map(i => account(browser, `media-viewer-${i}`)));
    await Promise.all(additional.map(connected)); viewers.push(...additional);
    pass('five viewers receive native audio and advancing video', await Promise.all(viewers.map(p => measure(p, true))));

    await viewers[0].locator('#volumeSlider').fill('0.35');
    await viewers[0].locator('#muteBtn').click();
    assert.equal(await viewers[0].locator('#remoteVideo').evaluate(v => v.muted), true);
    assert.equal(await viewers[1].locator('#remoteVideo').evaluate(v => v.muted), false);
    await owner.locator('#microphoneBtn').click();
    pass('broadcaster mute silences all five viewers while video continues', await Promise.all(viewers.map(p => measure(p, false))));
    await viewers.pop().context().close();
    const late = await account(browser, 'media-viewer-5'); await connected(late); viewers.push(late);
    pass('late joiner while muted receives silence', await measure(late, false));
    await owner.locator('#microphoneBtn').click();
    pass('unmute restores listening viewers; locally muted viewer stays silent', await Promise.all(
      viewers.map((page, index) => measure(page, index === 0 ? 'local-muted' : true))));
    assert.equal(await viewers[0].locator('#remoteVideo').evaluate(v => v.muted && v.volume === 0.35), true);
    await viewers[0].locator('#muteBtn').click();
    pass('explicit local unmute also receives audio at retained volume', await measure(viewers[0], true));
    assert.equal(await viewers[0].locator('#remoteVideo').evaluate(v => !v.muted && v.volume === 0.35), true);
    await viewers[0].locator('#muteBtn').click();
    assert.equal(await viewers[0].locator('#remoteVideo').evaluate(v => v.muted && v.volume === 0.35), true);
    pass('viewer mute/volume preferences remain local and survive broadcaster changes');

    // Separate browser with actual restrictive autoplay policy; no play() stubs.
    // Keep the active audience within the feature's five-viewer scope.
    await viewers.pop().context().close();
    restrictedBrowser = await chromium.launch({ executablePath, headless: true,
      args: ['--autoplay-policy=document-user-activation-required', '--disable-features=PreloadMediaEngagementData,MediaEngagementBypassAutoplayPolicies'] });
    try {
      await nativeAutoplayPreflight(restrictedBrowser);
      await incomingAutoplayChecks(restrictedBrowser);
    } catch (error) {
      // Keep the acceptance failure, but still exercise stop/restart/end below.
      failures.push({ name: 'genuine incoming-stream autoplay', error: error.message });
      console.error('FAIL genuine incoming-stream autoplay:', error.message);
    }
    await restrictedBrowser.close(); restrictedBrowser = null;

    await owner.evaluate(() => { window.capturedMicrophone = window.streamBroadcaster.microphone.stream.getAudioTracks()[0]; });
    await owner.locator('#stopSharingBtn').click();
    assert.equal(await owner.evaluate(() => window.capturedMicrophone.readyState), 'ended');
    await Promise.all(viewers.map(p => p.waitForFunction(() => document.querySelector('.stream-player-placeholder').dataset.playerState === 'waiting')));
    pass('stop releases native microphone and returns all viewers to waiting');
    await owner.locator('#shareScreenBtn').click();
    await Promise.all(viewers.map(connected));
    assert.equal(await owner.locator('#microphoneStatus').textContent(), 'Microphone off');
    pass('restart defaults to video only');
    await owner.locator('#microphoneBtn').click();
    await owner.waitForFunction(() => document.getElementById('microphoneStatus').textContent === 'Microphone on');
    await owner.evaluate(() => { window.endingMicrophone = window.streamBroadcaster.microphone.stream.getAudioTracks()[0]; });
    await owner.locator('#endStreamBtn').click();
    await owner.waitForFunction(() => document.getElementById('streamPlayer').dataset.streamStatus === 'ended');
    await Promise.all(viewers.map(p => p.waitForFunction(() => document.querySelector('.stream-player-placeholder').dataset.playerState === 'ended')));
    pass('real end-stream action tears down broadcast and all viewers reach ended');
    assert.equal(failures.length, 0, 'acceptance checks failed; see failures in the JSON report');
  } finally {
    if (restrictedBrowser) await restrictedBrowser.close();
    await browser.close();
    console.log(JSON.stringify({ baseline: config.baseline, captureOnly: config.captureOnly, passed: results.length, results, failures }));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
