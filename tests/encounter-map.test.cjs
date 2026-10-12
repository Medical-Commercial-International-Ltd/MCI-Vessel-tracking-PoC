const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/encounter-map.js', 'utf8');

function setup(leafletAvailable = true, options = {}) {
  const created = { maps: [], lines: [], polygons: [], markers: [], requests: [] };
  const element = () => ({ children: [], listeners: {}, checked: true, value: '0', style: {},
    classList: { add() {} }, append(...items) { this.children.push(...items); },
    replaceChildren(...items) { this.children = items; },
    addEventListener(name, handler) { this.listeners[name] = handler; },
    setAttribute(name, value) { this[name] = value; } });
  const timestamp = '2025-07-01T00:00:00+00:00';
  const event = { id: 'one', name: 'Chantal', stormId: 'AL032025', vessel: [-80, 30],
    storm: [-81, 30], distanceNm: 52, timestamp, synthetic: false,
    vesselTracks: [[[-80, 30], [-79, 30]]],
    stormTrack: [{ coordinates: [-81, 30], timestamp },
      { coordinates: [-80, 31], timestamp: '2025-07-01T06:00:00+00:00' }],
    frames: [{ timestamp, vessel: [-80, 30], storm: [-81, 30], windKt: 40, status: 'TS',
      windSectors: [{ speedKt: 34, radiusNm: 50, coordinates: [[-81, 30], [-80, 30], [-81, 31], [-81, 30]] }] },
      { timestamp: '2025-07-01T00:05:00+00:00', vessel: null, storm: [-80, 31], windKt: 45,
        status: 'TS', windSectors: [], missingRadii: true }] };
  const nodes = Object.fromEntries(['encounter-map', 'map-data', 'controls', 'timeline', 'time', 'event',
    'status', 'closest', 'fit', 'all', 'basemap', 'play', 'speed', 'imagery', 'imagery-note', 'details'].map((key) => [key, element()]));
  nodes.speed.value = '30'; nodes.imagery.value = 'street';
  if (options.contiguous) {
    event.frames[0].vesselPathId = 'one';
    event.frames[1].vesselPathId = 'one';
    event.frames[1].vessel = [-79, 31];
  }
  if (options.nextDay) event.frames[1].timestamp = '2025-07-02T06:00:00+00:00';
  if (options.gapPlayback) {
    event.vesselPlaybackPoints = [
      { timestamp, coordinates: [-80,30], gapToNext: true, speedKt: 12, headingDeg: 45 },
      { timestamp: event.frames[1].timestamp, coordinates: [-79,31], gapToNext: false } ];
    event.vesselGapTracks = [[[-80,30],[-79,31]]];
  }
  nodes['map-data'].textContent = JSON.stringify({ events: [event], tileUrl: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', attribution: 'OpenStreetMap contributors' });
  const layers = Object.fromEntries(['vessel', 'gaps', 'storm', 'samples', '34', '50', '64'].map((name) => [name, element()]));
  class Overlay { constructor(options = {}) { Object.assign(this, options); this.listeners = {}; }
    setLatLng(position) { this.position = position; return this; }
    addTo(map) { this.map = map; return this; } remove() { this.map = null; return this; }
    bindTooltip(text) { this.tooltip = text; return this; } bindPopup(text) { this.popup = text; return this; }
    on(name, handler) { this.listeners[name] = handler; return this; } }
  class Map { constructor(options) { this.options = options; this.bounds = []; created.maps.push(this); }
    fitBounds(bounds) { this.bounds.push(bounds); }
    setView() { return this; } createPane() { return { style: {} }; } closePopup() {} }
  const L = {
    map: (node, options) => new Map(options),
    tileLayer: (url, options) => { const tile = new Overlay(options); tile.url = url; created.requests.push(tile); return tile; },
    polyline: (path, options) => { const line = new Overlay(options); line.path = path; created.lines.push(line); return line; },
    polygon: (path, options) => { const polygon = new Overlay(options); polygon.path = path; created.polygons.push(polygon); return polygon; },
    circleMarker: (position, options) => { const marker = new Overlay(options); marker.position = position; created.markers.push(marker); return marker; },
    marker: (position, options) => { const marker = new Overlay(options); marker.position = position; created.markers.push(marker); return marker; },
    divIcon: (options) => options,
    latLngBounds: (points) => points,
  };
  const document = { hidden: false, addEventListener() {}, getElementById: (id) => nodes[id], createElement: element,
    head: { append: (script) => created.requests.push(script) },
    querySelectorAll: () => Object.values(layers),
    querySelector: (selector) => {
      const layer = selector.match(/data-map-layer="([^"]+)"/);
      if (layer) return layers[layer[1]];
      const name = selector.match(/data-map-([^\]]+)/)[1];
      return nodes[name];
    } };
  let pending = null;
  const window = { L: leafletAvailable ? L : null, addEventListener() {},
    requestAnimationFrame: (callback) => { pending = callback; return 1; }, cancelAnimationFrame: () => { pending = null; } };
  vm.runInNewContext(source, { document, window, L, Date, Number, Math, URLSearchParams });
  const tick = (timestamp) => { const callback = pending; pending = null; if (callback) callback(timestamp); };
  return { nodes, layers, created, tick };
}

test('Missing local Leaflet assets show a clear failure without requesting tiles', () => {
  const { nodes, created } = setup(false);
  assert.match(nodes['encounter-map'].textContent, /could not load/);
  assert.equal(nodes.controls.disabled, true);
  assert.equal(created.maps.length, 0);
  assert.equal(created.requests.length, 0);
});

test('Playback moves both markers and stops when the user scrubs', () => {
  const { nodes, created, tick } = setup(true, { contiguous: true });
  nodes.play.listeners.click();
  assert.equal(nodes.play.textContent, 'Pause');
  tick(100); tick(160);
  const active = created.markers.filter((marker) => marker.map !== null);
  assert.equal(active.length, 2);
  assert.ok(active[0].position[1] > -80 && active[0].position[1] < -79);
  assert.ok(active[1].position[1] > -81 && active[1].position[1] < -80);
  nodes.time.listeners.input();
  assert.equal(nodes.play.textContent, 'Play');
});

test('Playback never connects a vessel across a missing track interval', () => {
  const { nodes, created, tick } = setup();
  nodes.play.listeners.click(); tick(100); tick(160);
  assert.equal(created.markers.filter((marker) => marker.map !== null).length, 1);
  assert.match(nodes.status.textContent, /Vessel position unavailable/);
});

test('Gap playback follows a labelled dashed route and can be disabled', () => {
  const { nodes, layers, created, tick } = setup(true, { gapPlayback: true });
  assert.ok(created.lines.some((line) => line.dashArray === '6 7'));
  nodes.play.listeners.click(); tick(100); tick(160);
  const active = created.markers.filter((marker) => marker.map !== null);
  assert.equal(active.length, 2);
  assert.ok(active[0].position[1] > -80 && active[0].position[1] < -79);
  assert.match(nodes.status.textContent, /route estimated across missing data/);
  assert.equal(created.markers.length, 2); // update existing markers instead of replacing their DOM nodes
  layers.gaps.checked = false; layers.gaps.listeners.change();
  assert.equal(created.markers.filter((marker) => marker.map !== null).length, 1);
  assert.match(nodes.status.textContent, /Vessel position unavailable/);
});

test('Playback hides positions across a missing storm interpolation interval', () => {
  const { nodes, created, tick } = setup(true, { contiguous: true, nextDay: true });
  nodes.play.listeners.click(); tick(100); tick(160);
  assert.equal(created.markers.filter((marker) => marker.map !== null).length, 0);
  assert.match(nodes.status.textContent, /Storm position unavailable/);
});

test('No-key Leaflet view draws tracks and wind areas; timeline does not invent vessel positions', async () => {
  const { nodes, layers, created } = setup();
  await new Promise(setImmediate);
  assert.equal(created.maps.length, 1);
  assert.equal(created.maps[0].options.zoomControl, true);
  assert.equal(nodes.controls.disabled, false);
  assert.equal(created.lines.length, 3); // vessel, storm, closest-approach connection
  assert.equal(created.polygons.length, 1);
  assert.equal(created.markers.length, 2);
  layers['34'].checked = false;
  layers['34'].listeners.change();
  assert.equal(created.polygons[0].map, null);
  nodes.time.value = '1';
  nodes.time.listeners.input();
  assert.match(nodes.status.textContent, /Vessel position unavailable/);
  assert.match(nodes.status.textContent, /wind radii are unknown/);
  assert.equal(created.markers.filter((marker) => marker.map !== null).length, 1);
  nodes.closest.listeners.click();
  assert.equal(nodes.time.value, 0);
  assert.match(nodes.status.textContent, /closest approach/);
  assert.equal(created.markers.filter((marker) => marker.map !== null).length, 2);
});

 test('Tile failures preserve interactive NOAA overlays and disclose missing background', () => {
  const { nodes, created } = setup();
  created.requests[0].listeners.tileerror();
  assert.equal(nodes.basemap.hidden, false);
  assert.equal(nodes.controls.disabled, false);
  assert.equal(created.markers.filter((marker) => marker.map !== null).length, 2);
  assert.match(created.requests[0].url, /^https:\/\/tile.openstreetmap.org\//);
  assert.match(created.requests[0].attribution, /OpenStreetMap/);
});
