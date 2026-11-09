"use strict";

(() => {
  const key = "study-notes-theme";
  const system = matchMedia("(prefers-color-scheme: dark)");
  const root = document.documentElement;
  let preference;
  try {
    const saved = localStorage.getItem(key);
    if (saved === "light" || saved === "dark") preference = saved;
  } catch {
    // The theme still works when storage is unavailable.
  }

  const current = () => preference ?? (system.matches ? "dark" : "light");
  root.dataset.theme = current();

  document.addEventListener("DOMContentLoaded", () => {
    const buttons = document.querySelectorAll("[data-theme-toggle]");
    const frame = document.getElementById("note-frame");

    function applyToNote() {
      const noteRoot = frame.contentDocument?.documentElement;
      if (preference && noteRoot) noteRoot.dataset.theme = preference;
    }

    function render() {
      const theme = current();
      root.dataset.theme = theme;
      for (const button of buttons) button.setAttribute("aria-pressed", String(theme === "dark"));
      applyToNote();
    }

    for (const button of buttons) {
      button.addEventListener("click", () => {
        preference = current() === "dark" ? "light" : "dark";
        try {
          localStorage.setItem(key, preference);
        } catch {
          // Keep the selection for the current page.
        }
        render();
      });
    }
    frame.addEventListener("load", applyToNote);
    system.addEventListener("change", render);
    render();
  });
})();
