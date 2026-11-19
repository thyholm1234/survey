import { api, ApiError } from './api.js';
import { h, clear } from './dom.js';
import { t } from './i18n.js';

const view = document.getElementById('view');
const main = document.getElementById('main');
const statusEl = document.getElementById('status');
const reminder = document.getElementById('reminder');
const reminderText = document.getElementById('reminder-text');

const st = {
  intro: null, ticket: null, responseId: null, data: null,
  pages: [], pageIdx: 0, maxPageIdx: 0, seq: new Map(), saving: 0,
};

function announce(msg) { statusEl.textContent = ''; requestAnimationFrame(() => { statusEl.textContent = msg; }); }

function show(...nodes) {
  clear(view).append(...nodes);
  const heading = view.querySelector('h1, h2');
  if (heading) { heading.setAttribute('tabindex', '-1'); heading.focus({ preventScroll: false }); }
  else main.focus();
}

function errorBox(id) { return h('p', { id, class: 'error', role: 'alert' }); }

function browserClass() {
  const brands = navigator.userAgentData?.brands?.map((b) => b.brand.toLowerCase()) || [];
  if (brands.some((b) => b.includes('chromium'))) return 'chromium';
  const ua = navigator.userAgent;
  if (/Firefox\//.test(ua)) return 'firefox';
  if (/Chrome\//.test(ua) || /Edg\//.test(ua)) return 'chromium';
  if (/Safari\//.test(ua)) return 'safari';
  return 'other';
}
function screenClass() { const w = window.innerWidth; return w < 600 ? 's' : w < 1100 ? 'm' : 'l'; }

// ---------------------------------------------------------------- Kode
function codeView(message) {
  const err = errorBox('code-error');
  const input = h('input', {
    id: 'code', name: 'code', type: 'text', class: 'code', required: true, minlength: 6, maxlength: 40,
    autocomplete: 'one-time-code', autocapitalize: 'characters', autocorrect: 'off', spellcheck: 'false',
    enterkeyhint: 'go', 'aria-describedby': 'code-hint code-error',
  });
  input.addEventListener('input', () => { input.setCustomValidity(''); input.removeAttribute('aria-invalid'); err.textContent = ''; });
  const btn = h('button', { type: 'submit', text: t('codeSubmit') });
  const form = h('form', { method: 'post', action: '/', novalidate: true, 'aria-labelledby': 'code-h' },
    h('div', { class: 'field' },
      h('label', { for: 'code', text: t('codeLabel') }), input,
      h('span', { id: 'code-hint', class: 'hint', text: t('codeHint') })),
    err, btn);
  if (message) err.textContent = message;
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!input.value.trim()) {
      input.setAttribute('aria-invalid', 'true'); err.textContent = t('codeRequired'); input.focus(); return;
    }
    btn.disabled = true;
    try {
      const res = await api('POST', '/api/respondent/access-code/verify', { code: input.value });
      st.intro = res; st.ticket = res.ticket;
      infoView();
    } catch (ex) {
      input.setAttribute('aria-invalid', 'true');
      err.textContent = ex instanceof ApiError && ex.message ? ex.message : t('genericError');
      input.focus();
    } finally { btn.disabled = false; }
  });
  const resumeBtn = h('button', { type: 'button', class: 'secondary', text: t('resumeLink'), onclick: () => resumeView() });
  show(h('section', { class: 'card' }, h('h1', { id: 'code-h', text: t('appTitle') }), form),
    h('p', {}, resumeBtn));
}

function resumeView() {
  const err = errorBox('resume-error');
  const input = h('input', { id: 'resume', name: 'resume', type: 'text', class: 'code', required: true, maxlength: 40,
    autocomplete: 'off', autocapitalize: 'characters', autocorrect: 'off', spellcheck: 'false', 'aria-describedby': 'resume-error' });
  const btn = h('button', { type: 'submit', text: t('resumeSubmit') });
  const form = h('form', { method: 'post', action: '/', novalidate: true },
    h('div', { class: 'field' }, h('label', { for: 'resume', text: t('resumeLabel') }), input), err,
    h('div', { class: 'actions' }, h('button', { type: 'button', class: 'secondary', text: t('prev'), onclick: () => codeView() }), btn));
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    btn.disabled = true;
    try {
      const r = await api('POST', '/api/respondent/resume', { resumeKey: input.value });
      await loadSurvey(r.responseId);
    } catch (ex) {
      input.setAttribute('aria-invalid', 'true');
      err.textContent = ex.message || t('genericError'); input.focus();
    } finally { btn.disabled = false; }
  });
  show(h('section', { class: 'card' }, h('h1', { text: t('resumeLabel') }), form));
}

// ---------------------------------------------------------------- Information og samtykke
function infoView() {
  const i = st.intro;
  const dl = h('dl', { class: 'info' });
  for (const key of ['purpose', 'voluntary', 'pseudonymity', 'dataController', 'retention', 'contact']) {
    if (i.info[key]) dl.append(h('dt', { text: t(key) }), h('dd', { text: i.info[key] }));
  }
  const bgFields = (i.backgroundVariables || []).map((b) => {
    const id = `bg-${b.code}`;
    return h('div', { class: 'field' },
      h('label', { for: id, text: b.label }),
      h('select', { id, name: b.code },
        h('option', { value: '', text: t('preferNot') }),
        b.options.map((o) => h('option', { value: o.code, text: o.label }))));
  });
  const err = errorBox('consent-error');
  const consent = h('input', { type: 'checkbox', id: 'consent', name: 'consent', required: true, 'aria-describedby': 'consent-error' });
  const btn = h('button', { type: 'submit', text: t('start') });
  const form = h('form', { method: 'post', action: '/', novalidate: true },
    bgFields.length ? h('fieldset', { class: 'card' }, h('legend', { text: t('backgroundHeading') }), bgFields) : null,
    h('p', {}, consent, ' ', h('label', { for: 'consent', text: t('consent') })), err, btn);
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!consent.checked) { err.textContent = t('consentRequired'); consent.focus(); return; }
    const background = {};
    for (const b of i.backgroundVariables || []) {
      const v = form.elements[b.code].value; background[b.code] = v || null;
    }
    btn.disabled = true;
    try {
      const r = await api('POST', '/api/respondent/sessions', {
        ticket: st.ticket, consent: true, background,
        client: { browserClass: browserClass(), screenClass: screenClass() },
      });
      st.ticket = null;
      resumeKeyView(r.responseId, r.resumeKey);
    } catch (ex) {
      err.textContent = ex.message || t('genericError');
      if (ex.status === 400) setTimeout(() => codeView(ex.message), 1500);
    } finally { btn.disabled = false; }
  });
  show(h('section', { class: 'card' },
    h('h1', { text: i.title }),
    h('p', { class: 'lead', text: t('estimated', i.questions, i.estimatedMinutes) }),
    h('h2', { text: t('infoHeading') }), dl), form);
}

function resumeKeyView(responseId, key) {
  const copyBtn = h('button', { type: 'button', class: 'secondary', text: t('copy') });
  copyBtn.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(key); copyBtn.textContent = t('copied'); announce(t('copied')); } catch { /* manuelt */ }
  });
  show(h('section', { class: 'card' },
    h('h1', { text: t('resumeKeyHeading') }),
    h('p', { text: t('resumeKeyText') }),
    h('p', {}, h('output', { class: 'resume-key', text: key })),
    h('div', { class: 'actions' }, copyBtn,
      h('button', { type: 'button', text: t('continue'), onclick: () => loadSurvey(responseId) }))));
}

// ---------------------------------------------------------------- Besvarelse
const desktop = window.matchMedia('(min-width: 60rem)');

function buildPages() {
  const size = desktop.matches ? 3 : 1;
  const pages = [];
  let cur = [];
  let block = null;
  for (const o of st.data.order) {
    if (o.blockIndex !== block || cur.length === size) {
      if (cur.length) pages.push(cur);
      cur = []; block = o.blockIndex;
    }
    cur.push(o);
  }
  if (cur.length) pages.push(cur);
  st.pages = pages;
}

function pageOf(position) {
  const i = st.pages.findIndex((p) => p.some((o) => o.position === position));
  return i < 0 ? st.pages.length : i;
}

async function loadSurvey(responseId) {
  try {
    st.data = await api('GET', `/api/respondent/sessions/${encodeURIComponent(responseId)}/next`);
  } catch (ex) {
    if (ex.status === 401) return codeView(t('sessionExpired'));
    return codeView(t('genericError'));
  }
  st.responseId = responseId;
  if (st.data.status === 'completed') return doneView();
  for (const o of st.data.order) st.seq.set(o.questionId, o.seq || 0);
  buildPages();
  st.pageIdx = pageOf(st.data.resumePosition);
  st.maxPageIdx = st.pageIdx;
  renderPage();
}

desktop.addEventListener('change', () => {
  if (!st.data || st.pageIdx >= st.pages.length) return;
  const first = st.pages[st.pageIdx][0].position;
  buildPages();
  st.pageIdx = pageOf(first);
  st.maxPageIdx = Math.max(st.maxPageIdx, st.pageIdx);
  renderPage();
});

function setReminder(blockIndex) {
  const b = st.data.blocks[blockIndex];
  reminderText.textContent = b?.instruction || b?.name || '';
  reminder.hidden = !reminderText.textContent;
}

async function markShown(items) {
  const positions = items.filter((o) => !o.shown).map((o) => o.position);
  if (!positions.length) return;
  try {
    await api('POST', `/api/respondent/sessions/${st.responseId}/shown`, { positions });
    items.forEach((o) => { o.shown = true; });
  } catch (ex) { if (ex.status === 401) codeView(t('sessionExpired')); }
}

const queue = new Map();
let flushing = false;
async function flush() {
  if (flushing) return;
  flushing = true;
  try {
    while (queue.size) {
      const [qid, body] = queue.entries().next().value;
      try {
        await api('PUT', `/api/respondent/sessions/${st.responseId}/answers/${encodeURIComponent(qid)}`, body);
        if (queue.get(qid) === body) queue.delete(qid);
        announce(t('saved'));
        setSaveStatus(t('saved'));
      } catch (ex) {
        if (ex.status === 401) { queue.clear(); codeView(t('sessionExpired')); return; }
        if (ex.status && ex.status < 500 && ex.status !== 429) { queue.delete(qid); continue; }
        setSaveStatus(t('saveFailed'));
        await new Promise((r) => setTimeout(r, 2500));
      }
    }
  } finally { flushing = false; }
}
function setSaveStatus(text) { const el = document.getElementById('save-status'); if (el) el.textContent = text; }

function saveAnswer(o, value, missingCode) {
  o.value = value; o.missingCode = missingCode;
  const seq = (st.seq.get(o.questionId) || 0) + 1;
  st.seq.set(o.questionId, seq);
  const viaBack = st.pageIdx < st.maxPageIdx;
  queue.set(o.questionId, { value, missingCode, seq, viaBack });
  setSaveStatus(t('saving'));
  flush();
}

function itemFieldset(o, revisit) {
  const scale = st.data.scale;
  const name = `q-${o.position}`;
  const legendId = `${name}-legend`;
  const behId = `${name}-beh`;
  const opts = [];
  for (let v = scale.min; v <= scale.max; v++) {
    const lab = (scale.labels || []).find((l) => l.value === v)?.label || '';
    const input = h('input', { type: 'radio', name, value: String(v), id: `${name}-${v}` });
    if (o.value === v) input.checked = true;
    input.addEventListener('change', () => saveAnswer(o, v, null));
    opts.push(h('label', { class: 'opt', for: `${name}-${v}` }, input, h('span', {}, h('b', { text: String(v) }), lab)));
  }
  const likert = h('div', { class: 'likert' }, opts);
  likert.style.setProperty('--points', String(scale.max - scale.min + 1));
  let cannot = null;
  if (scale.cannotAssessLabel) {
    const input = h('input', { type: 'radio', name, value: 'CANNOT_ASSESS', id: `${name}-na` });
    if (o.missingCode === 'CANNOT_ASSESS') input.checked = true;
    input.addEventListener('change', () => saveAnswer(o, null, 'CANNOT_ASSESS'));
    cannot = h('div', { class: 'cannot' }, h('label', { class: 'opt', for: `${name}-na` }, input, h('span', { text: scale.cannotAssessLabel })));
  }
  const unanswered = revisit && o.value == null && !o.missingCode;
  return h('section', { class: `item-card${unanswered ? ' unanswered' : ''}`, 'aria-labelledby': legendId },
    h('div', { class: 'behavior', id: behId }, h('span', { class: 'label', text: t('behavior') }), o.behavior),
    h('fieldset', { class: 'item', 'aria-describedby': behId },
      h('legend', { id: legendId, text: o.text }),
      unanswered ? h('p', { class: 'hint', text: t('unansweredMark') }) : null,
      likert, cannot));
}

function renderPage() {
  if (st.pageIdx >= st.pages.length) return reviewView();
  const items = st.pages[st.pageIdx];
  const bi = items[0].blockIndex;
  const blockItems = st.data.order.filter((o) => o.blockIndex === bi);
  const posInBlock = blockItems.findIndex((o) => o.position === items[items.length - 1].position) + 1;
  setReminder(bi);
  const total = st.data.order.length;
  const done = items[items.length - 1].position + 1;
  const firstOfBlock = items[0].blockPosition === 0;
  const block = st.data.blocks[bi];
  const revisit = st.pageIdx < st.maxPageIdx;
  const prev = h('button', { type: 'button', class: 'secondary', text: t('prev'), disabled: st.pageIdx === 0 });
  prev.addEventListener('click', () => { st.pageIdx -= 1; renderPage(); });
  const next = h('button', { type: 'submit', text: st.pageIdx === st.pages.length - 1 ? t('finish') : t('next') });
  const form = h('form', { method: 'post', action: '/', 'aria-labelledby': 'block-h' },
    items.map((o) => itemFieldset(o, revisit)),
    h('div', { class: 'actions' }, prev, next));
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    st.pageIdx += 1; st.maxPageIdx = Math.max(st.maxPageIdx, st.pageIdx); renderPage();
  });
  show(
    h('h1', { class: 'visually-hidden', text: st.data.title }),
    h('div', { class: 'progress' },
      h('label', { for: 'pb', text: t('blockProgress', bi + 1, st.data.blocks.length) }),
      h('progress', { id: 'pb', max: blockItems.length, value: posInBlock }),
      h('label', { for: 'pt', text: t('totalProgress') }),
      h('progress', { id: 'pt', max: total, value: done })),
    h('h2', { id: 'block-h', text: block?.name || '' }),
    firstOfBlock && block?.instruction ? h('p', { class: 'lead', text: block.instruction }) : null,
    form,
    h('p', { id: 'save-status', class: 'status-line' }));
  markShown(items);
}

function reviewView() {
  reminder.hidden = true;
  const unanswered = st.data.order.filter((o) => o.value == null && !o.missingCode);
  const btn = h('button', { type: 'button', text: t('complete') });
  btn.addEventListener('click', async () => {
    btn.disabled = true;
    try {
      while (queue.size || flushing) { await flush(); await new Promise((r) => setTimeout(r, 200)); }
      await api('POST', `/api/respondent/sessions/${st.responseId}/complete`, {});
      doneView();
    } catch (ex) {
      btn.disabled = false;
      if (ex.status === 401) return codeView(t('sessionExpired'));
      announce(t('genericError'));
    }
  });
  show(h('section', { class: 'card' },
    h('h1', { text: t('reviewHeading') }),
    h('p', { text: t('reviewText', unanswered.length) }),
    h('div', { class: 'actions' },
      h('button', { type: 'button', class: 'secondary', text: unanswered.length ? t('goFirstUnanswered') : t('prev'),
        onclick: () => { st.pageIdx = unanswered.length ? pageOf(unanswered[0].position) : st.pages.length - 1; renderPage(); } }),
      btn)));
}

function doneView() {
  reminder.hidden = true;
  st.data = null;
  show(h('section', { class: 'card' }, h('h1', { text: t('doneHeading') }), h('p', { text: t('doneText') })));
}

// ---------------------------------------------------------------- Opstart
(async () => {
  try {
    const s = await api('GET', '/api/respondent/session');
    await loadSurvey(s.responseId);
  } catch { codeView(); }
})();
