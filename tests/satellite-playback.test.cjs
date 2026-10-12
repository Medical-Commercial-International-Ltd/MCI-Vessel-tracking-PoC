const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const script = fs.readFileSync('app/static/satellite-playback.js', 'utf8');
const START = Date.parse('2025-09-30T12:00:00Z');
const flush = async () => { for (let i = 0; i < 5; i++) await new Promise(setImmediate); };

function setup(options = {}) {
  const requests = [], statuses = [], overlays = [], revoked = [];
  const frames = Array.from({ length: 20 }, (_, index) => ({
    requestedAt: new Date(START + index * 600000).toISOString(), url: '/api/satellite/a/b/image?index=' + index,
  }));
  const manifest = { frames, bounds: [-80,25,-65,38] };
  let release;
  const wait = options.hold ? new Promise((resolve) => { release = resolve; }) : Promise.resolve();
  const fetch = async (url) => {
    requests.push(url);
    if (url.endsWith('/manifest')) return { ok: true, json: async () => manifest };
    await wait;
    const index = Number(url.split('index=')[1]);
    const acquired = options.stale ? '2026-09-30T12:00:00Z' : frames[index].requestedAt;
    return { ok: true, headers: { get: (key) => ({ 'X-Satellite-Acquired-At': acquired,
      'X-Satellite-Acquisition-End': new Date(Date.parse(acquired) + 540000).toISOString(),
      'X-Satellite-Name': 'GOES-19' })[key] }, blob: async () => ({ type: 'image/png' }) };
  };
  const L = { imageOverlay: (url, bounds, options) => {
    const overlay = { url, bounds, options, listeners: {}, on(name, handler) { this.listeners[name] = handler; return this; },
      addTo() { this.listeners.load(); return this; }, setOpacity(value) { this.opacity = value; }, remove() { this.removed = true; } };
    overlays.push(overlay); return overlay;
  } };
  let sequence = 0;
  const window = { setTimeout: () => 1, clearTimeout() {} };
  const URL = { createObjectURL: () => 'blob:' + (++sequence), revokeObjectURL: (url) => revoked.push(url) };
  class Image { async decode() {} }
  vm.runInNewContext(script, { window, fetch, AbortController, Image, URL, Date, Map, Set });
  const player = new window.MciSatellitePlayback({ map: {}, leaflet: L, manifestUrl: '/api/satellite/a/b/manifest',
    onStatus: (text) => statuses.push(text) });
  return { player, requests, statuses, overlays, revoked, release };
}

test('On-demand buffering waits, limits prefetch and reuses decoded images', async () => {
  const { player, requests, overlays, statuses } = setup({ hold: true });
  assert.equal(player.ensure(START), false);
  await flush();
  assert.equal(requests.length, 3); // one manifest and two in-flight images, not the whole encounter
  assert.equal(player.ensure(START), false);
  player.destroy();
  assert.equal(overlays.length, 0);
  assert.ok(statuses.some((text) => /Buffering/.test(text)));
});

test('Loaded frames carry actual acquisition times and are reused', async () => {
  const { player, requests, overlays, statuses } = setup();
  player.ensure(START); await flush();
  assert.equal(player.ensure(START + 120000), true);
  assert.equal(requests.length, 5); // manifest plus current and next three images
  assert.equal(overlays.length, 1);
  assert.equal(overlays[0].options.pane, 'satelliteImagery'); // imagery stays below routes and wind polygons
  assert.match(statuses.at(-1), /GOES-19.*2025-09-30T12:00:00/);
  player.ensure(START + 600000); await flush();
  assert.equal(overlays.length, 2);
  assert.equal(overlays[0].opacity, 0);
  player.destroy();
});

test('Provider frames with a wrong year are rejected rather than substituted', async () => {
  const { player, statuses, overlays } = setup({ stale: true });
  player.ensure(START); await flush();
  assert.equal(player.ensure(START), true);
  assert.equal(overlays.length, 0);
  assert.match(statuses.at(-1), /timestamp does not match/);
  player.destroy();
});

test('Destroying an encounter prevents a late image from reappearing', async () => {
  const { player, release, overlays, revoked } = setup({ hold: true });
  player.ensure(START); await flush(); player.destroy(); release(); await flush();
  assert.equal(overlays.length, 0);
  assert.ok(revoked.length > 0);
});

test('Browser image cache remains bounded during long playback', async () => {
  const { player, revoked } = setup();
  player.ensure(START); await flush();
  for (let index = 1; index < 18; index++) { player.ensure(START + index*600000); await flush(); }
  assert.ok(player.cache.size <= 12);
  assert.ok(revoked.length > 0);
  player.destroy();
});
