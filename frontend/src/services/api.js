const base = (import.meta.env?.VITE_API_BASE_URL || 'http://localhost:3000').replace(/\/$/, '');
const SESSION_KEY = 'truesignal.session';

/** Per-browser demo session: the backend gives each id its own seeded copy. */
function sessionId() {
  try {
    let id = localStorage.getItem(SESSION_KEY);
    if (!/^[a-z0-9]{8,32}$/.test(id || '')) {
      id = Array.from(crypto.getRandomValues(new Uint8Array(12)), b => (b % 36).toString(36)).join('');
      localStorage.setItem(SESSION_KEY, id);
    }
    return id;
  } catch { return null; } // no storage (tests, privacy mode): use the shared demo
}

async function request(path, body, signal, { replay = false } = {}) {
  let response;
  const headers = body === undefined ? {} : { 'Content-Type': 'application/json' };
  const sid = sessionId();
  if (sid) headers['X-Session-Id'] = sid;
  if (replay) headers['X-Replay'] = '1'; // fast-forward: backend skips Bedrock
  try {
    response = await fetch(`${base}${path}`, { method: body === undefined ? 'GET' : 'POST', signal,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body) });
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    throw new Error('Cannot reach the backend. Check its URL, connection, and CORS settings.');
  }
  const raw = await response.text();
  if (!raw.trim()) throw new Error(`Backend returned an empty payload (${response.status}).`);
  let data;
  try { data = JSON.parse(raw); } catch { throw new Error(`Backend returned invalid JSON (${response.status}).`); }
  if (!data || typeof data !== 'object' || Array.isArray(data)) throw new Error('Backend payload must be a JSON object.');
  if (!response.ok || data.error || data.ok === false) throw new Error(data.error || `Request failed (${response.status}).`);
  return data;
}
export const api = {
  state: (signal, opts) => request('/state', undefined, signal, opts),
  act: (action, payload = {}, signal, opts) => {
    const id = encodeURIComponent(payload.id || '');
    const routes = {
      sms: ['/sms/inbound', payload], verify: [`/rumors/${id}/verify`, {}],
      edit: [`/outbound/${id}/edit`, { text: payload.text }],
      approve: [`/outbound/${id}/approve`, { approver: payload.approver }],
      reset: ['/reset', {}],
    };
    const [path, body] = routes[action] || [`/chaos/${action}`, payload];
    return request(path, body, signal, opts);
  },
};
