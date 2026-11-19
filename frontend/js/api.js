// Fælles API-klient: altid JSON, same-origin, CSRF-header for admins.
let csrfToken = null;
export function setCsrf(t) { csrfToken = t; }

export class ApiError extends Error {
  constructor(status, detail) { super(detail || `HTTP ${status}`); this.status = status; }
}

export async function api(method, path, body, { raw = false } = {}) {
  const headers = { Accept: 'application/json' };
  const init = { method, headers, credentials: 'same-origin', cache: 'no-store', redirect: 'error' };
  if (method !== 'GET') {
    headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body ?? {});
    if (csrfToken) headers['X-CSRF-Token'] = csrfToken;
  }
  const res = await fetch(path, init);
  if (raw && res.ok) return res;
  if (res.status === 204) return null;
  let data = null;
  try { data = await res.json(); } catch { /* tomt svar */ }
  if (!res.ok) {
    let detail = data && typeof data.detail === 'string' ? data.detail : null;
    throw new ApiError(res.status, detail);
  }
  return data;
}
