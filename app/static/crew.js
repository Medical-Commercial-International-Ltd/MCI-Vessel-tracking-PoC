(() => {
  const form = document.querySelector('[data-crew-lookup]');
  if (!form) return;
  const samples = {
    maya: ['Maya', 'Patel', 'maya.patel@example.test'],
    alex: ['Alex', 'Morgan', 'alex.morgan@example.test'],
    missing: ['Jamie', 'Taylor', 'missing@example.test'],
    unavailable: ['Jamie', 'Taylor', 'unavailable@example.test'],
  };
  document.querySelectorAll('[data-crew-sample]').forEach(button => {
    button.addEventListener('click', () => {
      const sample = samples[button.dataset.crewSample];
      ['first_name', 'last_name', 'email'].forEach((key, i) => { form.elements[key].value = sample[i]; });
      form.elements.first_name.focus();
    });
  });
  const reset = () => {
    form.querySelector('[type="submit"]').disabled = false;
    form.querySelector('[data-crew-loading]').hidden = true;
    form.removeAttribute('aria-busy');
  };
  form.addEventListener('submit', () => {
    form.setAttribute('aria-busy', 'true');
    form.querySelector('[type="submit"]').disabled = true;
    form.querySelector('[data-crew-loading]').hidden = false;
  });
  window.addEventListener('pageshow', reset);
})();
