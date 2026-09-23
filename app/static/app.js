(() => {
  const form = document.querySelector("[data-analysis-form]");
  const panel = document.querySelector("[data-processing-panel]");
  const message = document.querySelector("[data-processing-message]");

  if (form && panel) {
    form.addEventListener("submit", () => {
      panel.hidden = false;
      const button = form.querySelector("button[type='submit']");
      button.disabled = true;
      button.textContent = "Analysing…";
      const messages = [
        "Resolving vessel identity…",
        "Reviewing AIS track history…",
        "Matching named storm tracks…",
        "Calculating exposure score…",
      ];
      let index = 0;
      window.setInterval(() => {
        index = Math.min(index + 1, messages.length - 1);
        if (message) message.textContent = messages[index];
      }, 550);
    });
  }

  const mapElement = document.getElementById("encounter-map");
  const mapPayload = document.getElementById("map-data");
  if (mapElement && mapPayload) {
    renderEncounterMap(mapElement, mapPayload);
  }

  function renderEncounterMap(container, payload) {
    const svgNamespace = "http://www.w3.org/2000/svg";
    const width = 960;
    const height = 390;
    const domain = { minLon: -161, maxLon: -63, minLat: 16, maxLat: 51 };

    const makeSvg = (name, attributes = {}) => {
      const element = document.createElementNS(svgNamespace, name);
      Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
      return element;
    };

    const project = (coordinates) => {
      const longitude = Number(coordinates[0]);
      const latitude = Number(coordinates[1]);
      return [
        ((longitude - domain.minLon) / (domain.maxLon - domain.minLon)) * width,
        ((domain.maxLat - latitude) / (domain.maxLat - domain.minLat)) * height,
      ];
    };

    let parsed;
    try {
      parsed = JSON.parse(payload.textContent);
    } catch (_error) {
      container.textContent = "Encounter map data could not be read.";
      container.classList.add("encounter-map--error");
      return;
    }

    const data = parsed.filter((event) => {
      const coordinates = [...(event.vessel || []), ...(event.storm || [])];
      return coordinates.length === 4 && coordinates.every((value) => Number.isFinite(Number(value)));
    });
    if (!data.length) {
      container.textContent = "No valid encounter positions are available.";
      container.classList.add("encounter-map--error");
      return;
    }

    const svg = makeSvg("svg", {
      viewBox: `0 0 ${width} ${height}`,
      role: "img",
      "aria-label": `Encounter map showing ${data.length} storm encounter${data.length === 1 ? "" : "s"}`,
      preserveAspectRatio: "xMidYMid meet",
    });
    svg.appendChild(makeSvg("rect", { width, height, class: "map-ocean" }));

    [-150, -130, -110, -90, -70].forEach((longitude) => {
      const [x] = project([longitude, domain.minLat]);
      svg.appendChild(makeSvg("line", { x1: x, y1: 0, x2: x, y2: height, class: "map-gridline" }));
    });
    [20, 30, 40, 50].forEach((latitude) => {
      const [, y] = project([domain.minLon, latitude]);
      svg.appendChild(makeSvg("line", { x1: 0, y1: y, x2: width, y2: y, class: "map-gridline" }));
    });

    const mainland = [
      [-124.7, 48.5], [-123.5, 45.5], [-124.2, 42], [-122.5, 37.5],
      [-117.1, 32.5], [-110, 31.3], [-106.5, 31.8], [-103, 29.7],
      [-97, 25.9], [-90, 29], [-85, 29.7], [-81.3, 25.4],
      [-80, 32], [-75.5, 35.5], [-70, 41.8], [-69, 45],
      [-76, 45], [-82, 42], [-83, 46], [-95, 49], [-110, 49],
    ].map(project).map((point) => point.join(",")).join(" ");
    svg.appendChild(makeSvg("polygon", { points: mainland, class: "map-land" }));

    [[-159.5, 22], [-157.8, 21.2], [-156.3, 20.7], [-155.5, 19.6]].forEach((coordinates) => {
      const [cx, cy] = project(coordinates);
      svg.appendChild(makeSvg("circle", { cx, cy, r: 4, class: "map-land" }));
    });
    const [prX, prY] = project([-66.4, 18.2]);
    svg.appendChild(makeSvg("ellipse", { cx: prX, cy: prY, rx: 9, ry: 3, class: "map-land" }));

    const details = document.createElement("div");
    details.className = "map-details";
    details.setAttribute("aria-live", "polite");
    const detailsTitle = document.createElement("strong");
    const detailsText = document.createElement("span");
    details.append(detailsTitle, detailsText);

    const showDetails = (event, kind, coordinates) => {
      const longitude = Number(coordinates[0]);
      const latitude = Number(coordinates[1]);
      detailsTitle.textContent = kind === "vessel" ? "Vessel position" : event.name;
      detailsText.textContent = kind === "vessel"
        ? `${event.name} · ${latitude.toFixed(2)}°, ${longitude.toFixed(2)}°`
        : `${event.distanceNm} nm closest approach · ${latitude.toFixed(2)}°, ${longitude.toFixed(2)}°`;
    };

    data.forEach((event, index) => {
      const vessel = project(event.vessel);
      const storm = project(event.storm);
      svg.appendChild(makeSvg("line", {
        x1: vessel[0], y1: vessel[1], x2: storm[0], y2: storm[1], class: "map-connection",
      }));

      [["vessel", event.vessel, vessel], ["storm", event.storm, storm]].forEach(([kind, coordinates, point]) => {
        const marker = makeSvg("g", {
          class: `map-marker map-marker--${kind}`,
          role: "button",
          tabindex: "0",
          "aria-label": kind === "vessel" ? `Vessel position for ${event.name}` : `${event.name}, ${event.distanceNm} nautical miles`,
        });
        marker.appendChild(makeSvg("circle", { cx: point[0], cy: point[1], r: 13, class: "map-marker__halo" }));
        marker.appendChild(makeSvg("circle", { cx: point[0], cy: point[1], r: kind === "vessel" ? 7 : 8, class: "map-marker__point" }));
        const title = makeSvg("title");
        title.textContent = marker.getAttribute("aria-label");
        marker.appendChild(title);
        marker.addEventListener("click", () => showDetails(event, kind, coordinates));
        marker.addEventListener("focus", () => showDetails(event, kind, coordinates));
        marker.addEventListener("keydown", (keyboardEvent) => {
          if (keyboardEvent.key === "Enter" || keyboardEvent.key === " ") {
            keyboardEvent.preventDefault();
            showDetails(event, kind, coordinates);
          }
        });
        svg.appendChild(marker);
      });

      if (index === 0) showDetails(event, "storm", event.storm);
    });

    const legend = document.createElement("div");
    legend.className = "map-legend";
    legend.innerHTML = '<span><i class="map-key map-key--vessel"></i>Vessel</span><span><i class="map-key map-key--storm"></i>Storm</span>';
    container.replaceChildren(svg, legend, details);
  }
})();
