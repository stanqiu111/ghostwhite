// Simulated browser media lifecycle tests; no database or real media transport.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

class Track extends EventTarget {
  constructor() { super(); this.enabled = true; this.readyState = 'live'; }
  stop() { this.readyState = 'ended'; }
  lose() { this.stop(); this.dispatchEvent(new Event('ended')); }
}
const capture = () => {
  const track = new Track();
  return { track, getTracks: () => [track], getAudioTracks: () => [track] };
};
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};
function setup(getUserMedia = async () => capture()) {
  const calls = [];
  const context = vm.createContext({ navigator: { mediaDevices: { getUserMedia: (...args) => {
    calls.push(args); return getUserMedia(...args);
  } } }, console });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../static/streams/microphone.js'), 'utf8'), context);
  const ui = { button: {}, status: {}, error: {} };
  context.ui = ui;
  const mic = vm.runInContext('new MicrophoneController(ui)', context);
  return { mic, calls, ui, context };
}
function peer() {
  const sender = { track: null, async replaceTrack(track) { this.track = track; } };
  const channel = { readyState: 'open', sent: [], send(message) { this.sent.push(JSON.parse(message)); }, close() {} };
  const pc = { sender, channel, connectionState: 'connected', addTransceiver(kind, options) {
    assert.equal(kind, 'audio'); assert.equal(options.direction, 'sendonly');
    return { sender };
  }, createDataChannel(label) { assert.equal(label, 'commentary'); return channel; } };
  return pc;
}
const flush = () => new Promise(resolve => setImmediate(resolve));

test('begin and viewer connection never request microphone; enable before begin is ignored', async () => {
  const { mic, calls, ui } = setup();
  await mic.enable();
  mic.begin();
  const pc = peer(); await mic.addPeer(pc, {});
  assert.equal(calls.length, 0);
  assert.equal(pc.sender.track, null);
  assert.equal(ui.status.textContent, 'Microphone off');
  assert.equal(pc.channel.sent.at(-1).available, false);
});

test('explicit enable attaches the same audio track to existing and later viewers', async () => {
  const { mic, calls } = setup(); mic.begin();
  const first = peer(); await mic.addPeer(first, {});
  await mic.enable();
  const later = peer(); await mic.addPeer(later, {});
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0].audio, true);
  assert.equal(calls[0][0].video, false);
  assert.equal(first.sender.track, later.sender.track);
  assert.equal(first.sender.track.readyState, 'live');
  assert.equal(first.channel.sent.at(-1).available, true);
});

test('mute silences shared track including late joiners; unmute does not reacquire', async () => {
  const { mic, calls, ui } = setup(); mic.begin(); await mic.enable();
  mic.toggleMute();
  const pc = peer(); await mic.addPeer(pc, {});
  assert.equal(pc.sender.track.enabled, false);
  assert.equal(ui.status.textContent, 'Muted');
  assert.equal(ui.button.textContent, 'Unmute microphone');
  assert.equal(pc.channel.sent.at(-1).available, true);
  mic.toggleMute();
  assert.equal(pc.sender.track.enabled, true);
  assert.equal(calls.length, 1);
});

for (const name of ['NotAllowedError', 'NotFoundError', 'NotReadableError', 'AbortError']) {
  test(`${name} preserves active video lifecycle and permits explicit retry`, async () => {
    let deny = true;
    const { mic, ui, calls } = setup(async () => {
      if (deny) throw Object.assign(new Error('failure'), { name });
      return capture();
    });
    mic.begin(); await mic.enable();
    assert.equal(mic.active, true);
    assert.equal(ui.status.textContent, 'Microphone unavailable');
    assert.equal(ui.button.textContent, 'Retry microphone');
    assert.equal(ui.error.hidden, false);
    await flush(); assert.equal(calls.length, 1);
    deny = false; await mic.enable();
    assert.equal(ui.status.textContent, 'Microphone on');
    assert.equal(calls.length, 2);
  });
}

test('unsupported capture explains fallback without ending broadcast', async () => {
  const { mic, context, ui } = setup();
  context.navigator.mediaDevices = undefined;
  mic.begin(); await mic.enable();
  assert.equal(mic.active, true);
  assert.equal(ui.status.textContent, 'Microphone unavailable');
  assert.match(ui.error.textContent, /support|secure/i);
});

test('duplicate clicks while permission is pending create one request', async () => {
  const pending = deferred(); const { mic, calls, ui } = setup(() => pending.promise);
  mic.begin(); const enabling = mic.enable(); await mic.enable();
  assert.equal(calls.length, 1); assert.equal(ui.button.disabled, true);
  pending.resolve(capture()); await enabling;
  assert.equal(ui.button.disabled, false);
});

test('grant after stop releases capture without activating commentary', async () => {
  const pending = deferred(); const { mic, ui } = setup(() => pending.promise);
  mic.begin(); const enabling = mic.enable(); mic.stop();
  const late = capture(); pending.resolve(late); await enabling;
  assert.equal(late.track.readyState, 'ended');
  assert.equal(mic.active, false);
  assert.equal(ui.status.textContent, 'Microphone off');
});

test('an obsolete grant cannot enable a new sharing session or clear its state', async () => {
  const pending = deferred(); const { mic, calls, ui } = setup(() => pending.promise);
  mic.begin(); const enabling = mic.enable(); mic.stop(); mic.begin();
  await mic.enable(); assert.equal(calls.length, 1);
  const late = capture(); pending.resolve(late); await enabling;
  assert.equal(late.track.readyState, 'ended');
  assert.equal(mic.active, true);
  assert.equal(ui.status.textContent, 'Microphone off');
  assert.equal(ui.button.disabled, false);
});

test('stop while muted releases capture and resets defaults', async () => {
  const input = capture(); const { mic, ui } = setup(async () => input);
  mic.begin(); await mic.enable(); mic.toggleMute(); mic.stop();
  assert.equal(input.track.readyState, 'ended');
  mic.begin(); assert.equal(ui.status.textContent, 'Microphone off');
});

test('device loss while muted detaches audio, remains unavailable and does not retry', async () => {
  const input = capture(); const { mic, ui, calls } = setup(async () => input);
  mic.begin(); const pc = peer(); await mic.addPeer(pc, {});
  await mic.enable(); mic.toggleMute(); input.track.lose(); await flush();
  assert.equal(mic.active, true);
  assert.equal(pc.sender.track, null);
  assert.equal(pc.channel.sent.at(-1).available, false);
  assert.equal(ui.status.textContent, 'Microphone unavailable');
  assert.equal(calls.length, 1);
});

test('data-channel open sends the current snapshot, including a muted microphone', async () => {
  const { mic } = setup(); mic.begin();
  const pc = peer(); pc.channel.readyState = 'connecting'; await mic.addPeer(pc, {});
  await mic.enable(); mic.toggleMute();
  pc.channel.readyState = 'open'; pc.channel.onopen(); await flush();
  assert.equal(pc.channel.sent.at(-1).available, true);
  assert.equal(pc.sender.track.enabled, false);
});

test('ordered replacement prevents an older attachment winning over stop', async () => {
  const { mic } = setup(); mic.begin(); const pc = peer(); await mic.addPeer(pc, {});
  const replace = deferred();
  pc.sender.replaceTrack = async track => { if (track) await replace.promise; pc.sender.track = track; };
  const enabling = mic.enable(); await flush(); mic.stop(); replace.resolve();
  await enabling; await flush();
  assert.equal(pc.sender.track, null);
  assert.equal(pc.channel.sent.at(-1).available, false);
});

test('mute remains usable while a slow viewer is attaching the captured microphone', async () => {
  const { mic, ui, calls } = setup(); mic.begin();
  const ready = peer(); const slow = peer();
  await mic.addPeer(ready, {}); await mic.addPeer(slow, {});
  const attachment = deferred();
  slow.sender.replaceTrack = async track => {
    if (track) await attachment.promise;
    slow.sender.track = track;
  };
  const enabling = mic.enable(); await flush();
  assert.equal(ready.sender.track.readyState, 'live');
  assert.equal(ui.button.textContent, 'Mute microphone');
  assert.equal(ui.button.disabled, false, 'live capture must be immediately mutable');
  for (let i = 0; i < 21; i++) mic.toggleMute();
  assert.equal(ready.sender.track.enabled, false);
  attachment.resolve(); await enabling;
  assert.equal(slow.sender.track.enabled, false);
  assert.equal(calls.length, 1);
  mic.stop(); assert.equal(ready.sender.track.readyState, 'ended');
});
