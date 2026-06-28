/* ── Device Labels (editable) ──────────────────────────────────
   Overlays custom labels (name + emoji icon) on the client bandwidth
   table and the host table. Labels are stored by MAC address.

   API:
     GET    /api/devices/labels            -> { labels: [{mac,label,icon}] }
     POST   /api/devices/label             <- {mac,label,icon}
     DELETE /api/devices/label/{mac}

   UI:
     - Pencil (✏️) button next to each device row opens an inline editor.
     - Labels cached locally and refetched on load.
     - Exposes window.DeviceLabels for integration by app.js.
*/

(function () {
  'use strict';

  const API = '';
  const STORE = new Map(); // mac -> {label, icon}
  let loaded = false;

  async function fetchJSON(url, opts) {
    const r = await fetch(API + url, opts);
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }

  async function load() {
    try {
      const data = await fetchJSON('/api/devices/labels');
      STORE.clear();
      (data.labels || []).forEach(l => STORE.set(l.mac.toLowerCase(), l));
      loaded = true;
    } catch (e) {
      console.warn('device_labels load', e);
    }
  }

  async function save(mac, label, icon) {
    const resp = await fetchJSON('/api/devices/label', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mac, label, icon }),
    });
    if (resp && resp.ok) {
      STORE.set(mac.toLowerCase(), { mac: mac.toLowerCase(), label, icon });
    }
    return resp;
  }

  async function remove(mac) {
    const resp = await fetchJSON(`/api/devices/label/${encodeURIComponent(mac)}`, { method: 'DELETE' });
    STORE.delete(mac.toLowerCase());
    return resp;
  }

  function get(mac) {
    if (!mac) return null;
    return STORE.get(String(mac).toLowerCase()) || null;
  }

  /** Return display string: icon + label (or fallback hostname). */
  function display(mac, fallback) {
    const l = get(mac);
    if (l && l.label) {
      const icon = l.icon ? escapeHtml(l.icon) + ' ' : '';
      return icon + escapeHtml(l.label);
    }
    return escapeHtml(fallback || '—');
  }

  /** Render an edit button. Caller wires up click. */
  function editButton(mac) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'tab-btn dl-edit-btn';
    btn.title = 'Gerät benennen';
    btn.textContent = '✏️';
    btn.dataset.mac = mac || '';
    btn.style.padding = '1px 6px';
    btn.style.fontSize = '11px';
    btn.style.marginLeft = '4px';
    return btn;
  }

  /** Open inline editor modal. */
  function openEditor(mac, currentDisplay, onSaved) {
    const existing = get(mac) || { label: '', icon: '' };
    const wrap = document.createElement('div');
    wrap.className = 'dl-modal-backdrop';
    wrap.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:1000;display:flex;align-items:center;justify-content:center';
    const box = document.createElement('div');
    box.style.cssText = 'background:var(--card,#0f172a);border:1px solid var(--border);border-radius:12px;padding:16px;min-width:280px;max-width:90vw;color:var(--text,#e5edf7)';
    box.innerHTML = `
      <div style="font-weight:700;margin-bottom:8px">Gerät benennen</div>
      <div style="font-size:11px;color:var(--muted,#94a3b8);margin-bottom:10px" class="mono">${escapeHtml(mac || '—')}</div>
      <label style="font-size:11px;color:var(--muted,#94a3b8)">Name</label>
      <input id="dl-name" type="text" placeholder="z.B. Wohnzimmer Laptop" value="${escapeHtml(existing.label || (currentDisplay && currentDisplay !== '—' ? currentDisplay : ''))}" style="width:100%;margin-bottom:10px;padding:6px 8px;background:var(--bg2,#0f172a);border:1px solid var(--border);border-radius:6px;color:var(--text,#e5edf7)">
      <label style="font-size:11px;color:var(--muted,#94a3b8)">Icon (Emoji)</label>
      <input id="dl-icon" type="text" maxlength="8" placeholder="💻 📱 🖥️ 🎮 📺" value="${escapeHtml(existing.icon || '')}" style="width:100%;margin-bottom:12px;padding:6px 8px;background:var(--bg2,#0f172a);border:1px solid var(--border);border-radius:6px;color:var(--text,#e5edf7)">
      <div style="display:flex;gap:8px;justify-content:flex-end">
        <button type="button" id="dl-del" class="tab-btn" style="margin-right:auto">Löschen</button>
        <button type="button" id="dl-cancel" class="tab-btn">Abbrechen</button>
        <button type="button" id="dl-save" class="tab-btn active">Speichern</button>
      </div>`;
    wrap.appendChild(box);
    document.body.appendChild(wrap);
    const nameInput = box.querySelector('#dl-name');
    nameInput.focus();
    const close = () => wrap.remove();
    box.querySelector('#dl-cancel').addEventListener('click', close);
    box.querySelector('#dl-del').addEventListener('click', async () => {
      try { await remove(mac); } catch (e) {}
      close();
      if (onSaved) onSaved();
    });
    box.querySelector('#dl-save').addEventListener('click', async () => {
      const label = nameInput.value.trim();
      const icon = box.querySelector('#dl-icon').value.trim();
      try { await save(mac, label, icon); close(); if (onSaved) onSaved(); }
      catch (e) { alert('Speichern fehlgeschlagen: ' + e.message); }
    });
  }

  // Public API
  window.DeviceLabels = {
    load,
    save,
    remove,
    get,
    display,
    editButton,
    openEditor,
    isLoaded: () => loaded,
  };

  // Auto-load on DOM ready.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', load);
  } else {
    load();
  }
})();