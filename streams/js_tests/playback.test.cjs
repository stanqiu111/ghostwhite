// Playback-policy simulations; native playback is covered by the browser harness.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

class Element extends EventTarget {
  constructor() { super(); this.hidden = true; this.dataset = {}; }
  setAttribute(name, value) { this[name] = value; }
}
function setup(play = async () => {}) {
  const video = new Element();
  Object.assign(video, { srcObject: {}, muted: true, volume: 1, play() { return play(this); } });
  const ui = { group: new Element(), slider: new Element(), muteBtn: new Element(),
    enableBtn: new Element(), status: new Element() };
  const context = vm.createContext({ document: { addEventListener() {} }, video, ui, console });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../static/streams/player_controls.js'), 'utf8'), context);
  const playback = vm.runInContext('new StreamPlayback(video, ui)', context);
  return { playback, video, ui };
}
const flush = () => new Promise(resolve => setImmediate(resolve));

test('reserved audio without commentary keeps video silent and controls hidden', async () => {
  const { playback, video, ui } = setup(); await playback.update();
  assert.equal(video.muted, true);
  assert.equal(ui.group.hidden, true);
  assert.equal(ui.enableBtn.hidden, true);
});

test('commentary arriving after video exposes controls and attempts audible playback', async () => {
  const { video, ui } = setup();
  video.dataset.audioAvailable = '1'; video.dispatchEvent(new Event('commentarychange')); await flush();
  assert.equal(ui.group.hidden, false); assert.equal(video.muted, false);
});

test('autoplay denial preserves muted video with an explicit sound action', async () => {
  let blocked = true;
  const { video, ui } = setup(async video => {
    if (blocked && !video.muted) throw Object.assign(new Error('blocked'), { name: 'NotAllowedError' });
  });
  video.dataset.audioAvailable = '1'; video.dispatchEvent(new Event('commentarychange')); await flush();
  assert.equal(video.muted, true); assert.equal(ui.enableBtn.hidden, false);
  blocked = false; ui.enableBtn.dispatchEvent(new Event('click')); await flush();
  assert.equal(video.muted, false); assert.equal(ui.enableBtn.hidden, true);
});

test('viewer mute and volume survive microphone recovery and stream replacement', async () => {
  const { playback, video, ui } = setup(); video.dataset.audioAvailable = '1'; await playback.update();
  ui.slider.value = '0.35'; ui.slider.dispatchEvent(new Event('input')); await flush();
  ui.muteBtn.dispatchEvent(new Event('click')); await flush();
  video.dataset.audioAvailable = '0'; video.dispatchEvent(new Event('commentarychange'));
  video.srcObject = {}; video.dispatchEvent(new Event('streamchange'));
  video.dataset.audioAvailable = '1'; video.dispatchEvent(new Event('commentarychange')); await flush();
  assert.equal(video.muted, true); assert.equal(video.volume, 0.35);
  assert.equal(ui.muteBtn['aria-label'], 'Unmute');
  ui.muteBtn.dispatchEvent(new Event('click')); await flush();
  assert.equal(video.muted, false); assert.equal(video.volume, 0.35);
});

test('an old playback rejection cannot mute a newer successful user action', async () => {
  let reject;
  let first = true;
  const { video, ui } = setup(video => {
    if (first && !video.muted) {
      first = false;
      return new Promise((resolve, fail) => { reject = fail; });
    }
    return Promise.resolve();
  });
  video.dataset.audioAvailable = '1'; video.dispatchEvent(new Event('commentarychange')); await flush();
  ui.enableBtn.dispatchEvent(new Event('click')); await flush();
  reject(Object.assign(new Error('old failure'), { name: 'NotAllowedError' })); await flush();
  assert.equal(video.muted, false); assert.equal(ui.enableBtn.hidden, true);
});
