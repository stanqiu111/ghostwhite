const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

test('viewer signaling uses the home-node proxy and preserves credentials on our origin', async () => {
  const calls = [];
  const context = vm.createContext({ URLSearchParams, localStorage: { getItem: () => null },
    document: { cookie: 'csrftoken=csrf-test', getElementById: () => ({ dataset: { apiBase: '/api/remote-nodes/node/streams/room/' } }) },
    fetch: async (...args) => { calls.push(args); return { ok: true, status: 200, json: async () => ({ items: [] }) }; },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../static/streams/signaling.js'), 'utf8'), context);
  await vm.runInContext("postSignal('room', { kind: 'join', direction: 'to_streamer', peerId: 'viewer' })", context);
  await vm.runInContext("pollSignals('room', 'viewer', 'viewer')", context);
  assert.equal(calls[0][0], '/api/remote-nodes/node/streams/room/signals/');
  assert.equal(calls[0][1].credentials, 'same-origin');
  assert.equal(calls[0][1].headers['X-CSRFToken'], 'csrf-test');
  assert.equal(calls[1][0], '/api/remote-nodes/node/streams/room/signals/?role=viewer&peer_id=viewer');
  assert.equal(vm.runInContext("streamApiUrl('room', 'bullets/')", context), '/api/remote-nodes/node/streams/room/bullets/');
});

test('local endpoints remain unchanged and ICE configuration comes from the server', () => {
  let config;
  const context = vm.createContext({ document: { addEventListener() {}, getElementById: id =>
    id === 'streamIceConfig' ? config : null }, localStorage: { getItem: () => null } });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../static/streams/signaling.js'), 'utf8'), context);
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../static/streams/screenshare.js'), 'utf8'), context);
  assert.equal(vm.runInContext("streamApiUrl('room')", context), '/api/streams/room/');
  assert.equal(vm.runInContext('streamIceConfiguration().iceServers[0].urls', context), 'stun:stun.l.google.com:19302');
  config = { textContent: JSON.stringify({ iceServers: [{ urls: 'turn:relay.example', username: 'temporary', credential: 'test' }] }) };
  assert.equal(vm.runInContext('streamIceConfiguration().iceServers[0].urls', context), 'turn:relay.example');
});

function playerContext(ice = { iceServers: [] }) {
  const element = { textContent: JSON.stringify(ice) };
  const timers = new Map(); let timerId = 0;
  const peers = [], fetches = [];
  class Peer {
    constructor(config) { this.config = config; this.connectionState = 'new'; peers.push(this); }
    async setRemoteDescription(description) { this.remoteDescription = description; }
    async createAnswer() { return { type: 'answer', sdp: 'simulated' }; }
    async createOffer() { return { type: 'offer', sdp: 'simulated' }; }
    async setLocalDescription(description) { this.localDescription = description; }
    close() { this.connectionState = 'closed'; }
  }
  const video = Object.assign(new EventTarget(), { dataset: {}, srcObject: {} });
  const ui = { video, placeholder: { dataset: {} }, stateText: {}, retryBtn: {} };
  const fresh = { iceServers: [{ urls: 'turn:relay.example', username: 'renewed', credential: 'temporary' }], expiresAt: Date.now() / 1000 + 3600 };
  const context = vm.createContext({ ui, console, Event, URLSearchParams, RTCPeerConnection: Peer,
    RTCSessionDescription: function(value) { return value; },
    document: { addEventListener() {}, getElementById: () => element, cookie: '' },
    localStorage: { getItem: () => null }, crypto: { randomUUID: () => 'new-peer' },
    fetch: async (...args) => { fetches.push(args); return { ok: true, status: 200, json: async () => fresh }; },
    setTimeout: (callback, delay) => { timers.set(++timerId, { callback, delay }); return timerId; },
    clearTimeout: id => timers.delete(id), clearInterval() {},
    postSignal: async () => ({}),
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../static/streams/signaling.js'), 'utf8'), context);
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../static/streams/screenshare.js'), 'utf8'), context);
  vm.runInContext('postSignal = async () => ({}); player = new Player("room", ui); player.peerId = "original";', context);
  return { context, player: context.player, peers, timers, fetches, ui, element };
}

test('an old page refreshes TURN credentials before its next peer and renews before expiry', async () => {
  const { player, peers, fetches, timers } = playerContext({ iceServers: [], expiresAt: 1 });
  await player.handleOffer({ type: 'offer', sdp: 'simulated' });
  assert.equal(fetches[0][0], '/api/streams/ice/');
  assert.equal(fetches[0][1].credentials, 'same-origin');
  assert.equal(peers[0].config.iceServers[0].username, 'renewed');
  const timer = [...timers.values()][0];
  assert(timer.delay > 3500 * 1000 && timer.delay <= 3540 * 1000);
  timer.callback();
  assert.equal(peers[0].connectionState, 'closed');
  assert.equal(player.peerId, 'new-peer');
  assert.equal(player.state, 'waiting');
});

test('revoked access closes media and renewal timers; stale offers cannot reopen playback', async () => {
  const { player, peers, ui, timers, context } = playerContext({ iceServers: [], expiresAt: Date.now() / 1000 + 3600 });
  await player.handleOffer({ type: 'offer', sdp: 'simulated' });
  player.onAccessDenied();
  assert.equal(peers[0].connectionState, 'closed');
  assert.equal(player.stopped, true);
  assert.equal(ui.video.srcObject, null);
  assert.equal(ui.video.hidden, true);
  assert.equal(timers.size, 0);
  let sent = 0;
  context.postSignal = async () => { sent++; };
  peers[0].onicecandidate({ candidate: { toJSON: () => ({ candidate: 'stale' }) } });
  assert.equal(sent, 0);
  await player.handleOffer({ type: 'offer', sdp: 'stale' });
  assert.equal(peers.length, 1);
});

test('permission revoked while ICE refresh is pending cannot create a peer', async () => {
  const { player, peers, context } = playerContext({ iceServers: [], expiresAt: 1 });
  let release;
  context.fetch = () => new Promise(resolve => { release = resolve; });
  const offer = player.handleOffer({ type: 'offer', sdp: 'simulated' });
  player.onAccessDenied();
  release({ ok: true, status: 200, json: async () => ({ iceServers: [] }) });
  await offer;
  assert.equal(peers.length, 0);
});

test('host renews its earlier TURN allocation independently of a viewer credential', async () => {
  const { context, peers, timers } = playerContext({ iceServers: [], expiresAt: Date.now() / 1000 + 600 });
  const sent = [];
  context.postSignal = async (serial, message) => { sent.push(message); };
  context.MicrophoneController = class { async addPeer() {} removePeer() {} };
  const host = vm.runInContext('new Broadcaster("room", { microphone: {} })', context);
  host.active = true;
  host.media = { getVideoTracks: () => [] };
  await host.handleJoin('viewer');
  const timer = [...timers.values()][0];
  assert(timer.delay > 539000 && timer.delay <= 540000);
  timer.callback();
  assert.equal(peers[0].connectionState, 'closed');
  assert.equal(host.pcs.size, 0);
  assert.equal(host.active, true);
  assert.equal(sent.at(-1).kind, 'bye');
  assert.equal(sent.at(-1).peerId, 'viewer');
});
