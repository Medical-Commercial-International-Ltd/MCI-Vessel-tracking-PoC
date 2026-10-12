/* On-demand frame fetching, bounded prefetch, and decoded-image buffering. */
(() => {
  class SatellitePlayback {
    constructor({ map, leaflet, manifestUrl, onStatus }) {
      this.map = map; this.L = leaflet; this.manifestUrl = manifestUrl; this.onStatus = onStatus;
      this.manifest = null; this.cache = new Map(); this.queue = []; this.active = 0;
      this.disposed = false; this.overlay = null; this.shown = -1; this.targetTime = 0; this.desired = -1;
      this.controllers = new Set(); this.loading = null; this.failure = null;
    }
    ensure(timestamp) {
      if (this.disposed) return false;
      this.targetTime = timestamp;
      if (!this.manifest) {
        if (this.failure) { this.onStatus(this.failure); return true; }
        if (!this.loading) this.loading = this.prepare();
        this.onStatus('Loading historical satellite frame catalogue…'); return false;
      }
      let low = 0, high = this.manifest.frames.length - 1;
      while (low < high) { const middle = Math.ceil((low + high) / 2);
        if (Date.parse(this.manifest.frames[middle].requestedAt) <= timestamp) low = middle; else high = middle - 1; }
      this.desired = low;
      this.queue = this.queue.filter((index) => index >= low && index < low + 4);
      for (let index = low; index < Math.min(low + 4, this.manifest.frames.length); index++) {
        if (!this.cache.has(index) && !this.queue.includes(index)) this.queue.push(index);
      }
      this.queue.sort((a, b) => a - b); this.pump();
      const entry = this.cache.get(low);
      if (entry?.state === 'ready') {
        this.show(low, entry);
        return true;
      }
      if (entry?.state === 'error') {
        if (this.overlay) this.overlay.remove();
        this.overlay = null; this.shown = -1;
        this.onStatus(`Satellite image unavailable for ${this.manifest.frames[low].requestedAt}. ${entry.message}`);
        return true; // Preserve a visible gap, never silently substitute a different date.
      }
      this.onStatus('Buffering historical satellite imagery; playback waits for the next image…'); return false;
    }
    async prepare() {
      const controller = new AbortController(); this.controllers.add(controller);
      try {
        const response = await fetch(this.manifestUrl, { credentials: 'same-origin', signal: controller.signal });
        if (!response.ok) throw new Error(await this.message(response));
        const manifest = await response.json();
        if (!manifest.frames?.length || !manifest.bounds || manifest.frames.some((frame) => !frame.url.startsWith('/api/satellite/'))) {
          throw new Error('Satellite catalogue is invalid');
        }
        if (this.disposed) return;
        this.manifest = manifest; this.ensure(this.targetTime);
      } catch (error) {
        if (!this.disposed) { this.failure = error.message; this.onStatus(`Satellite imagery unavailable: ${error.message}`); }
      } finally { this.controllers.delete(controller); }
    }
    async message(response) {
      try { const data = await response.json(); return data.detail || 'The imagery service could not complete the request'; }
      catch (_) { return 'The imagery service could not complete the request'; }
    }
    pump() {
      while (!this.disposed && this.active < 2 && this.queue.length) {
        const index = this.queue.shift();
        if (this.cache.has(index)) continue;
        this.cache.set(index, { state: 'loading' }); this.active++;
        this.load(index);
      }
    }
    async load(index) {
      const controller = new AbortController(); this.controllers.add(controller);
      const timeout = window.setTimeout(() => controller.abort(), 150000);
      let objectUrl = null;
      try {
        const response = await fetch(this.manifest.frames[index].url, { credentials: 'same-origin', signal: controller.signal });
        if (!response.ok) throw new Error(await this.message(response));
        const acquired = response.headers.get('X-Satellite-Acquired-At');
        const end = response.headers.get('X-Satellite-Acquisition-End');
        if (!acquired || !end || !Number.isFinite(Date.parse(acquired)) || !Number.isFinite(Date.parse(end))
            || Math.abs(Date.parse(acquired) - Date.parse(this.manifest.frames[index].requestedAt)) > 600000) {
          throw new Error('The returned satellite timestamp does not match the requested frame');
        }
        const blob = await response.blob();
        if (!blob.type.startsWith('image/')) throw new Error('The imagery service did not return an image');
        objectUrl = URL.createObjectURL(blob);
        const decoded = new Image(); decoded.src = objectUrl;
        await decoded.decode();
        if (this.disposed) { URL.revokeObjectURL(objectUrl); return; }
        this.cache.set(index, { state: 'ready', url: objectUrl, acquired, end,
          satellite: response.headers.get('X-Satellite-Name') || 'GOES' });
        objectUrl = null;
      } catch (error) {
        if (objectUrl) URL.revokeObjectURL(objectUrl);
        if (!this.disposed) this.cache.set(index, { state: 'error', message: error.message });
      } finally {
        window.clearTimeout(timeout); this.controllers.delete(controller); this.active--;
        if (!this.disposed) {
          if (this.desired === index) this.ensure(this.targetTime);
          this.trim(); this.pump();
        }
      }
    }
    show(index, entry) {
      if (this.shown === index) return;
      const previous = this.overlay;
      const bounds = this.manifest.bounds;
      const layer = this.L.imageOverlay(entry.url, [[bounds[1], bounds[0]], [bounds[3], bounds[2]]], {
        opacity: 0, pane: 'satelliteImagery', attribution: 'NOAA GOES infrared · acquisition times shown below', interactive: false,
      });
      this.overlay = layer; this.shown = index;
      layer.on('load', () => {
        if (this.disposed || this.overlay !== layer) { layer.remove(); return; }
        layer.setOpacity(0.9);
        if (previous) { previous.setOpacity(0); window.setTimeout(() => previous.remove(), 150); }
        this.onStatus(`${entry.satellite} C13 infrared · Acquired ${entry.acquired} to ${entry.end} · Approximately 2 km · Cold cloud tops are brighter`);
      }).on('error', () => {
        layer.remove(); if (previous) previous.remove();
        this.onStatus('Satellite image could not be displayed; the street map and tracking remain available.');
      }).addTo(this.map);
    }
    trim() {
      if (this.cache.size <= 12) return;
      for (const [index, entry] of this.cache) {
        if (this.cache.size <= 12) break;
        if (index === this.shown || index >= this.desired - 1 && index < this.desired + 4 || entry.state === 'loading') continue;
        if (entry.url) URL.revokeObjectURL(entry.url);
        this.cache.delete(index);
      }
    }
    destroy() {
      this.disposed = true;
      this.controllers.forEach((controller) => controller.abort());
      if (this.overlay) this.overlay.remove();
      this.cache.forEach((entry) => { if (entry.url) URL.revokeObjectURL(entry.url); });
      this.cache.clear(); this.queue = [];
    }
    retry() {
      if (this.disposed) return;
      if (this.failure) { this.failure = null; this.loading = null; }
      for (const [index, entry] of this.cache) { if (entry.state === 'error') this.cache.delete(index); }
      this.ensure(this.targetTime);
    }
  }
  window.MciSatellitePlayback = SatellitePlayback;
})();
