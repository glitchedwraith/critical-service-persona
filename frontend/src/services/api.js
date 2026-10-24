const base = (import.meta.env?.VITE_API_BASE_URL || 'http://localhost:3000').replace(/\/$/, '');
async function request(path, body, signal) {
  let response;
  try {
    response = await fetch(`${base}${path}`, { method: body === undefined ? 'GET' : 'POST', signal,
      headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
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
  state: signal => request('/state', undefined, signal),
  act: (action, payload = {}, signal) => {
    const id = encodeURIComponent(payload.id || '');
    const routes = {
      sms: ['/sms/inbound', payload], verify: [`/rumors/${id}/verify`, {}],
      edit: [`/outbound/${id}/edit`, { text: payload.text }],
      approve: [`/outbound/${id}/approve`, { approver: payload.approver }],
      reset: ['/reset', {}],
    };
    const [path, body] = routes[action] || [`/chaos/${action}`, payload];
    return request(path, body, signal);
  },
};
