/* ── PWA support ────────────────────────────────────────────────
   Registers /sw.js and handles the install prompt.
   Shows an "Installieren" button in the header when install is available. */

(function () {
  'use strict';

  let deferredPrompt = null;

  function registerSW() {
    if (!('serviceWorker' in navigator)) return;
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/sw.js').catch((err) => {
        console.warn('SW registration failed:', err);
      });
    });
  }

  function buildInstallButton() {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'tab-btn';
    btn.id = 'pwa-install-btn';
    btn.textContent = 'Installieren';
    btn.style.display = 'none';
    btn.style.marginLeft = '4px';
    return btn;
  }

  function addToHeader(btn) {
    const header = document.getElementById('header');
    if (!header) return;
    const lastUpdate = document.getElementById('last-update');
    if (lastUpdate) {
      lastUpdate.insertAdjacentElement('beforebegin', btn);
    } else {
      header.appendChild(btn);
    }
  }

  function handleInstallPrompt() {
    const btn = buildInstallButton();
    addToHeader(btn);

    window.addEventListener('beforeinstallprompt', (e) => {
      e.preventDefault();
      deferredPrompt = e;
      btn.style.display = '';
    });

    btn.addEventListener('click', async () => {
      if (!deferredPrompt) return;
      btn.style.display = 'none';
      deferredPrompt.prompt();
      const { outcome } = await deferredPrompt.userChoice;
      console.info('PWA install:', outcome);
      deferredPrompt = null;
    });

    window.addEventListener('appinstalled', () => {
      btn.style.display = 'none';
      deferredPrompt = null;
      console.info('Homelab Dashboard installed');
    });
  }

  function init() {
    registerSW();
    handleInstallPrompt();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();