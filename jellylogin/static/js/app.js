'use strict';

/* ─── Utilities ─────────────────────────────────────────────────────────── */
function getCsrfToken() {
  return document.querySelector('input[name="csrf_token"]')?.value
    || (typeof CSRF_TOKEN !== 'undefined' ? CSRF_TOKEN : '');
}

/* ─── Toasts ─────────────────────────────────────────────────────────────── */
(function initToasts() {
  const container = document.createElement('div');
  container.id = 'toast-container';
  document.body.appendChild(container);
})();

function showToast(message, type = 'info', duration = 3500) {
  const icons = { success: 'fa-circle-check', error: 'fa-circle-exclamation', info: 'fa-circle-info' };
  const toast = document.createElement('div');
  toast.className = `toast toast--${type}`;
  toast.innerHTML = `<i class="fas ${icons[type] || icons.info}"></i><span>${message}</span>`;
  document.getElementById('toast-container').appendChild(toast);
  setTimeout(() => {
    toast.classList.add('removing');
    toast.addEventListener('animationend', () => toast.remove());
  }, duration);
}

/* ─── Password Toggle ────────────────────────────────────────────────────── */
document.addEventListener('click', e => {
  const btn = e.target.closest('.input-toggle-pw');
  if (!btn) return;
  const input = btn.closest('.input-wrapper')?.querySelector('input[type=password], input[type=text]');
  if (!input) return;
  const isPassword = input.type === 'password';
  input.type = isPassword ? 'text' : 'password';
  btn.querySelector('i').className = `fas fa-${isPassword ? 'eye-slash' : 'eye'}`;
});

/* ─── User Dropdown ──────────────────────────────────────────────────────── */
(function initUserMenu() {
  const btn = document.getElementById('user-menu-btn');
  const dropdown = document.getElementById('user-dropdown');
  if (!btn || !dropdown) return;

  dropdown.hidden = true;

  btn.addEventListener('click', e => {
    e.stopPropagation();
    const open = !dropdown.hidden;
    dropdown.hidden = open;
    btn.classList.toggle('open', !open);
  });

  document.addEventListener('click', () => {
    dropdown.hidden = true;
    btn?.classList.remove('open');
  });
})();

/* ─── Modals ─────────────────────────────────────────────────────────────── */
function openModal(id) {
  const overlay = document.getElementById(id);
  if (!overlay) return;
  overlay.hidden = false;
  overlay.querySelector('input:not([type=hidden]),.modal-close')?.focus();
}

function closeModal(id) {
  const overlay = document.getElementById(id);
  if (overlay) overlay.hidden = true;
}

document.addEventListener('click', e => {
  if (e.target.classList.contains('modal-overlay')) {
    e.target.hidden = true;
  }
});

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-overlay:not([hidden])').forEach(m => { m.hidden = true; });
  }
});

/* ─── Edit Link Modal ────────────────────────────────────────────────────── */
function openEditModal(card) {
  const form = document.getElementById('edit-link-form');
  if (!form) return;

  form.action = `/admin/links/${card.id}/edit`;

  const set = (name, value) => {
    const el = form.querySelector(`[name="${name}"]`);
    if (!el) return;
    if (el.type === 'checkbox') el.checked = Boolean(value);
    else if (el.type === 'radio') {
      form.querySelectorAll(`[name="${name}"]`).forEach(r => { r.checked = r.value === value; });
    } else el.value = value ?? '';
  };

  set('name', card.name);
  set('url', card.url);
  set('description', card.description || '');
  set('icon', card.icon || '');
  set('bg_color', card.bg_color || '#1e1b4b');
  set('bg_image', card.bg_image || '');
  set('style', card.style || 'glass');
  set('category_id', card.category_id ?? '');
  set('open_in_new_tab', card.open_in_new_tab);
  set('check_status', card.check_status);
  set('is_visible', card.is_visible);

  // Sync color text box
  const colorText = form.querySelector('#f-bg_color-text');
  if (colorText) colorText.value = card.bg_color || '#1e1b4b';

  openModal('modal-edit-link');
}

/* ─── Color picker sync ──────────────────────────────────────────────────── */
document.addEventListener('input', e => {
  const picker = e.target.closest('input[type=color]');
  if (!picker) return;
  const textId = picker.id + '-text';
  const textEl = document.getElementById(textId);
  if (textEl) textEl.value = picker.value;
});

/* ─── Mobile Search Toggle ───────────────────────────────────────────────── */
(function initMobileSearchBar() {
  // Only inject on pages that actually have link cards (not login/setup/admin)
  if (document.body.classList.contains('auth-page')) return;
  if (!document.querySelector('.link-card, .links-grid')) return;

  // Inject mobile search bar element once
  const bar = document.createElement('div');
  bar.className = 'mobile-search-bar';
  bar.id = 'mobile-search-bar';
  bar.innerHTML = `
    <i class="fas fa-magnifying-glass" style="color:var(--color-text-muted);font-size:.875rem;flex-shrink:0"></i>
    <input type="text" id="mobile-search-input" placeholder="Suchen…" autocomplete="off">
    <button class="mobile-search-close" onclick="toggleMobileSearch()" aria-label="Schließen">
      <i class="fas fa-xmark"></i>
    </button>`;
  document.body.appendChild(bar);

  const mobileInput = bar.querySelector('#mobile-search-input');
  mobileInput.addEventListener('input', () => filterCards(mobileInput.value.trim().toLowerCase()));
  mobileInput.addEventListener('keydown', e => {
    if (e.key === 'Escape') toggleMobileSearch();
  });
})();

function toggleMobileSearch() {
  const bar = document.getElementById('mobile-search-bar');
  const btn = document.getElementById('mobile-search-btn');
  if (!bar) return;
  const open = bar.classList.toggle('open');
  document.documentElement.classList.toggle('mobile-search-open', open);
  if (open) {
    bar.querySelector('input')?.focus();
    btn?.querySelector('i')?.classList.replace('fa-magnifying-glass', 'fa-xmark');
  } else {
    bar.querySelector('input').value = '';
    filterCards('');
    btn?.querySelector('i')?.classList.replace('fa-xmark', 'fa-magnifying-glass');
  }
}

/* ─── Search ─────────────────────────────────────────────────────────────── */
(function initSearch() {
  const input = document.getElementById('search-input');
  const resultsEl = document.getElementById('search-results');
  if (!input) return;

  // Keyboard shortcut '/' – only on dashboard/content pages
  document.addEventListener('keydown', e => {
    if (e.key === '/' && !['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName)
        && !document.body.classList.contains('auth-page')) {
      e.preventDefault();
      input.focus();
    }
  });

  if (!resultsEl) {
    // Dashboard inline filter
    input.addEventListener('input', () => filterCards(input.value.trim().toLowerCase()));
    input.addEventListener('keydown', e => {
      if (e.key === 'Escape') { input.value = ''; filterCards(''); input.blur(); }
    });
    return;
  }

  // Full search panel
  let timer;
  input.addEventListener('input', () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (!q) { resultsEl.hidden = true; return; }
    timer = setTimeout(() => fetchSearch(q), 220);
  });

  input.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      input.value = '';
      resultsEl.hidden = true;
      input.blur();
    }
  });

  document.addEventListener('click', e => {
    if (!input.contains(e.target) && !resultsEl.contains(e.target)) {
      resultsEl.hidden = true;
    }
  });
})();

function filterCards(q) {
  const cards = document.querySelectorAll('.link-card');
  const sections = document.querySelectorAll('.links-section');

  if (!q) {
    cards.forEach(c => c.hidden = false);
    sections.forEach(s => s.hidden = false);
    return;
  }

  sections.forEach(section => {
    let anyVisible = false;
    section.querySelectorAll('.link-card').forEach(card => {
      const name = card.dataset.name || '';
      const desc = card.dataset.desc || '';
      const match = name.includes(q) || desc.includes(q);
      card.hidden = !match;
      if (match) anyVisible = true;
    });
    section.hidden = !anyVisible;
  });
}

async function fetchSearch(q) {
  const resultsEl = document.getElementById('search-results');
  try {
    const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
    if (!res.ok) return;
    const items = await res.json();
    renderSearchResults(items, q);
    resultsEl.hidden = false;
  } catch {}
}

function renderSearchResults(items, q) {
  const el = document.getElementById('search-results');
  if (!items.length) {
    el.innerHTML = `<div class="search-no-results"><i class="fas fa-magnifying-glass"></i> Keine Ergebnisse für „${escHtml(q)}"</div>`;
    return;
  }
  el.innerHTML = items.map(card => `
    <a href="${escHtml(card.url)}" class="search-result-item"
       ${card.open_in_new_tab ? 'target="_blank" rel="noopener noreferrer"' : ''}>
      <div class="sr-icon">${renderIcon(card.icon)}</div>
      <div>
        <div class="sr-name">${escHtml(card.name)}</div>
        <div class="sr-url">${escHtml(card.url)}</div>
      </div>
    </a>
  `).join('');
}

function renderIcon(icon) {
  if (!icon) return '<i class="fas fa-link"></i>';
  if (icon.startsWith('http') || icon.startsWith('/'))
    return `<img src="${escHtml(icon)}" alt="" style="width:22px;height:22px;border-radius:4px;object-fit:contain">`;
  if (icon.startsWith('fa'))
    return `<i class="${escHtml(icon)}"></i>`;
  return `<span>${escHtml(icon)}</span>`;
}

/* ─── Category Tabs ──────────────────────────────────────────────────────── */
(function initCategoryTabs() {
  const tabs = document.getElementById('category-tabs');
  if (!tabs) return;

  tabs.addEventListener('click', e => {
    const tab = e.target.closest('.category-tab');
    if (!tab) return;

    tabs.querySelectorAll('.category-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');

    const cat = tab.dataset.cat;
    document.querySelectorAll('.links-section').forEach(section => {
      if (cat === 'all') {
        section.hidden = false;
      } else {
        section.hidden = section.dataset.cat !== cat;
      }
    });
  });
})();

/* ─── Status Checking ────────────────────────────────────────────────────── */
(function initStatusCheck() {
  if (typeof SHOW_STATUS === 'undefined' || !SHOW_STATUS) return;

  const dots = document.querySelectorAll('.status-dot[id^="status-"]');
  if (!dots.length) return;

  const statusIcons = { online: '🟢', offline: '🔴', unknown: '⚪', disabled: '' };

  // Stagger requests to avoid hammering
  Array.from(dots).forEach((dot, i) => {
    const id = dot.id.replace('status-', '');
    setTimeout(() => checkStatus(id, dot), i * 120);
  });
})();

async function checkStatus(linkId, dot) {
  try {
    const res = await fetch(`/api/status/${linkId}`);
    if (!res.ok) return;
    const { status, latency } = await res.json();
    dot.className = `status-dot status-dot--${status}`;
    const labels = { online: `Online${latency ? ` (${latency}ms)` : ''}`, offline: 'Offline', unknown: 'Unbekannt', disabled: '' };
    dot.title = labels[status] || status;
  } catch {
    dot.className = 'status-dot status-dot--unknown';
    dot.title = 'Prüfung fehlgeschlagen';
  }
}

/* ─── Admin: Drag-Sort ───────────────────────────────────────────────────── */
function initLinkAdmin() {
  initDragSort();
}

function initDragSort() {
  const tbody = document.getElementById('sortable-links');
  if (!tbody) return;

  let dragging = null;

  tbody.querySelectorAll('.sortable-row').forEach(row => {
    const handle = row.querySelector('.drag-handle');
    if (handle) handle.setAttribute('draggable', 'true');
    row.addEventListener('dragstart', e => {
      dragging = row;
      row.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
    });
    row.addEventListener('dragend', () => {
      row.classList.remove('dragging');
      tbody.querySelectorAll('.sortable-row').forEach(r => r.classList.remove('drag-over'));
      dragging = null;
      saveOrder();
    });
    row.addEventListener('dragover', e => {
      e.preventDefault();
      if (!dragging || dragging === row) return;
      const rect = row.getBoundingClientRect();
      if (e.clientY < rect.top + rect.height / 2) {
        tbody.insertBefore(dragging, row);
      } else {
        tbody.insertBefore(dragging, row.nextSibling);
      }
    });
  });
}

async function saveOrder() {
  const rows = document.querySelectorAll('.sortable-row[data-id]');
  const order = Array.from(rows).map(r => parseInt(r.dataset.id));
  try {
    const res = await fetch('/api/links/reorder', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': getCsrfToken() },
      body: JSON.stringify({ order }),
    });
    if (res.ok) showToast('Reihenfolge gespeichert.', 'success');
    else showToast('Fehler beim Speichern.', 'error');
  } catch {
    showToast('Netzwerkfehler.', 'error');
  }
}

/* ─── Auto-dismiss alerts ────────────────────────────────────────────────── */
document.querySelectorAll('.flash-container .alert').forEach(alert => {
  setTimeout(() => {
    alert.style.transition = 'opacity .4s';
    alert.style.opacity = '0';
    setTimeout(() => alert.remove(), 400);
  }, 4000);
});

/* ─── Helpers ────────────────────────────────────────────────────────────── */
function escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
