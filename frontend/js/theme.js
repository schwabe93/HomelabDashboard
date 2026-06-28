/* ── Light/Dark Theme Toggle ────────────────────────────────────
   Adds a sun/moon toggle button to the header, persists the choice
   in localStorage and applies light theme via body.light-theme.
   Default: dark (current theme stays as-is).
   Depends on: css/theme-light.css (must be loaded in index.html). */

(function () {
  'use strict';

  const STORAGE_KEY = 'homelab-theme';
  const LIGHT_CLASS = 'light-theme';

  /** Read stored preference; returns 'dark' if unset. */
  function storedTheme() {
    try { return localStorage.getItem(STORAGE_KEY) || 'dark'; }
    catch (_) { return 'dark'; }
  }

  /** Persist preference (best-effort). */
  function storeTheme(theme) {
    try { localStorage.setItem(STORAGE_KEY, theme); } catch (_) {}
  }

  /** Apply theme class to <body>. */
  function applyTheme(theme) {
    document.body.classList.toggle(LIGHT_CLASS, theme === 'light');
  }

  /** Build the toggle button (sun/moon icon). */
  function buildButton() {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'theme-toggle';
    btn.setAttribute('aria-label', 'Theme wechseln');
    btn.title = 'Helles / dunkles Theme wechseln';
    return btn;
  }

  /** Update icon/title based on active theme. */
  function updateButton(btn) {
    const isLight = document.body.classList.contains(LIGHT_CLASS);
    btn.textContent = isLight ? '🌙' : '☀️';
    btn.title = isLight ? 'Zum dunklen Theme wechseln' : 'Zum hellen Theme wechseln';
  }

  function init() {
    // Apply stored preference before first paint as much as possible.
    applyTheme(storedTheme());

    // Insert button into the header (after #last-update if present, else at the end).
    const header = document.getElementById('header');
    if (!header) return;

    const btn = buildButton();
    const lastUpdate = document.getElementById('last-update');
    if (lastUpdate) {
      // place before last-update so it stays near the right side
      lastUpdate.insertAdjacentElement('beforebegin', btn);
    } else {
      header.appendChild(btn);
    }

    updateButton(btn);

    btn.addEventListener('click', () => {
      const nowLight = !document.body.classList.contains(LIGHT_CLASS);
      applyTheme(nowLight ? 'light' : 'dark');
      storeTheme(nowLight ? 'light' : 'dark');
      updateButton(btn);
    });

    // React to system preference changes only if the user never chose.
    try {
      const mq = window.matchMedia('(prefers-color-scheme: light)');
      mq.addEventListener('change', e => {
        if (storedTheme() !== 'system-auto') return;
        applyTheme(e.matches ? 'light' : 'dark');
        updateButton(btn);
      });
    } catch (_) {}
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();