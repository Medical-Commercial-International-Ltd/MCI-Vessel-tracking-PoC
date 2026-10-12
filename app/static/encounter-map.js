(() => {
  const container = document.getElementById('encounter-map');
  const payload = document.getElementById('map-data');
  if (!container || !payload) return;
  const status = document.querySelector('[data-map-status]');
  const controls = document.querySelector('[data-map-controls]');
  const timeline = document.querySelector('[data-map-timeline]');
  const slider = document.querySelector('[data-map-time]');
  const selector = document.querySelector('[data-map-event]');
  const basemapNote = document.querySelector('[data-map-basemap]');
  const playButton = document.querySelector('[data-map-play]');
  const speedControl = document.querySelector('[data-map-speed]');
  const imageryControl = document.querySelector('[data-map-imagery]');
  const imageryNote = document.querySelector('[data-map-imagery-note]');
  const details = document.querySelector('[data-map-details]');
  const satelliteRetry = document.querySelector('[data-map-satellite-retry]');
  const colors = { vessel: '#07877f', gaps: '#07877f', storm: '#ea671e', 34: '#e6b437', 50: '#ef7b2d', 64: '#c93f4d' };
  const fail = (message) => {
    container.replaceChildren(); container.classList.add('encounter-map--error');
    container.textContent = message; status.textContent = message;
    controls.disabled = true; timeline.hidden = true;
  };
  const valid = (point) => Array.isArray(point) && point.length === 2 && point.every(Number.isFinite)
    && Math.abs(point[0]) <= 180 && Math.abs(point[1]) <= 90;
  const latLng = (point) => [point[1], point[0]];
  const utc = (value) => new Date(value).toLocaleString('en-GB', { timeZone: 'UTC' }) + ' UTC';
  let data;
  try { data = JSON.parse(payload.textContent); } catch (_) { fail('Encounter map data could not be read.'); return; }
  const events = (data.events || []).filter((event) => valid(event.vessel) && valid(event.storm));
  if (!events.length) { fail('No valid encounter positions are available.'); return; }
  if (!window.L) { fail('The map could not load. Refresh the page to try again.'); return; }

  function start() {
    const map = L.map(container, { zoomControl: true, scrollWheelZoom: false }).setView(latLng(events[0].vessel), 7);
    L.tileLayer(data.tileUrl, { maxZoom: 19, attribution: data.attribution }).addTo(map)
      .on('tileerror', () => { basemapNote.hidden = false; });
    [34, 50, 64].forEach((speed, index) => { map.createPane('wind' + speed).style.zIndex = 320 + index * 10; });
    const satellitePane = map.createPane('satelliteImagery');
    satellitePane.style.zIndex = 250; satellitePane.style.pointerEvents = 'none';
    let selected, frame, closestIndex = 0, animation = null, playTime = 0, previousTick = null, lastDraw = 0;
    let routes = [], wind = [], samples = [], connection;
    const markerCache = {};
    let satellitePlayer = null;
    const visible = (layer) => document.querySelector(`[data-map-layer="${layer}"]`).checked;
    const content = (title, text) => {
      const node = document.createElement('div');
      const heading = document.createElement('strong'); const detail = document.createElement('p');
      heading.textContent = title; detail.textContent = text; node.append(heading, detail); return node;
    };
    const mark = (point, title, kind, text) => {
      let marker = markerCache[kind];
      if (marker) {
        marker.setLatLng(latLng(point)).addTo(map);
        if (marker.playbackArrow) marker.playbackArrow.style.transform = `rotate(${frame.vesselHeadingDeg || 0}deg)`;
      } else if (kind === 'vessel') {
        const arrow = document.createElement('span');
        arrow.textContent = '▲'; arrow.style.transform = `rotate(${frame.vesselHeadingDeg || 0}deg)`;
        const icon = L.divIcon({ html: arrow, className: 'map-vessel-icon', iconSize: [28, 28], iconAnchor: [14, 14] });
        marker = L.marker(latLng(point), { icon, title }).addTo(map);
        marker.playbackArrow = arrow;
      } else marker = L.circleMarker(latLng(point), { radius: 10,
        color: '#fff', weight: 3, fillColor: colors[kind], fillOpacity: 1 }).addTo(map);
      marker.bindTooltip(title).bindPopup(content(title, text));
      if (!markerCache[kind]) markerCache[kind] = marker;
    };
    const clearFrame = () => {
      wind.forEach((overlay) => overlay.remove()); wind = [];
      if (connection) connection.remove(); map.closePopup();
    };
    const route = (points, layer) => {
      const path = points.filter(valid).map(latLng);
      if (path.length < 2) return;
      const overlay = L.polyline(path, { color: colors[layer], weight: layer === 'gaps' ? 2 : layer === 'vessel' ? 3 : 4,
        dashArray: layer === 'gaps' ? '6 7' : null, opacity: 0.85 });
      if (visible(layer)) overlay.addTo(map);
      overlay.bindTooltip(layer === 'gaps' ? 'Estimated route across missing track data (playback only)'
        : layer === 'vessel' ? 'Cached vessel track' : selected.name + ' NOAA storm track');
      routes.push({ overlay, layer });
    };
    const updateImagery = () => {
      const source = imageryControl.value;
      if (satelliteRetry) satelliteRetry.hidden = source !== 'goes';
      if (source === 'goes') {
        imageryNote.hidden = false;
        if (selected.synthetic || !selected.satelliteManifestUrl) {
          imageryNote.textContent = 'Historical GOES imagery requires a real storm encounter.'; return;
        }
        if (!satellitePlayer) {
          satellitePlayer = new window.MciSatellitePlayback({ map, leaflet: L, manifestUrl: selected.satelliteManifestUrl,
            onStatus: (message) => { imageryNote.textContent = message; } });
        }
        satellitePlayer.ensure(Date.parse(frame.timestamp)); return;
      }
      if (satellitePlayer) { satellitePlayer.destroy(); satellitePlayer = null; }
      imageryNote.hidden = true;
      imageryNote.textContent = '';
    };
    const positionText = (point) => valid(point) ? `${point[1].toFixed(4)}°, ${point[0].toFixed(4)}°` : 'Unavailable (track gap)';
    const separation = (a, b) => {
      const radians = Math.PI / 180;
      const value = Math.sin((b[1] - a[1]) * radians / 2) ** 2
        + Math.cos(a[1] * radians) * Math.cos(b[1] * radians) * Math.sin((b[0] - a[0]) * radians / 2) ** 2;
      return 6880.13 * Math.asin(Math.sqrt(Math.min(1, value)));
    };
    const playbackVessel = (timestamp) => {
      const points = selected.vesselPlaybackPoints || [];
      if (!points.length) return null;
      if (timestamp < Date.parse(points[0].timestamp) || timestamp > Date.parse(points[points.length - 1].timestamp)) {
        return { vessel: null, vesselGapInterpolated: false };
      }
      let low = 0, high = points.length - 1;
      while (low < high) { const middle = Math.ceil((low + high) / 2);
        if (Date.parse(points[middle].timestamp) <= timestamp) low = middle; else high = middle - 1; }
      const left = points[low], right = points[Math.min(low + 1, points.length - 1)];
      const duration = Date.parse(right.timestamp) - Date.parse(left.timestamp);
      const fraction = duration ? (timestamp - Date.parse(left.timestamp)) / duration : 0;
      const gap = fraction > 0 && left.gapToNext;
      return { vessel: gap && !visible('gaps') ? null : interpolateCoordinates(left.coordinates, right.coordinates, fraction),
        vesselGapInterpolated: gap && visible('gaps'), vesselSpeedKt: left.speedKt, vesselHeadingDeg: left.headingDeg };
    };
    const drawFrame = (animatedFrame = null) => {
      clearFrame();
      frame = animatedFrame || (selected.frames.length ? selected.frames[Number(slider.value)] : {
        timestamp: selected.timestamp, vessel: selected.vessel, storm: selected.storm, windSectors: [] });
      const playback = playbackVessel(Date.parse(frame.timestamp));
      if (playback) frame = { ...frame, ...playback };
      if (valid(frame.vessel)) mark(frame.vessel, frame.vesselGapInterpolated ? 'Estimated vessel position (data gap)' : 'Vessel position',
        'vessel', utc(frame.timestamp) + (frame.vesselGapInterpolated ? ' · Gap interpolation for playback only' : ' · Estimated AIS track position'));
      else if (markerCache.vessel) markerCache.vessel.remove();
      if (valid(frame.storm)) mark(frame.storm, selected.name, 'storm', utc(frame.timestamp) + (Number.isFinite(frame.windKt) ? ` · ${frame.status} · ${frame.windKt} kt` : ''));
      else if (markerCache.storm) markerCache.storm.remove();
      if (valid(frame.vessel) && valid(frame.storm)) connection = L.polyline([latLng(frame.vessel), latLng(frame.storm)],
        { color: '#596d7c', weight: 2, opacity: 0.6, dashArray: '5 7' }).addTo(map);
      (frame.windSectors || []).forEach((sector) => {
        const polygon = L.polygon(sector.coordinates.filter(valid).map(latLng), {
          pane: 'wind' + sector.speedKt, color: colors[sector.speedKt], opacity: 0.65, weight: 1,
          fillColor: colors[sector.speedKt], fillOpacity: 0.15 });
        polygon.bindPopup(content(selected.name, `${sector.speedKt} kt reported wind radius: ${sector.radiusNm.toFixed(1)} nm · ${utc(frame.timestamp)}`));
        if (visible(sector.speedKt)) polygon.addTo(map);
        wind.push(polygon); polygon.speedKt = sector.speedKt;
      });
      status.textContent = `${selected.name} · ${utc(frame.timestamp)}${Number.isFinite(frame.windKt) ? ` · ${frame.windKt} kt` : ''}`
        + (!frame.vessel ? ' · Vessel position unavailable at this time' : '')
        + (frame.vesselGapInterpolated ? ' · Vessel route estimated across missing data (playback only)' : '')
        + (!valid(frame.storm) ? ' · Storm position unavailable at this time' : '')
        + (frame.missingRadii ? ' · Some wind radii are unknown' : '')
        + (selected.synthetic ? ' · Synthetic demonstration positions' : '')
        + (frame.timestamp === selected.timestamp ? ` · ${selected.distanceNm} nm closest approach` : '');
      details.replaceChildren();
      const values = [ [frame.vesselGapInterpolated ? 'Vessel position (gap estimate)' : 'Vessel position', positionText(frame.vessel)], ['Storm centre', positionText(frame.storm)],
        ['Estimated vessel speed / heading', frame.vesselSpeedKt !== null && frame.vesselSpeedKt !== undefined && frame.vessel
          ? `${frame.vesselSpeedKt.toFixed(1)} kt / ${Math.round(frame.vesselHeadingDeg || 0)}°` : 'Unavailable'],
        ['Centre separation', valid(frame.vessel) && valid(frame.storm) ? separation(frame.vessel, frame.storm).toFixed(1) + ' nm' : 'Unavailable'] ];
      if (selected.vesselSampleCount) values.push(['Track samples', `${selected.vesselSamples.length.toLocaleString()} displayed / ${selected.vesselSampleCount.toLocaleString()} available`]);
      values.forEach(([label, value]) => {
        const cell = document.createElement('div'), term = document.createElement('dt'), description = document.createElement('dd');
        term.textContent = label; description.textContent = value; cell.append(term, description); details.append(cell);
      });
      updateImagery();
    };
    const fit = (fullTrack = false) => {
      const points = [selected.vessel, selected.storm];
      if (fullTrack) points.push(...selected.stormTrack.map((point) => point.coordinates));
      else points.push(...selected.vesselTracks.flat(), ...selected.frames.map((item) => item.storm),
        ...(frame.windSectors || []).flatMap((sector) => sector.coordinates));
      map.fitBounds(L.latLngBounds(points.filter(valid).map(latLng)), { padding: [30, 30], maxZoom: 13 });
    };
    const choose = () => {
      pause();
      if (satellitePlayer) { satellitePlayer.destroy(); satellitePlayer = null; }
      routes.forEach(({ overlay }) => overlay.remove()); routes = [];
      samples.forEach((point) => point.remove()); samples = [];
      selected = events[Number(selector.value)];
      (selected.vesselSamples || []).forEach((point) => {
        const marker = L.circleMarker(latLng(point.coordinates), { radius: 3, color: colors.vessel, weight: 1, fillOpacity: 0.6 })
          .bindPopup(content('Derived track sample', utc(point.timestamp) + ' · ' + positionText(point.coordinates)));
        if (visible('samples')) marker.addTo(map);
        samples.push(marker);
      });
      selected.vesselTracks.forEach((points) => route(points, 'vessel'));
      (selected.vesselGapTracks || []).forEach((points) => route(points, 'gaps'));
      let part = [];
      selected.stormTrack.forEach((point, index) => {
        if (index && new Date(point.timestamp) - new Date(selected.stormTrack[index - 1].timestamp) > 12 * 3600000) {
          route(part, 'storm'); part = [];
        }
        part.push(point.coordinates);
      });
      route(part, 'storm');
      closestIndex = Math.max(0, selected.frames.findIndex((item) => item.timestamp === selected.timestamp));
      slider.max = Math.max(0, selected.frames.length - 1); slider.value = closestIndex;
      timeline.hidden = selected.frames.length < 2;
      drawFrame(); fit();
    };
    events.forEach((event, index) => {
      const option = document.createElement('option'); option.value = index;
      option.textContent = `${event.name} · ${event.stormId}`; selector.append(option);
    });
    const pause = () => {
      if (animation !== null) window.cancelAnimationFrame(animation);
      animation = null; previousTick = null; playButton.textContent = 'Play'; playButton.setAttribute('aria-pressed', 'false');
    };
    const interpolateCoordinates = (left, right, fraction) => [
      (left[0] + ((right[0] - left[0] + 540) % 360 - 180) * fraction + 540) % 360 - 180,
      left[1] + (right[1] - left[1]) * fraction ];
    const frameAt = (timestamp) => {
      const frames = selected.frames;
      let low = 0, high = frames.length - 1;
      while (low < high) { const middle = Math.ceil((low + high) / 2);
        if (Date.parse(frames[middle].timestamp) <= timestamp) low = middle; else high = middle - 1; }
      slider.value = low;
      const left = frames[low], right = frames[Math.min(low + 1, frames.length - 1)];
      const duration = Date.parse(right.timestamp) - Date.parse(left.timestamp);
      const fraction = duration ? Math.max(0, Math.min(1, (timestamp - Date.parse(left.timestamp)) / duration)) : 0;
      if (!fraction) return left;
      if (duration > 5 * 60000 + 1) return { ...left, timestamp: new Date(timestamp).toISOString(),
        storm: null, vessel: null, windKt: null, windSectors: [], missingRadii: true };
      // Never draw a moving vessel between unrelated tracks or across missing data.
      const contiguous = left.vessel && right.vessel && left.vesselPathId !== null
        && left.vesselPathId !== undefined && left.vesselPathId === right.vesselPathId;
      const rightSectors = new Map((right.windSectors || []).map((sector) => [sector.speedKt + ':' + sector.quadrant, sector]));
      const sectors = (left.windSectors || []).flatMap((sector) => {
        const next = rightSectors.get(sector.speedKt + ':' + sector.quadrant);
        if (!next || next.coordinates.length !== sector.coordinates.length) return [];
        return [{ ...sector, radiusNm: sector.radiusNm + (next.radiusNm - sector.radiusNm) * fraction,
          coordinates: sector.coordinates.map((point, index) => interpolateCoordinates(point, next.coordinates[index], fraction)) }];
      });
      return { ...left, timestamp: new Date(timestamp).toISOString(), storm: interpolateCoordinates(left.storm, right.storm, fraction),
        vessel: contiguous ? interpolateCoordinates(left.vessel, right.vessel, fraction) : null,
        windKt: Math.round(left.windKt + (right.windKt - left.windKt) * fraction), windSectors: sectors,
        missingRadii: left.missingRadii || right.missingRadii };
    };
    const tick = (now) => {
      if (document.hidden) { pause(); return; }
      const elapsed = previousTick !== null ? Math.min(now - previousTick, 250) * Number(speedControl.value) * 60 : 0;
      previousTick = now;
      const end = Date.parse(selected.frames[selected.frames.length - 1].timestamp);
      const nextTime = Math.min(playTime + elapsed, end);
      if (imageryControl.value === 'goes' && satellitePlayer && !satellitePlayer.ensure(nextTime)) {
        animation = window.requestAnimationFrame(tick); return;
      }
      playTime = nextTime;
      if (now - lastDraw >= 50 || playTime === end) { drawFrame(frameAt(playTime)); lastDraw = now; }
      if (playTime === end) { pause(); return; }
      animation = window.requestAnimationFrame(tick);
    };
    playButton.addEventListener('click', () => {
      if (animation !== null) { pause(); return; }
      const atEnd = Number(slider.value) >= selected.frames.length - 1;
      if (atEnd) slider.value = 0;
      playTime = Date.parse(atEnd ? selected.frames[0].timestamp : frame.timestamp); previousTick = null; lastDraw = 0;
      playButton.textContent = 'Pause'; playButton.setAttribute('aria-pressed', 'true');
      animation = window.requestAnimationFrame(tick);
    });
    selector.addEventListener('change', choose); slider.addEventListener('input', () => { pause(); drawFrame(); });
    imageryControl.addEventListener('change', () => {
      if (imageryControl.value === 'goes') speedControl.value = '10';
      updateImagery();
    });
    if (satelliteRetry) satelliteRetry.addEventListener('click', () => { if (satellitePlayer) satellitePlayer.retry(); });
    document.querySelector('[data-map-closest]').addEventListener('click', () => { pause(); slider.value = closestIndex; drawFrame(); fit(); });
    document.querySelector('[data-map-fit]').addEventListener('click', () => fit());
    document.querySelector('[data-map-all]').addEventListener('click', () => fit(true));
    document.querySelectorAll('[data-map-layer]').forEach((checkbox) => checkbox.addEventListener('change', () => {
      routes.forEach(({ overlay, layer }) => visible(layer) ? overlay.addTo(map) : overlay.remove());
      wind.forEach((overlay) => visible(overlay.speedKt) ? overlay.addTo(map) : overlay.remove());
      samples.forEach((point) => visible('samples') ? point.addTo(map) : point.remove());
      drawFrame(frame);
    }));
    document.addEventListener('visibilitychange', () => { if (document.hidden) pause(); });
    window.addEventListener('pagehide', pause);
    window.addEventListener('pagehide', () => { if (satellitePlayer) satellitePlayer.destroy(); });
    controls.disabled = false; choose();
  }
  try { start(); } catch (_) { fail('The encounter map could not be displayed. Refresh the page to try again.'); }
})();
