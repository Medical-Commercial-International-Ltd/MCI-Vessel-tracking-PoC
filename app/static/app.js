(() => {
  const revealEvidence = (hash) => {
    if (!hash || hash === '#') return;
    const target = document.getElementById(decodeURIComponent(hash.slice(1)));
    if (target instanceof HTMLDetailsElement) target.open = true;
  };
  document.querySelectorAll('a[href^="#"]').forEach(link => {
    link.addEventListener('click', () => revealEvidence(link.hash));
  });
  revealEvidence(location.hash);
  window.addEventListener('hashchange', () => revealEvidence(location.hash));
  const form = document.querySelector("[data-analysis-form]");
  const panel = document.querySelector("[data-processing-panel]");
  const message = document.querySelector("[data-processing-message]");
  const presetsElement = document.getElementById('storm-case-presets');
  if (form && presetsElement) {
    const presets = JSON.parse(presetsElement.textContent);
    const identifier = form.elements.identifier;
    const identifierType = form.elements.identifierType;
    const note = document.querySelector('[data-case-period-note]');
    let appliedKey = null;
    const originalDates = {from: form.elements.fromDate.value, to: form.elements.toDate.value,
      proximity: form.elements.stormProximityNm.value};
    let appliedValues = null;
    const applyCase = () => {
      const value = identifier.value.trim();
      const key = identifierType.value === 'IMO' ? 'imo' : 'mmsi';
      const selected = presets.find(item => item[key] === value);
      const currentKey = key + ':' + value;
      if (selected && appliedKey !== currentKey) {
        form.elements.fromDate.value = selected.from;
        form.elements.toDate.value = selected.to;
        form.elements.stormProximityNm.value = selected.proximityNm || 70;
        appliedValues = {from: selected.from, to: selected.to, proximity: String(selected.proximityNm || 70)};
        appliedKey = currentKey;
        note.textContent = selected.name + ': loaded the recorded case dates (' + selected.from + ' to ' + selected.to + '). You can change them. ' + selected.note;
        note.hidden = false;
      } else if (!selected) {
        if (appliedValues && form.elements.fromDate.value === appliedValues.from &&
            form.elements.toDate.value === appliedValues.to && form.elements.stormProximityNm.value === appliedValues.proximity) {
          form.elements.fromDate.value = originalDates.from;
          form.elements.toDate.value = originalDates.to;
          form.elements.stormProximityNm.value = originalDates.proximity;
        }
        appliedKey = null;
        appliedValues = null;
        note.hidden = true;
      }
    };
    identifier.addEventListener('input', applyCase);
    identifierType.addEventListener('change', applyCase);
  }

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

})();
