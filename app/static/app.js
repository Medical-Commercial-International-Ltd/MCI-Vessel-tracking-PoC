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

})();
