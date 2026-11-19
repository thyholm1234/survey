// Udfylder juridiske sider med driftsoplysninger fra /api/public/legal-info (kun textContent – Trusted Types-sikkert).
import './chrome.js';

const NOT_SET = 'ikke angivet – udfyldes af driftsansvarlig før produktion';

function get(obj, path) { return path.split('.').reduce((o, k) => (o == null ? o : o[k]), obj); }

async function main() {
  let info = null;
  try {
    const r = await fetch('/api/public/legal-info', { headers: { Accept: 'application/json' }, cache: 'no-store' });
    if (r.ok) info = await r.json();
  } catch { /* vis 'ikke angivet' */ }
  for (const el of document.querySelectorAll('[data-legal]')) {
    const v = info ? get(info, el.dataset.legal) : null;
    if (v === null || v === undefined || v === '') {
      el.textContent = NOT_SET; el.classList.add('todo');
    } else if (el.dataset.mail !== undefined) {
      const a = document.createElement('a'); a.href = `mailto:${v}`; a.textContent = v; el.replaceChildren(a);
    } else { el.textContent = String(v); }
  }
  const body = document.querySelector('[data-legal-cookies]');
  if (body && info) {
    for (const c of info.cookies) {
      const tr = document.createElement('tr');
      const cells = [c.name, c.purpose, `Session. Udløber efter ${c.idleMinutes} minutters inaktivitet, senest efter ${c.maxHours} timer.`,
        'Strengt nødvendig · 1. part'];
      cells.forEach((txt, i) => {
        const cell = document.createElement(i === 0 ? 'th' : 'td');
        if (i === 0) cell.scope = 'row';
        cell.textContent = txt; tr.append(cell);
      });
      body.append(tr);
    }
  }
}
main();
