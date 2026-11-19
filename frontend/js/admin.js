import { api, setCsrf } from './api.js';
import { h, s, clear, fmt } from './dom.js';
import { icon } from './icons.js';
import './chrome.js';

const view = document.getElementById('view');
const userbox = document.getElementById('userbox');
const statusEl = document.getElementById('status');
const tooltip = document.getElementById('tooltip');

const app = { me: null, who: null, tenantId: null, tenants: [], allTenants: [], units: [], surveys: [], tab: 'dashboard' };
const UNIT_TYPES = { daycare: 'Dagtilbud', school: 'Skole', other: 'Andet' };

function announce(m) { statusEl.textContent = ''; requestAnimationFrame(() => { statusEl.textContent = m; }); }
function focusHeading() { const hd = view.querySelector('h2'); if (hd) { hd.tabIndex = -1; hd.focus(); } }
function err(id) { return h('p', { id, class: 'error', role: 'alert' }); }
/** Midtstillet auth-visning (login, MFA, adgangskode) i samme hero-stil som respondentsiden. */
function authShell({ badgeIcon = 'lock', badge = 'Kun for administratorer', title, lead }, ...nodes) {
  return h('section', { class: 'hero', 'aria-labelledby': 'auth-h' }, h('div', { class: 'hero-inner' },
    h('span', { class: 'badge' }, icon(badgeIcon, 'icon-sm'), badge),
    h('h2', { id: 'auth-h', text: title }),
    lead ? h('p', { class: 'lead', text: lead }) : null,
    h('div', { class: 'card' }, ...nodes)));
}
const TAB_ICONS = { dashboard: 'layout-dashboard', surveys: 'clipboard-list', units: 'building-2', codes: 'key-round',
  analyses: 'flask-conical', exports: 'download', users: 'users', audit: 'scroll-text', tenants: 'landmark' };
const TINTS = ['a', 'b', 'c'];
function tabIcon(key, i = 0) { return h('span', { class: `icon-box ${TINTS[i % TINTS.length]}` }, icon(TAB_ICONS[key])); }
/** Sidehoved for en fane: farvet ikonboks + serif h2. */
function heading(key, text) {
  return h('div', { class: 'panel-head' }, tabIcon(key, Object.keys(TAB_ICONS).indexOf(key)), h('h2', { text }));
}
function field(label, input, hint) {
  const id = input.id || `f-${Math.random().toString(36).slice(2)}`;
  input.id = id;
  return h('div', { class: 'field' }, h('label', { for: id, text: label }), input, hint ? h('span', { class: 'hint', text: hint }) : null);
}
function table(caption, headers, rows) {
  const capId = `cap-${Math.random().toString(36).slice(2)}`;
  return h('div', { class: 'table-wrapper', tabindex: 0, role: 'region', 'aria-labelledby': capId },
    h('table', {}, h('caption', { id: capId, text: caption }),
      h('thead', {}, h('tr', {}, headers.map((x) => h('th', { scope: 'col', text: x })))),
      h('tbody', {}, rows)));
}
function row(head, cells) { return h('tr', {}, h('th', { scope: 'row' }, head), cells.map((c) => (c instanceof Node ? c : h('td', { text: c ?? '–' })))); }
function supCell(colspan = 1) { return h('td', { class: 'suppressed', colspan, text: 'Undertrykt (lille n)' }); }
async function guard(fn, errEl) {
  try { if (errEl) errEl.textContent = ''; return await fn(); } catch (ex) {
    if (ex.status === 401) { boot(); return; }
    if (errEl) errEl.textContent = ex.message || 'Der opstod en fejl.'; else announce(ex.message || 'Fejl');
  }
}

// ------------------------------------------------------------------ Login
function loginView(message) {
  clear(userbox);
  const e = err('login-err');
  if (message) e.textContent = message;
  const u = h('input', { name: 'username', type: 'text', autocomplete: 'username', required: true, autocapitalize: 'none', autocorrect: 'off', spellcheck: 'false' });
  const p = h('input', { name: 'password', type: 'password', autocomplete: 'current-password', required: true });
  const btn = h('button', { type: 'submit', class: 'cta-full' }, 'Log ind', icon('arrow-right'));
  const form = h('form', { method: 'post', action: '/admin/' }, field('Brugernavn', u), field('Adgangskode', p), e, btn);
  form.addEventListener('submit', async (ev) => {
    ev.preventDefault(); btn.disabled = true;
    await guard(async () => {
      const r = await api('POST', '/api/admin/auth/login', { username: u.value, password: p.value });
      setCsrf(r.csrfToken);
      p.value = '';
      return r.mfaEnrolled ? mfaView(false) : mfaView(true);
    }, e);
    btn.disabled = false;
  });
  clear(view).append(authShell({ title: 'Log ind', lead: 'Administration af spørgeskemaer, adgangskoder og resultater.' }, form));
  focusHeading();
}

async function mfaView(enroll) {
  const e = err('mfa-err');
  const parts = [];
  if (enroll) {
    const setup = await guard(() => api('POST', '/api/admin/auth/mfa/setup', {}), e);
    if (!setup) return;
    parts.push(h('p', { text: 'Scan QR-koden med en godkendelsesapp (fx Microsoft Authenticator) eller indtast nøglen manuelt.' }),
      h('img', { src: setup.qrSvgDataUri, alt: 'QR-kode til to-faktor-opsætning', width: 220, height: 220 }),
      h('p', {}, 'Nøgle: ', h('code', { text: setup.secret })));
  }
  const c = h('input', { name: 'code', type: 'text', inputmode: 'numeric', autocomplete: 'one-time-code', pattern: '\\d{6}', maxlength: 6, required: true });
  const btn = h('button', { type: 'submit', class: 'cta-full' }, 'Bekræft', icon('shield-check'));
  const form = h('form', { method: 'post', action: '/admin/' }, field('6-cifret kode', c), e, btn);
  form.addEventListener('submit', async (ev) => {
    ev.preventDefault(); btn.disabled = true;
    await guard(async () => {
      const r = await api('POST', '/api/admin/auth/mfa/verify', { code: c.value.trim() });
      setCsrf(r.csrfToken);
      return r.mustChangePassword ? passwordView() : boot();
    }, e);
    btn.disabled = false;
  });
  clear(view).append(authShell({ badgeIcon: 'shield-check', badge: 'Ekstra sikkerhed',
    title: enroll ? 'Opsæt to-faktor-godkendelse' : 'To-faktor-godkendelse' }, ...parts, form));
  focusHeading();
}

function passwordView() {
  const e = err('pw-err');
  const cur = h('input', { type: 'password', autocomplete: 'current-password', required: true });
  const nw = h('input', { type: 'password', autocomplete: 'new-password', minlength: 14, required: true, 'aria-describedby': 'pw-hint' });
  const btn = h('button', { type: 'submit', class: 'cta-full' }, 'Skift adgangskode', icon('key-round'));
  const form = h('form', { method: 'post', action: '/admin/' }, field('Nuværende adgangskode', cur),
    h('div', { class: 'field' }, h('label', { for: 'nw', text: 'Ny adgangskode' }), Object.assign(nw, { id: 'nw' }),
      h('span', { id: 'pw-hint', class: 'hint', text: 'Mindst 14 tegn. Brug gerne en lang sætning.' })), e, btn);
  form.addEventListener('submit', async (ev) => {
    ev.preventDefault(); btn.disabled = true;
    await guard(async () => { await api('POST', '/api/admin/auth/password', { current: cur.value, new: nw.value }); boot(); }, e);
    btn.disabled = false;
  });
  clear(view).append(authShell({ badgeIcon: 'key-round', badge: 'Første login', title: 'Skift adgangskode' }, form));
  focusHeading();
}

async function logout() {
  await api('POST', '/api/admin/auth/logout', {}).catch(() => {});
  setCsrf(null);
  loginView('Du er logget ud.');
}

// ------------------------------------------------------------------ Shell
const TABS = [
  ['dashboard', 'Resultater'], ['surveys', 'Spørgeskemaer'], ['units', 'Institutioner'], ['codes', 'Adgangskoder'],
  ['analyses', 'Analyser'], ['exports', 'Eksport'], ['users', 'Brugere'], ['audit', 'Auditlog'], ['tenants', 'Tenants'],
];

async function loadTenantData() {
  if (!app.tenantId) { app.units = []; app.surveys = []; return; }
  [app.units, app.surveys] = await Promise.all([
    api('GET', `/api/admin/tenants/${app.tenantId}/units`),
    api('GET', `/api/admin/surveys?tenantId=${app.tenantId}`),
  ]);
}
function publishedVersions() {
  return app.surveys.flatMap((sv) => sv.versions.filter((v) => v.status === 'published')
    .map((v) => ({ ...v, title: sv.title, assignedUnitIds: sv.assignedUnitIds || [] })));
}
function versionSelect(id = 'sv-select') {
  return h('select', { id, required: true }, publishedVersions().map((v) => h('option', { value: v.id, text: `${v.title} v${v.versionNo}` })));
}
// Organisation: institution (parentId null) → afdelinger/klasser (parentId = institution)
function unitLabel(u) { return u.parentId ? `${u.parentName || '?'} › ${u.name}` : u.name; }
/** Enheder sorteret som træ: institution efterfulgt af dens afdelinger/klasser. */
function unitsSorted() {
  const key = (u) => [(u.parentId ? u.parentName : u.name) || '', u.parentId ? 1 : 0, u.name].map((x) => String(x).toLocaleLowerCase('da'));
  return [...app.units].sort((a, b) => { const ka = key(a); const kb = key(b);
    for (let i = 0; i < 3; i++) { const c = String(ka[i]).localeCompare(String(kb[i]), 'da'); if (c) return c; } return 0; });
}
function unitOptions() { return unitsSorted().map((u) => h('option', { value: u.id, text: unitLabel(u) })); }
function isOrgAdmin() { return app.who?.orgTenants?.includes(app.tenantId); }

function shell() {
  clear(userbox).append(h('span', { class: 'muted', text: `${app.who.username} ` }),
    h('button', { type: 'button', class: 'secondary', onclick: logout }, icon('log-out', 'icon-sm'), 'Log ud'));
  const tabs = TABS.filter(([k]) => {
    if (k === 'tenants') return app.who.systemAdmin;
    if (['surveys', 'units', 'users'].includes(k)) return isOrgAdmin();
    if (k === 'audit') return app.who.systemAdmin || isOrgAdmin();
    return Boolean(app.tenantId);
  });
  if (!tabs.some(([k]) => k === app.tab)) app.tab = tabs[0]?.[0] || 'tenants';
  const tenantSel = app.tenants.length > 1 ? field('Organisation', h('select', { id: 'tenant-sel', onchange: async (e) => {
    app.tenantId = e.target.value; await loadTenantData(); shell(); } }, app.tenants.map((t) =>
    h('option', { value: t.id, text: t.name, selected: t.id === app.tenantId })))) : null;
  const nav = h('nav', { class: 'tabs', 'aria-label': 'Sektioner' }, tabs.map(([k, label], i) =>
    h('button', { type: 'button', 'aria-current': k === app.tab ? 'page' : null, onclick: () => { app.tab = k; shell(); } },
      tabIcon(k, i), label)));
  const panel = h('div', { id: 'panel' });
  clear(view).append(h('div', { class: 'filters' }, tenantSel), nav, panel);
  ({ dashboard: dashboardTab, surveys: surveysTab, units: unitsTab, codes: codesTab, analyses: analysesTab,
     exports: exportsTab, users: usersTab, audit: auditTab, tenants: tenantsTab })[app.tab](panel);
}

// ------------------------------------------------------------------ Filtre (fælles)
function filterForm(onSubmit, { withThresholds = false } = {}) {
  const sv = versionSelect();
  const unitType = h('select', { id: 'f-type' }, h('option', { value: '', text: 'Alle' }),
    Object.entries(UNIT_TYPES).map(([k, v]) => h('option', { value: k, text: v })));
  const picker = unitPicker();
  const from = h('input', { type: 'date', id: 'f-from' });
  const to = h('input', { type: 'date', id: 'f-to' });
  const bgWrap = h('div', { class: 'filters' });
  const loadBg = async () => {
    clear(bgWrap);
    if (!sv.value) return;
    const d = await api('GET', `/api/admin/surveys/versions/${sv.value}`);
    for (const b of d.backgroundVariables) {
      bgWrap.append(field(b.label, h('select', { 'data-bg': b.code }, h('option', { value: '', text: 'Alle' }),
        b.options.map((o) => h('option', { value: o.code, text: o.label })))));
    }
  };
  sv.addEventListener('change', loadBg);
  const thr = h('input', { type: 'number', id: 'f-thr', min: 0.5, max: 1, step: 0.05, value: 0.8 });
  const btn = h('button', { type: 'submit', text: 'Vis' });
  const form = h('form', { method: 'get', action: '/admin/' },
    h('search', {}, h('div', { class: 'filters' }, field('Spørgeskema', sv), field('Type', unitType), picker.el,
      field('Fra dato', from), field('Til dato', to), withThresholds ? field('Subskala-tærskel', thr, 'Andel besvarede items') : null),
    bgWrap, btn));
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const bg = {};
    bgWrap.querySelectorAll('select[data-bg]').forEach((x) => { if (x.value) bg[x.dataset.bg] = x.value; });
    const chosen = picker.value();
    onSubmit({ surveyVersionId: sv.value, unitIds: chosen.length ? chosen : null, unitType: unitType.value || null,
      dateFrom: from.value || null, dateTo: to.value || null, background: bg }, Number(thr.value));
  });
  loadBg();
  return form;
}
/** Dropdown med flueben: institutioner og deres afdelinger/klasser. Tomt valg = alle. */
function unitPicker() {
  const units = unitsSorted();
  const summary = h('summary', { class: 'picker-summary' });
  const boxes = [];
  const list = h('div', { class: 'picker-list', role: 'group', 'aria-label': 'Institutioner og afdelinger' });
  const update = () => {
    const sel = boxes.filter((b) => b.checked);
    summary.textContent = !sel.length ? 'Alle institutioner'
      : sel.length <= 2 ? sel.map((b) => b.dataset.label).join(', ') : `${sel.length} valgt`;
  };
  for (const u of units) {
    const id = `pick-${u.id}`;
    const cb = h('input', { type: 'checkbox', id, value: u.id });
    cb.dataset.label = unitLabel(u);
    cb.addEventListener('change', update);
    boxes.push(cb);
    list.append(h('label', { class: `check${u.parentId ? ' child' : ''}`, for: id }, cb,
      u.parentId ? ` ${u.name}` : h('strong', { text: ` ${u.name}` })));
  }
  const clearBtn = h('button', { type: 'button', class: 'link', text: 'Ryd valg',
    onclick: () => { boxes.forEach((b) => { b.checked = false; }); update(); } });
  const details = h('details', { class: 'picker' }, summary,
    h('div', { class: 'picker-panel' },
      h('p', { class: 'hint', text: 'Sæt flueben ved det, du vil sammenligne. En institution omfatter sine afdelinger/klasser.' }),
      units.length ? list : h('p', { text: 'Ingen institutioner.' }), clearBtn));
  // Luk ved klik udenfor eller Escape
  document.addEventListener('click', (e) => { if (details.open && !details.contains(e.target)) details.open = false; });
  details.addEventListener('keydown', (e) => { if (e.key === 'Escape') { details.open = false; summary.focus(); } });
  update();
  const el = h('div', { class: 'field' }, h('span', { class: 'label', id: 'pick-lbl', text: 'Institutioner og afdelinger' }), details);
  summary.setAttribute('aria-describedby', 'pick-lbl');
  return { el, value: () => boxes.filter((b) => b.checked).map((b) => b.value) };
}
function filtersToQuery(f) {
  const q = new URLSearchParams({ tenantId: app.tenantId, surveyVersionId: f.surveyVersionId });
  if (f.unitIds) q.set('unitIds', f.unitIds.join(','));
  if (f.unitType) q.set('unitType', f.unitType);
  if (f.dateFrom) q.set('dateFrom', f.dateFrom);
  if (f.dateTo) q.set('dateTo', f.dateTo);
  for (const [k, v] of Object.entries(f.background || {})) q.append('bg', `${k}:${v}`);
  return q;
}

// ------------------------------------------------------------------ Diagrammer
function showTip(ev, text) {
  tooltip.textContent = text; tooltip.hidden = false;
  const r = (ev.target.getBoundingClientRect?.() || { left: ev.clientX, top: ev.clientY, width: 0 });
  tooltip.style.setProperty('left', `${Math.min(window.innerWidth - 220, r.left + r.width / 2 + 8)}px`);
  tooltip.style.setProperty('top', `${r.top - 36}px`);
}
function hideTip() { tooltip.hidden = true; }

/** Punkt + 95 %-CI pr. kategori; én række pr. kategori, evt. to serier (dagtilbud/skole). */
function ciChart(rows, { min = 1, max = 6, series = null, title }) {
  const W = 760; const left = 300; const right = 24; const rowH = series ? 44 : 34; const top = 24;
  const H = top + rows.length * rowH + 28;
  const x = (v) => left + ((v - min) / (max - min)) * (W - left - right);
  const svg = s('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': title });
  for (let v = min; v <= max; v++) {
    svg.append(s('line', { class: 'grid', x1: x(v), x2: x(v), y1: top - 8, y2: H - 24 }),
      s('text', { x: x(v), y: H - 8, 'text-anchor': 'middle', text: String(v) }));
  }
  rows.forEach((r, i) => {
    const yBase = top + i * rowH + rowH / 2;
    svg.append(s('text', { class: 'label', x: left - 10, y: yBase + 4, 'text-anchor': 'end', text: r.label }));
    const entries = series ? series.map((k, j) => [k, r[k], yBase + (j - 0.5) * 14]) : [['main', r, yBase]];
    for (const [k, d, y] of entries) {
      if (!d || d.suppressed || d.mean == null) continue;
      const cls = series ? `s-${k}` : '';
      if (d.ci95) svg.append(s('line', { class: `ci ${cls}`, x1: x(d.ci95[0]), x2: x(d.ci95[1]), y1: y, y2: y }));
      const tip = `${r.label}${series ? ` · ${k === 'daycare' ? 'Dagtilbud' : 'Skole'}` : ''}: middel ${fmt(d.mean)}` +
        (d.ci95 ? ` [${fmt(d.ci95[0])}; ${fmt(d.ci95[1])}]` : '') + `, n=${d.nValid}`;
      const hit = s('circle', { class: 'hit', cx: x(d.mean), cy: y, r: 12, tabindex: 0, role: 'img', 'aria-label': tip });
      hit.addEventListener('pointerenter', (e) => showTip(e, tip));
      hit.addEventListener('focus', (e) => showTip(e, tip));
      hit.addEventListener('pointerleave', hideTip); hit.addEventListener('blur', hideTip);
      // Serier skelnes på form (cirkel/firkant) – ikke kun farve (WCAG 1.4.1)
      svg.append(hit, k === 'school'
        ? s('rect', { class: `dot ${cls}`, x: x(d.mean) - 5, y: y - 5, width: 10, height: 10, rx: 2 })
        : s('circle', { class: `dot ${cls}`, cx: x(d.mean), cy: y, r: 5 }));
    }
  });
  return h('figure', { class: 'chart' }, svg);
}

function heatColor(v, min = 1, max = 6) {
  const steps = 7; const i = Math.max(0, Math.min(steps - 1, Math.floor(((v - min) / (max - min)) * steps)));
  return [`var(--seq-${i})`, i >= 4 ? '#ffffff' : '#0b0b0b'];
}

// ------------------------------------------------------------------ Resultater
function dashboardTab(panel) {
  const out = h('div');
  const e = err('dash-err');
  panel.append(heading('dashboard', 'Resultater'),
    h('p', { class: 'hint', text: 'Aggregerede, beskrivende resultater. Ingen individuelle profiler eller ranglister. Små celler undertrykkes.' }),
    publishedVersions().length ? filterForm(async (f, thr) => {
      const q = filtersToQuery(f); q.set('subscaleThreshold', String(thr));
      const d = await guard(() => api('GET', `/api/admin/dashboard?${q}`), e);
      if (d) renderDashboard(out, d);
    }, { withThresholds: true }) : h('p', { text: 'Ingen publicerede spørgeskemaer endnu.' }), e, out);
}

function renderDashboard(out, d) {
  clear(out);
  if (d.suppressed) { out.append(h('p', { class: 'notice', text: d.reason })); return; }
  const sub = Object.fromEntries(d.subscales.map((x) => [x.code, x.name]));
  const dom = Object.fromEntries(d.domains.map((x) => [x.code, x.name]));
  out.append(h('div', { class: 'stats', role: 'group', 'aria-label': 'Nøgletal' },
    [[d.n, 'besvarelser'], [d.minCellSize, 'minimum cellestørrelse'], [d.domains.length, 'domæner'], [d.subscales.length, 'perspektiver']]
      .map(([v, l]) => h('div', { class: 'stat' }, h('b', { text: String(v) }), h('span', { text: l })))));

  // 1. Profil
  out.append(h('section', { class: 'card' }, h('h3', { text: '1. Subskalaprofil (middel og 95 % CI)' }),
    ciChart(d.profile.map((p) => ({ ...p, label: sub[p.subscale] })), { title: 'Subskalaprofil' }),
    table('Subskalaprofil', ['Subskala', 'N', 'Gyldige', 'Missing %', 'Middel', 'SD', 'Median', 'IQR', '95 % CI'],
      d.profile.map((p) => p.suppressed ? row(sub[p.subscale], [supCell(8)]) :
        row(sub[p.subscale], [p.n, p.nValid, fmt(p.missingPct, 1), fmt(p.mean), fmt(p.sd), fmt(p.median), fmt(p.iqr),
          p.ci95 ? `${fmt(p.ci95[0])}–${fmt(p.ci95[1])}` : '–'])))));

  // 2. Heatmap
  const hm = new Map(d.heatmap.map((c) => [`${c.domain}|${c.subscale}`, c]));
  const heatRows = d.domains.map((dm) => row(dom[dm.code], d.subscales.map((sb) => {
    const c = hm.get(`${dm.code}|${sb.code}`);
    if (!c || c.suppressed) return supCell();
    const td = h('td', { class: 'heat', text: fmt(c.mean), title: `n=${c.nValid}, SD ${fmt(c.sd)}` });
    const [bg, ink] = heatColor(c.mean);
    td.style.setProperty('--cell-bg', bg); td.style.setProperty('--cell-ink', ink);
    return td;
  })));
  out.append(h('section', { class: 'card' }, h('h3', { text: '2. Domæne × subskala (middel)' }),
    h('p', { class: 'hint', text: 'Mørkere = højere middelværdi (1–6). Værdien står i cellen.' }),
    table('Domæne × subskala', ['Domæne', ...d.subscales.map((x) => x.name)], heatRows)));

  // 3. Afdelinger (alfabetisk – ikke rangliste)
  const byInst = d.comparisonLevel === 'institution';
  const custom = d.comparisonLevel === 'custom';
  const cmpTitle = byInst ? 'Institutioner' : custom ? 'Valgte institutioner og afdelinger'
    : `Afdelinger/klasser${d.institution ? ` – ${d.institution.name}` : ''}`;
  out.append(h('section', { class: 'card' }, h('h3', { text: `3. ${cmpTitle} (alfabetisk, ikke rangliste)` }),
    h('p', { class: 'hint', text: byInst
      ? 'Hver institution omfatter alle sine afdelinger/klasser. Vælg institutioner og afdelinger i filteret for at sammenligne dem.'
      : custom ? 'Hver valgt institution omfatter sine afdelinger/klasser. Er en institution valgt sammen med nogle af sine '
        + 'afdelinger, vises de valgte afdelinger for sig og institutionen som »øvrige«, så ingen besvarelse tælles to gange.'
        : 'Profilen ovenfor er hele institutionens resultat; her sammenlignes dens afdelinger/klasser.' }),
    table(cmpTitle, [byInst ? 'Institution' : custom ? 'Institution / afdeling' : 'Afdeling/klasse', 'Type', 'N', ...d.subscales.map((x) => `${x.name} (95 % CI)`)],
      d.units.map((u) => u.suppressed ? row(u.name, [UNIT_TYPES[u.unitType], supCell(1 + d.subscales.length)]) :
        row(u.name, [UNIT_TYPES[u.unitType], u.n, ...u.subscales.map((c) => c.suppressed ? supCell() :
          h('td', { text: `${fmt(c.mean)} (${c.ci95 ? `${fmt(c.ci95[0])}–${fmt(c.ci95[1])}` : '–'})` }))])))));

  // 4. Skole vs dagtilbud
  out.append(h('section', { class: 'card' }, h('h3', { text: '4. Skole og dagtilbud' }),
    h('div', { class: 'legend' }, h('span', {}, h('span', { class: 'sw daycare' }), 'Dagtilbud'), h('span', {}, h('span', { class: 'sw school' }), 'Skole')),
    ciChart(d.setting.map((r) => ({ ...r, label: sub[r.subscale] })), { series: ['daycare', 'school'], title: 'Skole og dagtilbud' }),
    table('Skole og dagtilbud (beskrivende)', ['Subskala', 'Dagtilbud middel (n)', 'Skole middel (n)', 'Hedges g skole−dagtilbud [95 % CI]'],
      d.setting.map((r) => {
        const g = r.hedgesG_school_minus_daycare;
        return row(sub[r.subscale], [
          r.daycare.suppressed ? supCell() : h('td', { text: `${fmt(r.daycare.mean)} (${r.daycare.nValid})` }),
          r.school.suppressed ? supCell() : h('td', { text: `${fmt(r.school.mean)} (${r.school.nValid})` }),
          g && g.g != null ? `${fmt(g.g)} [${fmt(g.ci95[0])}; ${fmt(g.ci95[1])}]` : '–']);
      })),
    h('p', { class: 'hint', text: 'Inferens (Welch-ANOVA, mixed model med afdeling som random effect) køres under Analyser.' })));

  // 6. Missing
  out.append(h('section', { class: 'card' }, h('h3', { text: '6. Missing og "kan ikke vurdere" (% af celler)' }),
    table('Missing pr. subskala', ['Subskala', 'Gyldige', 'Kan ikke vurdere', 'Ubesvaret', 'Ikke nået'],
      d.missing.bySubscale.map((m) => row(sub[m.subscale], [fmt(m.validPct, 1), fmt(m.cannotAssessPct, 1), fmt(m.notAnsweredPct, 1), fmt(m.notReachedPct, 1)]))),
    table('Missing pr. domæne', ['Domæne', 'Gyldige', 'Kan ikke vurdere', 'Ubesvaret', 'Ikke nået'],
      d.missing.byDomain.map((m) => row(dom[m.domain], [fmt(m.validPct, 1), fmt(m.cannotAssessPct, 1), fmt(m.notAnsweredPct, 1), fmt(m.notReachedPct, 1)])))));

  // 7. Items
  out.append(h('section', { class: 'card' }, h('h3', { text: '7. Itemanalyse og svarfordeling' }),
    table('Items', ['Item', 'Subskala', 'Domæne', 'N', 'Middel', 'SD', 'Missing %', 'Kan ikke vurdere', 'Fordeling 1–6', 'Median svartid (s)'],
      d.items.map((it) => row(it.questionId, [sub[it.subscale], it.domain, it.n, fmt(it.mean), fmt(it.sd), fmt(it.missingPct, 1), it.cannotAssess,
        it.distribution ? Object.values(it.distribution).join(' / ') : 'Undertrykt',
        it.medianRtMs != null ? fmt(it.medianRtMs / 1000, 1) : '–'])))));

  // 8. Protokol
  out.append(h('section', { class: 'card' }, h('h3', { text: '8. Analyseprotokol' }),
    h('pre', { class: 'json', text: JSON.stringify(d.protocol, null, 2) })));
}

// ------------------------------------------------------------------ Spørgeskemaer
function surveysTab(panel) {
  const e = err('imp-err');
  const file = h('input', { type: 'file', id: 'imp-file', accept: 'application/json,.json' });
  const result = h('div');
  let doc = null;
  const previewBtn = h('button', { type: 'submit', text: 'Validér og vis preview' });
  const form = h('form', { method: 'post', action: '/admin/' }, field('Spørgeskema-JSON', file, 'Max 2 MB. Valideres mod survey.schema.json.'), e, previewBtn);
  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    if (!file.files[0]) { e.textContent = 'Vælg en fil.'; return; }
    if (file.files[0].size > 2 * 1024 * 1024) { e.textContent = 'Filen er for stor.'; return; }
    try { doc = JSON.parse(await file.files[0].text()); } catch { e.textContent = 'Filen er ikke gyldig JSON.'; return; }
    const r = await guard(() => api('POST', '/api/admin/surveys/import', { tenantId: app.tenantId, document: doc, dryRun: true }), e);
    if (r) renderPreview(result, r, doc);
  });
  panel.append(heading('surveys', 'Spørgeskemaer'), h('section', { class: 'card' }, h('h3', { text: 'Importér' }), form, result),
    assignmentSection(),
    h('section', { class: 'card' }, h('h3', { text: 'Versioner' }), table('Versioner', ['Spørgeskema', 'Version', 'Status', 'Importeret', 'SHA-256', ''],
      app.surveys.flatMap((sv) => sv.versions.map((v) => row(`${sv.title} (${sv.surveyId})`, [String(v.versionNo), v.status,
        new Date(v.importedAt).toLocaleString('da-DK'), v.sha256.slice(0, 12) + '…',
        h('td', {}, v.status === 'draft' ? h('button', { type: 'button', text: 'Publicér', onclick: async () => {
          if (!confirm('Publicering er permanent – versionen kan derefter ikke ændres. Fortsæt?')) return;
          await guard(() => api('POST', `/api/admin/surveys/${v.id}/publish`, {}));
          await loadTenantData(); shell();
        } }) : '')]))))));
}

/** Tildeling af spørgeskemaer til institutioner. Fratagelse stopper nye koder, men sletter intet. */
function assignmentSection() {
  const insts = app.units.filter((u) => !u.parentId).sort((a, b) => a.name.localeCompare(b.name, 'da'));
  const intro = h('p', { class: 'hint', text: 'Spørgeskemaerne ligger i biblioteket og kan tildeles de institutioner, der skal bruge dem. '
    + 'Der kan kun udstedes adgangskoder til institutioner (og deres afdelinger/klasser), som spørgeskemaet er tildelt. '
    + 'Fratager du et spørgeskema, kan der ikke laves nye koder, men allerede udleverede koder og indsamlede svar berøres ikke.' });
  if (!app.surveys.length) return h('section', { class: 'card' }, h('h3', { text: 'Tildeling til institutioner' }), intro,
    h('p', { class: 'notice', text: 'Importér et spørgeskema først.' }));
  if (!insts.length) return h('section', { class: 'card' }, h('h3', { text: 'Tildeling til institutioner' }), intro,
    h('p', { class: 'notice', text: 'Opret først institutioner under Institutioner.' }));
  const forms = app.surveys.map((s) => {
    const e = err(`asg-err-${s.id}`);
    const assigned = new Set(s.assignedUnitIds || []);
    const boxes = insts.map((i) => {
      const id = `asg-${s.id}-${i.id}`;
      return h('label', { class: 'check', for: id }, h('input', { type: 'checkbox', id, value: i.id, checked: assigned.has(i.id) }),
        ` ${i.name} (${UNIT_TYPES[i.unitType]})`);
    });
    const published = s.versions.some((v) => v.status === 'published');
    const f = h('form', { method: 'post', action: '/admin/' },
      h('fieldset', {}, h('legend', { text: `${s.title} (${s.surveyId})` }),
        published ? null : h('p', { class: 'hint', text: 'Ingen publiceret version endnu – koder kræver en publiceret version.' }),
        h('div', { class: 'check-list' }, boxes)), e,
      h('button', { type: 'submit', class: 'secondary', text: 'Gem tildeling' }));
    f.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const unitIds = boxes.map((b) => b.querySelector('input')).filter((x) => x.checked).map((x) => x.value);
      const r = await guard(() => api('PUT', `/api/admin/surveys/${s.id}/assignments`, { unitIds }), e);
      if (r) { s.assignedUnitIds = r.assignedUnitIds; announce(`Tildeling gemt for ${s.title}`); }
    });
    return f;
  });
  return h('section', { class: 'card' }, h('h3', { text: 'Tildeling til institutioner' }), intro, forms);
}

function renderPreview(out, r, doc) {
  clear(out);
  if (!r.valid) {
    out.append(h('h4', { text: `Valideringsfejl (${r.errors.length})` }), h('ul', { class: 'error' }, r.errors.map((x) => h('li', { text: x }))));
    return;
  }
  const p = r.preview;
  out.append(h('h4', { text: 'Preview' }), h('dl', { class: 'info' },
    [['Titel', p.title], ['Items (adfærdsbeskrivelser)', p.items], ['Spørgsmål', p.questions], ['Domæner', p.domains],
    ['Subskalaer', p.subscales], ['Spørgsmål pr. subskala', JSON.stringify(p.questionsPerSubscale)], ['Reverse-scorede', p.reverseScored],
    ['Baggrundsvariable', p.backgroundVariables.join(', ') || '–'], ['Estimeret svartid', `${p.estimatedMinutes} min`]]
    .flatMap(([k, v]) => [h('dt', { text: k }), h('dd', { text: String(v) })])),
    h('button', { type: 'button', text: 'Gem som kladde', onclick: async () => {
      const s2 = await guard(() => api('POST', '/api/admin/surveys/import', { tenantId: app.tenantId, document: doc, dryRun: false }));
      if (s2?.stored) { announce(`Gemt som version ${s2.versionNo}`); await loadTenantData(); shell(); }
    } }));
}

// ------------------------------------------------------------------ Institutioner og afdelinger
function unitsTab(panel) {
  const org = isOrgAdmin();
  const e1 = err('inst-err');
  const iname = h('input', { type: 'text', required: true, maxlength: 200 });
  const ityp = h('select', {}, Object.entries(UNIT_TYPES).map(([k, v]) => h('option', { value: k, text: v })));
  const instForm = h('form', { method: 'post', action: '/admin/' },
    h('div', { class: 'filters' }, field('Navn', iname, 'Fx "Nordskolen" eller "Børnehuset Solsikken"'), field('Type', ityp)), e1,
    h('button', { type: 'submit', text: 'Opret institution' }));
  instForm.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const r = await guard(() => api('POST', `/api/admin/tenants/${app.tenantId}/units`, { name: iname.value, unitType: ityp.value }), e1);
    if (r) { announce(`Institution ${r.name} oprettet`); await loadTenantData(); shell(); }
  });

  const insts = app.units.filter((u) => !u.parentId).sort((a, b) => a.name.localeCompare(b.name, 'da'));
  const e2 = err('sub-err');
  const parent = h('select', { required: true }, insts.map((i) => h('option', { value: i.id, text: `${i.name} (${UNIT_TYPES[i.unitType]})` })));
  const sname = h('input', { type: 'text', required: true, maxlength: 200 });
  const subForm = h('form', { method: 'post', action: '/admin/' },
    h('div', { class: 'filters' }, field('Institution', parent), field('Navn', sname, 'Fx "3.A", "Vuggestuen" eller "Udskolingen"')), e2,
    h('button', { type: 'submit', text: 'Opret afdeling/klasse' }));
  subForm.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const r = await guard(() => api('POST', `/api/admin/tenants/${app.tenantId}/units`, { name: sname.value, parentId: parent.value }), e2);
    if (r) { announce(`${r.name} oprettet`); await loadTenantData(); shell(); }
  });

  const removeBtn = (u) => h('button', { type: 'button', class: 'secondary', text: 'Fjern', 'aria-label': `Fjern ${u.name}`,
    onclick: async () => {
      if (!confirm(`Fjern "${u.name}" fra ${u.parentName || 'institutionen'}?\n\n`
        + 'Indsamlede svar bevares og tælles fremover med under institutionen. '
        + 'Adgangskoder til afdelingen/klassen deaktiveres, og afdelingsadmin-adgang til den fjernes.')) return;
      const r = await guard(() => api('POST', `/api/admin/tenants/${app.tenantId}/units/${u.id}/delete`, {}));
      if (r) { announce(`${u.name} fjernet`); await loadTenantData(); shell(); }
    } });
  const rows = unitsSorted().map((u) => u.parentId
    ? h('tr', { class: 'child' }, h('th', { scope: 'row' }, h('span', { class: 'indent', 'aria-hidden': 'true', text: '└ ' }), u.name),
        h('td', { text: 'Afdeling/klasse' }), h('td', { text: UNIT_TYPES[u.unitType] }), h('td', { text: u.status }),
        org ? h('td', {}, removeBtn(u)) : null)
    : row(u.name, ['Institution', UNIT_TYPES[u.unitType], u.status, ...(org ? [''] : [])]));
  const assignedTitles = (instId) => app.surveys.filter((s) => (s.assignedUnitIds || []).includes(instId)).map((s) => s.title).join(', ') || '–';
  rows.forEach((tr, i) => {
    const u = unitsSorted()[i];
    tr.children[3].after(h('td', { text: u.parentId ? '' : assignedTitles(u.id) }));
  });
  panel.append(heading('units', 'Institutioner og afdelinger'),
    h('p', { class: 'hint', text: 'Opret først institutionen (skole, dagtilbud …) og derefter dens afdelinger eller klasser. '
      + 'Resultater kan ses samlet for institutionen og sammenlignet mellem dens afdelinger/klasser. '
      + 'Adgangskoder kan udstedes til en afdeling/klasse eller til hele institutionen.' }),
    org ? h('section', { class: 'card' }, h('h3', { text: 'Ny institution' }), instForm) : null,
    org && insts.length ? h('section', { class: 'card' }, h('h3', { text: 'Ny afdeling eller klasse' }), subForm) : null,
    table('Institutioner og afdelinger', ['Navn', 'Niveau', 'Type', 'Status', 'Spørgeskemaer', ...(org ? ['Handling'] : [])], rows));
}

// ------------------------------------------------------------------ Koder
async function codesTab(panel) {
  const e = err('code-err');
  const sv = versionSelect('code-sv');
  const validTo = h('input', { type: 'date' });
  const label = h('input', { type: 'text', maxlength: 100 });
  const total = h('output', { text: '0' });
  const inputs = new Map();
  const units = unitsSorted();
  const hasKids = new Set(units.filter((u) => u.parentId).map((u) => u.parentId));
  const updateTotal = () => {
    total.textContent = String([...inputs.values()].reduce((a, i) => a + (Number(i.value) || 0), 0));
  };
  const countRows = units.map((u) => {
    const inp = h('input', { type: 'number', min: 0, max: 500, step: 1, inputmode: 'numeric', class: 'count-input',
      'aria-label': `Antal koder til ${unitLabel(u)}`, placeholder: '0' });
    inp.addEventListener('input', updateTotal);
    inputs.set(u.id, inp);
    const name = u.parentId
      ? [h('span', { class: 'indent', 'aria-hidden': 'true', text: '└ ' }), u.name]
      : [u.name, hasKids.has(u.id) ? h('span', { class: 'hint', text: ' (hele institutionen)' }) : null];
    const tr = h('tr', { class: u.parentId ? 'child' : '' }, h('th', { scope: 'row' }, ...name), h('td', {}, inp));
    tr.dataset.inst = u.parentId || u.id;
    return tr;
  });
  // Kun institutioner, som det valgte spørgeskema er tildelt (og deres afdelinger/klasser), vises
  const noneAssigned = h('p', { class: 'notice', hidden: true,
    text: 'Spørgeskemaet er ikke tildelt nogen institution. Tildel det under Spørgeskemaer.' });
  const applyAssignment = () => {
    const v = publishedVersions().find((x) => x.id === sv.value);
    const ok = new Set(v ? v.assignedUnitIds : []);
    for (const tr of countRows) {
      const show = ok.has(tr.dataset.inst);
      tr.hidden = !show;
      if (!show) tr.querySelector('input').value = '';
    }
    noneAssigned.hidden = ok.size > 0;
    updateTotal();
  };
  sv.addEventListener('change', applyAssignment);
  const btn = h('button', { type: 'submit' }, icon('download', 'icon-sm'), 'Generér koder og hent PDF');
  const form = h('form', { method: 'post', action: '/admin/' },
    h('p', { class: 'hint', text: 'Hver kode er personlig og giver én besvarelse. Deltageren kan logge ind igen med koden for at '
      + 'fortsætte, trække sin besvarelse tilbage og svare forfra. PDF\'en har en forside til den ansvarlige for hver afdeling '
      + 'og derefter én side pr. kode med vejledning, kode og QR-kode. Højst 1000 koder ad gangen.' }),
    h('div', { class: 'filters' }, field('Spørgeskema', sv), field('Gyldig til', validTo, 'Tom = 60 dage'),
      field('Etiket (valgfri)', label, 'Fx "Forår 2027"')),
    noneAssigned, table('Antal koder pr. afdeling', ['Institution / afdeling', 'Antal'], countRows),
    h('p', {}, 'Koder i alt: ', total), e, btn);
  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const items = [...inputs].map(([unitId, i]) => ({ unitId, count: Number(i.value) || 0 })).filter((x) => x.count > 0);
    if (!items.length) { e.textContent = 'Angiv antal koder for mindst én afdeling.'; return; }
    btn.disabled = true;
    announce('Genererer koder – det tager ca. et minut pr. 1000 koder…');
    try {
      const res = await guard(() => api('POST', '/api/admin/access-codes', {
        surveyVersionId: sv.value, units: items, label: label.value || null,
        validTo: validTo.value ? `${validTo.value}T23:59:59Z` : null }, { raw: true }), e);
      if (!res) return;
      const blob = await res.blob();
      const name = /filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') || '')?.[1] || 'adgangskoder.pdf';
      const a = h('a', { href: URL.createObjectURL(blob), download: name });
      document.body.append(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 60000);
      announce('PDF hentet. Koderne kan ikke vises igen – gem filen sikkert.');
      inputs.forEach((i) => { i.value = ''; }); updateTotal();
      refresh();
    } finally { btn.disabled = false; }
  });
  const list = h('div');
  const openBlocks = new Set();
  const refresh = async () => {
    const codes = await guard(() => api('GET', `/api/admin/access-codes?tenantId=${app.tenantId}`));
    if (!codes) return;
    clear(list).append(...codeBatches(codes, openBlocks, refresh));
  };
  panel.append(heading('codes', 'Adgangskoder'),
    units.length ? h('section', { class: 'card' }, form) : h('p', { class: 'notice', text: 'Opret først institutioner og afdelinger.' }), list);
  applyAssignment();
  refresh();
}

/** Udstedte koder samlet pr. bestilling (nyeste først) og derefter i afdelingsblokke i bestilt rækkefølge. */
function codeBatches(codes, openBlocks, refresh) {
  if (!codes.length) return [h('p', { class: 'hint', text: 'Der er ikke udstedt koder endnu.' })];
  const uname = Object.fromEntries(app.units.map((u) => [u.id, unitLabel(u)]));
  const svTitle = Object.fromEntries(app.surveys.flatMap((s) => s.versions.map((v) => [v.id, `${s.title} v${v.versionNo}`])));
  const batches = new Map();
  for (const c of codes) {
    const key = c.batchId || `single-${c.id}`;
    if (!batches.has(key)) batches.set(key, { id: c.batchId, created: c.createdAt, sv: c.surveyVersionId, validTo: c.validTo, codes: [] });
    const b = batches.get(key);
    if (c.createdAt < b.created) b.created = c.createdAt;
    b.codes.push(c);
  }
  const sorted = [...batches.values()].sort((a, b) => b.created.localeCompare(a.created));
  const sum = (arr, k) => arr.reduce((a, c) => a + c[k], 0);
  return [h('h3', { text: 'Udstedte koder' }), ...sorted.map((b) => {
    const blocks = new Map();
    for (const c of b.codes) {
      if (!blocks.has(c.unitId)) blocks.set(c.unitId, { unitId: c.unitId, pos: c.batchPos ?? 9999, codes: [] });
      blocks.get(c.unitId).codes.push(c);
    }
    const ordered = [...blocks.values()].sort((x, y) => x.pos - y.pos || (uname[x.unitId] || '').localeCompare(uname[y.unitId] || '', 'da'));
    const prefix = (b.codes[0].label || '').split(' · nr. ')[0];
    const label = /^nr\. /.test(b.codes[0].label || '') ? '' : prefix;
    const active = b.codes.filter((c) => c.status === 'active').length;
    const disableBtn = (unitId, n, what) => (n && b.id ? h('button', { type: 'button', class: 'secondary', text: `Deaktivér ${what}`,
      onclick: async () => {
        if (!confirm(`Deaktivér ${n} aktive koder (${what})? Deltagere kan så ikke længere logge ind med dem.`)) return;
        const r = await guard(() => api('POST', `/api/admin/access-codes/batches/${b.id}/disable`, { tenantId: app.tenantId, unitId }));
        if (r) { announce(`${r.disabled} koder deaktiveret`); refresh(); }
      } }) : null);
    const blockEls = ordered.map((bl) => {
      const key = `${b.id || b.codes[0].id}:${bl.unitId}`;
      bl.codes.sort((x, y) => (x.seqNo ?? 0) - (y.seqNo ?? 0) || x.createdAt.localeCompare(y.createdAt));
      const act = bl.codes.filter((c) => c.status === 'active').length;
      const det = h('details', { class: 'code-block', open: openBlocks.has(key) },
        h('summary', {}, h('strong', { text: uname[bl.unitId] || 'Fjernet afdeling' }),
          h('span', { class: 'hint', text: ` · ${bl.codes.length} koder · ${sum(bl.codes, 'starts')} startet · `
            + `${sum(bl.codes, 'completions')} fuldført${act < bl.codes.length ? ` · ${bl.codes.length - act} deaktiveret` : ''}` })),
        table(`Koder – ${uname[bl.unitId] || ''}`, ['Nr.', 'Starter', 'Fuldførte', 'Status', ''],
          bl.codes.map((c) => row(c.seqNo != null ? String(c.seqNo) : '–', [String(c.starts), String(c.completions),
            c.status === 'active' ? 'Aktiv' : 'Deaktiveret',
            h('td', {}, c.status === 'active' ? h('button', { type: 'button', class: 'secondary', text: 'Deaktivér',
              onclick: async () => { await guard(() => api('POST', `/api/admin/access-codes/${c.id}/disable`, {})); refresh(); } }) : '')]))),
        h('div', { class: 'actions' }, disableBtn(bl.unitId, act, 'blokken')));
      det.addEventListener('toggle', () => { if (det.open) openBlocks.add(key); else openBlocks.delete(key); });
      return det;
    });
    return h('section', { class: 'card code-batch' },
      h('div', { class: 'batch-head' },
        h('div', {},
          h('h4', { text: `Bestilling ${new Date(b.created).toLocaleString('da-DK', { dateStyle: 'medium', timeStyle: 'short' })}${label ? ` · ${label}` : ''}` }),
          h('p', { class: 'hint', text: `${svTitle[b.sv] || 'Spørgeskema'} · ${b.codes.length} koder i ${ordered.length} `
            + `${ordered.length === 1 ? 'afdeling' : 'afdelinger'} · gyldige til ${new Date(b.validTo).toLocaleDateString('da-DK')}` })),
        disableBtn(null, active, 'hele bestillingen')),
      blockEls);
  })];
}

// ------------------------------------------------------------------ Analyser
function analysesTab(panel) {
  const e = err('an-err');
  const kind = h('select', { id: 'an-kind' }, [['reliability', 'Reliabilitet (alfa, omega, item-total)'],
    ['group_comparison', 'Skole vs dagtilbud (Welch/ANOVA/mixed model)'], ['team_level', 'Teamniveau (ICC, rwg(j))'],
    ['screening', 'Datascreening (hurtige svar, straightlining)']].map(([k, v]) => h('option', { value: k, text: v })));
  const list = h('div');
  const detail = h('div');
  panel.append(heading('analyses', 'Analyser'), h('section', { class: 'card' }, field('Analyse', kind),
    publishedVersions().length ? filterForm(async (f, thr) => {
      const params = kind.value === 'group_comparison' ? { covariates: ['profession', 'experience'], subscaleThreshold: thr }
        : kind.value === 'reliability' ? { bootstrap: 1000 } : { subscaleThreshold: thr };
      if (kind.value === 'screening') delete params.subscaleThreshold;
      const r = await guard(() => api('POST', '/api/admin/analyses', { tenantId: app.tenantId, kind: kind.value, filters: f, params }), e);
      if (r) { announce('Analysen er sat i kø'); refresh(); poll(r.id); }
    }, { withThresholds: true }) : null, e), list, detail);
  const poll = async (id) => {
    for (let i = 0; i < 120; i++) {
      const r = await api('GET', `/api/admin/analyses/${id}`).catch(() => null);
      if (r && (r.status === 'done' || r.status === 'failed')) { refresh(); renderRun(detail, r); return; }
      await new Promise((res) => setTimeout(res, 1500));
    }
  };
  const refresh = async () => {
    const runs = await guard(() => api('GET', `/api/admin/analyses?tenantId=${app.tenantId}`));
    if (!runs) return;
    clear(list).append(table('Kørsler', ['Type', 'Status', 'Bestilt', 'Data-hash', ''], runs.map((r) => row(r.kind, [r.status,
      new Date(r.requestedAt).toLocaleString('da-DK'), r.dataSha256 ? r.dataSha256.slice(0, 12) + '…' : '–',
      h('td', {}, h('button', { type: 'button', class: 'secondary', text: 'Vis', onclick: async () => renderRun(detail, await api('GET', `/api/admin/analyses/${r.id}`)) }))]))));
  };
  refresh();
}

function flags(list) { return (list || []).map((f) => h('span', { class: 'flag', text: f })); }

function renderRun(out, r) {
  clear(out);
  const res = r.result;
  out.append(h('h3', { text: `Resultat: ${r.kind} (${r.status})` }));
  if (r.status === 'failed') { out.append(h('p', { class: 'error', text: r.error })); return; }
  if (!res) return;
  if (res.suppressed) { out.append(h('p', { class: 'notice', text: res.reason })); return; }
  if (r.kind === 'reliability') {
    out.append(table('Reliabilitet pr. subskala', ['Subskala', 'Items', 'Komplette', 'Alfa', '95 % CI (bootstrap)', 'Omega total', 'Gns. inter-item r', 'Flag'],
      res.bySubscale.map((b) => row(b.subscale, [b.nItems, b.nComplete, fmt(b.alpha, 3), b.alphaCi95 ? `${fmt(b.alphaCi95[0], 3)}–${fmt(b.alphaCi95[1], 3)}` : '–',
        fmt(b.omegaTotal, 3), fmt(b.meanInterItemR, 3), h('td', {}, flags(b.flags))]))),
    table('Reliabilitet pr. subskala × domæne', ['Subskala', 'Domæne', 'Items', 'Alfa', 'Omega', 'Gns. r'],
      res.bySubscaleDomain.map((b) => row(b.subscale, [b.domain, b.nItems, fmt(b.alpha, 3), fmt(b.omegaTotal, 3), fmt(b.meanInterItemR, 3)]))));
    for (const b of res.bySubscale) {
      out.append(h('details', {}, h('summary', { text: `Itemstatistik: ${b.subscale}` }),
        table(`Items ${b.subscale}`, ['Item', 'Middel', 'SD', 'Korr. item-total', 'Alfa hvis slettet', 'Flag'],
          (b.items || []).map((it) => row(it.item, [fmt(it.mean), fmt(it.sd), fmt(it.itemTotalR, 3), fmt(it.alphaIfDeleted, 3), h('td', {}, flags(it.flags))])))));
    }
  } else if (r.kind === 'group_comparison') {
    out.append(table('Skole vs dagtilbud pr. subskala', ['Subskala', 'Anbefalet', 'Welch F (df) p', 'ANOVA F p', 'η² / ω²', 'Levene p', 'Kruskal-Wallis p', 'Hedges g [95 % CI]'],
      res.bySubscale.map((b) => b.suppressed ? row(b.subscale, [h('td', { class: 'suppressed', colspan: 7, text: b.reason })]) :
        row(b.subscale, [b.recommended, `${fmt(b.welchAnova.F)} (${fmt(b.welchAnova.df1, 0)}, ${fmt(b.welchAnova.df2, 1)}) p=${fmt(b.welchAnova.p, 4)}`,
          `${fmt(b.classicAnova.F)} p=${fmt(b.classicAnova.p, 4)}`, `${fmt(b.classicAnova.etaSquared, 3)} / ${fmt(b.classicAnova.omegaSquared, 3)}`,
          fmt(b.levene.p, 3), fmt(b.kruskalWallis.p, 4), b.hedgesG ? `${fmt(b.hedgesG.g)} [${fmt(b.hedgesG.ci95[0])}; ${fmt(b.hedgesG.ci95[1])}]` : '–']))));
    const mm = res.mixedModel;
    if (mm && !mm.suppressed) {
      out.append(h('h4', { text: `Mixed model: ${mm.formula} + (1|afdeling)` }),
        h('p', { class: 'hint', text: `Afdelinger: ${mm.nGroups}, observationer: ${mm.nObs}, konvergeret: ${mm.converged ? 'ja' : 'nej'}, afdelingsvarians: ${fmt(mm.groupVariance, 3)}` }),
        flags(mm.warnings), h('p', { class: 'hint', text: mm.note || '' }),
        mm.fixedEffects ? table('Faste effekter', ['Term', 'Estimat', 'SE', 'p', '95 % CI'], mm.fixedEffects.map((f) => row(f.term, [fmt(f.estimate, 3), fmt(f.se, 3), fmt(f.p, 4), `${fmt(f.ci95[0], 3)}; ${fmt(f.ci95[1], 3)}`]))) : null);
    }
    for (const b of res.bySubscale.filter((x) => !x.suppressed)) {
      out.append(h('details', {}, h('summary', { text: `Antagelser og post hoc: ${b.subscale}` }),
        h('ul', {}, (b.assumptions || []).map((a) => h('li', { text: a }))),
        b.recommendedNote ? h('p', { class: 'flag', text: b.recommendedNote }) : null,
        h('p', { text: `Shapiro-Wilk på residualer: p=${fmt(b.shapiroResiduals?.p, 4)}, skævhed ${fmt(b.residualSkew)}` }),
        table('Post hoc', ['Par', 'Metode', 'Forskel', '95 % CI', 'p (justeret)'], (b.posthoc || []).map((p) => row(`${p.a} – ${p.b}`, [p.method, fmt(p.diff, 3), `${fmt(p.ci95[0], 3)}; ${fmt(p.ci95[1], 3)}`, fmt(p.pAdj, 4)])))));
    }
  } else if (r.kind === 'team_level') {
    out.append(table('ICC og enighed', ['Subskala', 'ICC(1)', 'ICC(2)', 'Afdelinger', 'Median rwg(j)', 'Anbefaling'],
      res.bySubscale.map((b) => row(b.subscale, [fmt(b.icc1, 3), fmt(b.icc2, 3), b.nGroups, fmt(b.rwgJMedian, 2), b.aggregationAdvice]))));
  } else {
    out.append(h('dl', { class: 'info' }, [['Respondenter', res.nRespondents], ['Median svartid (ms)', fmt(res.sampleMedianRtMs, 0)],
      ['Hurtige respondenter (flag)', res.fastResponders], ['Straightlining (flag)', res.straightliners],
      ['Regler', JSON.stringify(res.rules)], ['Bemærk', res.note]].flatMap(([k, v]) => [h('dt', { text: k }), h('dd', { text: String(v) })])));
  }
  out.append(h('details', {}, h('summary', { text: 'Analyseprotokol' }), h('pre', { class: 'json', text: JSON.stringify({ ...res.protocol, software: r.software }, null, 2) })));
}

// ------------------------------------------------------------------ Eksport
function exportsTab(panel) {
  const e = err('ex-err');
  const fmtSel = h('select', { id: 'ex-fmt' }, [['report_html', 'Rapport (HTML)'], ['long_csv', 'CSV – long (én række pr. svar)'],
    ['wide_csv', 'CSV – wide (én række pr. besvarelse)'], ['codebook_json', 'Kodebog (JSON)'], ['protocol_json', 'Analyseprotokol (JSON)']]
    .map(([k, v]) => h('option', { value: k, text: v })));
  panel.append(heading('exports', 'Eksport'),
    h('p', { class: 'hint', text: 'Kræver eksportrettighed. Eksporter indeholder aldrig adgangskoder eller direkte identifikatorer. Alle eksporter auditeres.' }),
    h('section', { class: 'card' }, field('Format', fmtSel), publishedVersions().length ? filterForm(async (f) => {
      await guard(async () => {
        const res = await api('POST', '/api/admin/exports', { tenantId: app.tenantId, format: fmtSel.value, filters: f }, { raw: true });
        const blob = await res.blob();
        const name = (res.headers.get('Content-Disposition') || '').match(/filename="([^"]+)"/)?.[1] || 'eksport';
        const a = h('a', { href: URL.createObjectURL(blob), download: name });
        document.body.append(a); a.click(); a.remove();
        announce(`Downloadet ${name}`);
      }, e);
    }) : null, e));
}

// ------------------------------------------------------------------ Brugere
async function usersTab(panel) {
  const e = err('usr-err');
  const uname = h('input', { type: 'text', required: true, pattern: '[a-z0-9._@\\-]{3,100}', autocomplete: 'off', autocapitalize: 'none' });
  const role = h('select', {}, h('option', { value: 'unit_admin', text: 'Afdelingsadmin' }), h('option', { value: 'org_admin', text: 'Organisationsadmin' }));
  const unit = h('select', { multiple: true, size: 6 }, unitOptions());
  const exp = h('input', { type: 'checkbox', id: 'u-exp' });
  const result = h('div');
  const form = h('form', { method: 'post', action: '/admin/' }, h('div', { class: 'filters' }, field('Brugernavn', uname, 'Små bogstaver, tal og . _ @ -'), field('Rolle', role), field('Institutioner/afdelinger (afdelingsadmin)', unit, 'En institution giver adgang til alle dens afdelinger/klasser')),
    h('p', {}, exp, ' ', h('label', { for: 'u-exp', text: 'Må eksportere' })), e, h('button', { type: 'submit', text: 'Opret bruger' }));
  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const r = await guard(() => api('POST', '/api/admin/users', { username: uname.value, role: role.value, tenantId: app.tenantId,
      unitIds: [...unit.selectedOptions].map((o) => o.value), canExport: exp.checked }), e);
    if (r) { clear(result).append(h('p', { class: 'notice', text: `Engangsadgangskode for ${r.username} (vises kun nu): ` }, h('code', { text: r.initialPassword }))); load(); }
  });
  const list = h('div');
  const load = async () => {
    const users = await guard(() => api('GET', `/api/admin/tenants/${app.tenantId}/users`));
    if (users) clear(list).append(table('Brugere', ['Brugernavn', 'Roller', 'MFA', 'Status'], users.map((u) => row(u.username,
      [u.scopes.map((x) => x.role + (x.canExport ? ' (eksport)' : '')).join(', '), u.mfaEnrolled ? 'ja' : 'nej', u.status]))));
  };
  panel.append(heading('users', 'Brugere'), h('section', { class: 'card' }, form, result), list);
  load();
}

// ------------------------------------------------------------------ Audit og tenants
async function auditTab(panel) {
  const q = app.tenantId ? `?tenantId=${app.tenantId}` : '';
  const verify = h('div');
  if (app.who.systemAdmin) {
    verify.append(h('button', { type: 'button', class: 'secondary', text: 'Verificér hash-kæde', onclick: async () => {
      const r = await guard(() => api('GET', '/api/admin/audit/verify'));
      if (r) clear(verify).append(h('p', { class: r.ok ? 'notice' : 'error', text: r.ok ? `Kæden er intakt (${r.checked} hændelser).` : `Brud ved hændelse ${r.brokenAt}!` }));
    } }));
  }
  const ev = await guard(() => api('GET', `/api/admin/audit${q}`)) || [];
  panel.append(heading('audit', 'Auditlog'), verify, table('Seneste hændelser', ['Tid', 'Handling', 'Aktør', 'Mål', 'Detaljer'],
    ev.map((x) => row(new Date(x.at).toLocaleString('da-DK'), [x.action, `${x.actorType}${x.actorId ? ' ' + x.actorId.slice(0, 8) : ''}`,
      x.targetType ? `${x.targetType} ${String(x.targetId || '').slice(0, 8)}` : '', JSON.stringify(x.details).slice(0, 120)]))));
}

async function tenantsTab(panel) {
  const e = err('ten-err');
  const name = h('input', { type: 'text', required: true });
  const k = h('input', { type: 'number', min: 5, max: 100, value: 10 });
  const ret = h('input', { type: 'number', min: 1, max: 120, value: 24 });
  const orgUser = h('input', { type: 'text', autocomplete: 'off', autocapitalize: 'none' });
  const result = h('div');
  if (app.flash) { result.append(app.flash); app.flash = null; }
  const form = h('form', { method: 'post', action: '/admin/' }, h('div', { class: 'filters' }, field('Navn', name), field('Min. cellestørrelse', k), field('Opbevaring (måneder)', ret),
    field('Første organisationsadmin (brugernavn)', orgUser)), e, h('button', { type: 'submit', text: 'Opret tenant' }));
  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    await guard(async () => {
      const t = await api('POST', '/api/admin/tenants', { name: name.value, minCellSize: Number(k.value), retentionMonths: Number(ret.value) });
      if (orgUser.value) {
        const u = await api('POST', '/api/admin/users', { username: orgUser.value, role: 'org_admin', tenantId: t.id, canExport: false });
        // shell() gentegner fanen – gem beskeden så den overlever gentegningen (vises kun én gang)
        app.flash = h('p', { class: 'notice', role: 'status', text: `Engangsadgangskode for ${u.username} (vises kun nu – log ud og log ind som denne bruger for at oprette spørgeskemaer): ` }, h('code', { text: u.initialPassword }));
      }
      app.allTenants = await api('GET', '/api/admin/tenants');
      shell();
    }, e);
  });
  panel.append(heading('tenants', 'Tenants'),
    h('p', { class: 'hint', text: 'Systemadministratorer kan ikke som standard se besvarelser.' }),
    h('section', { class: 'card' }, form, result),
    table('Tenants', ['Navn', 'Min. celle', 'Opbevaring (mdr.)', 'Status', 'Handling'], app.allTenants.map((t) => row(t.name, [t.minCellSize, t.retentionMonths, t.status,
      h('td', {}, h('button', { type: 'button', class: 'secondary', 'aria-label': `Slet tenant ${t.name}`, onclick: () => deleteTenant(t, e) }, icon('trash-2', 'icon-sm'), 'Slet'))]))));
}

async function deleteTenant(t, e) {
  const typed = window.prompt(`Slet tenant "${t.name}" PERMANENT?\n\nAlle afdelinger, spørgeskemaer, adgangskoder, besvarelser og analyser slettes, `
    + 'og brugere der kun har adgang til denne tenant fjernes. Auditloggen bevares. Handlingen kan ikke fortrydes.\n\n'
    + 'Skriv tenantens navn for at bekræfte:');
  if (typed === null) return;
  if (typed.trim() !== t.name) { e.textContent = 'Navnet matchede ikke – intet blev slettet.'; return; }
  const r = await guard(() => api('POST', `/api/admin/tenants/${t.id}/delete`, { confirmName: typed.trim() }), e);
  if (!r) return;
  announce(`Tenant ${t.name} er slettet`);
  app.allTenants = await api('GET', '/api/admin/tenants');
  app.tenants = app.allTenants.filter((x) => app.tenants.some((y) => y.id === x.id));
  if (app.tenantId === t.id) { app.tenantId = app.tenants[0]?.id || null; await loadTenantData(); }
  shell();
}

// ------------------------------------------------------------------ Opstart
async function boot() {
  let me;
  try { me = await api('GET', '/api/admin/auth/me'); } catch { return loginView(); }
  setCsrf(me.csrfToken);
  if (!me.mfaPassed) return mfaView(!me.mfaEnrolled);
  if (me.mustChangePassword) return passwordView();
  app.me = me;
  app.who = await api('GET', '/api/admin/auth/whoami');
  app.allTenants = await api('GET', '/api/admin/tenants');
  app.tenants = app.allTenants.filter((t) => app.who.tenants.includes(t.id));
  app.tenantId = app.tenants[0]?.id || null;
  await loadTenantData();
  shell();
}
boot();
