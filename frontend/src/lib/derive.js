// Pure view-model helpers over the /state payload. No time logic and no demo
// data here: every fact comes from the backend.

const idNum = id => Number(String(id || '').split('-').pop()) || 0;
const newestFirst = rows => [...rows].sort((a, b) => idNum(b.id) - idNum(a.id));
const byId = rows => Object.fromEntries((rows || []).map(r => [r.id, r]));

export const shortClaim = claim => String(claim || '').replace(/\s+—\s+[^,.]*?(?= is | has |$)/, '');

export function zonesFromTarget(to) {
  const m = /^zone:(.+)$/.exec(to || '');
  return m && m[1] !== 'all' ? m[1].split(',') : [];
}

function zoneNames(state, to) {
  const zones = byId(state.zones);
  const ids = zonesFromTarget(to);
  if (!ids.length) return 'everyone';
  return ids.map(id => zones[id]?.label || id).join(', ');
}

function evidenceLine(state, rumor) {
  const sources = byId(state.sources);
  const ev = (rumor.evidence || [])[0];
  if (!ev) return '';
  const who = sources[ev.source_id]?.name || ev.source_id;
  const at = ev.last_verified_at || ev.published_at;
  return at ? `${who}, as of ${at}` : who;
}

/** What Dana says right now and the actions she offers. Highest priority first. */
export function danaFocus(state) {
  const sources = byId(state.sources);
  const shelters = state.shelters || [];
  const outbound = byId(state.outbound);
  const rumors = newestFirst(state.rumors || []);
  const draftOf = r => {
    const o = outbound[r.clarification_id];
    return o && o.state === 'draft' ? o : null;
  };

  // 1. Officials disagree: only Dana can settle it.
  for (const r of rumors) {
    if (r.status === 'resolved') continue;
    const shelter = shelters.find(s => s.conflict && (r.entity_ids || []).includes(s.id));
    if (!shelter || !(r.validator?.flags || []).includes('needs_officer_decision')) continue;
    const a = sources[shelter.status_source_id], b = sources[shelter.conflict.source_id];
    return {
      mood: 'decide', rumor: r, draft: null,
      line: `${a?.name || 'One source'} says ${shelter.name.split(' — ')[0]} is ${shelter.status}. ${b?.name || 'Another'} says ${shelter.conflict.status}. Same authority — who do I trust?`,
      actions: [
        { kind: 'chaos', action: 'officer_decision', label: `Trust ${a?.name || 'current'}`, primary: true,
          payload: { shelter_id: shelter.id, source_id: shelter.status_source_id } },
        { kind: 'chaos', action: 'officer_decision', label: `Trust ${b?.name || 'report'}`,
          payload: { shelter_id: shelter.id, source_id: shelter.conflict.source_id } },
      ],
    };
  }

  // 2. A clarification draft is waiting for approval.
  for (const r of rumors) {
    const draft = draftOf(r);
    if (!draft) continue;
    const claim = `“${shortClaim(r.claim)}”`;
    const where = zoneNames(state, draft.to);
    const proof = evidenceLine(state, r);
    const line = r.status === 'reopened'
      ? `${claim} is still spreading. I drafted a follow-up for ${where}. Send it?`
      : r.verdict === 'contradicted'
        ? `${claim} is false${proof ? ` — ${proof}` : ''}. Send a correction to ${where}?`
        : r.verdict === 'confirmed'
          ? `${claim} checks out${proof ? ` — ${proof}` : ''}. Confirm it to ${where}?`
          : `I can't confirm ${claim} from official sources. Send a holding message to ${where}?`;
    return {
      mood: r.status === 'reopened' ? 'critical' : 'alert', rumor: r, draft, line,
      actions: [
        { kind: 'approve', label: 'Approve & send', primary: true, payload: { id: draft.id } },
        { kind: 'edit', label: 'Edit', payload: { id: draft.id } },
        { kind: 'verify', label: 'Re-check', payload: { id: r.id } },
      ],
    };
  }

  // 3. Something already sent is no longer true.
  for (const r of rumors) {
    if (r.status === 'resolved' && !r.outdated) continue;
    if (r.outdated || r.evidence_expired) {
      const why = r.outdated ? 'the facts changed since I sent it' : 'its evidence expired';
      return {
        mood: 'alert', rumor: r, draft: null,
        line: `My message on “${shortClaim(r.claim)}” is out of date — ${why}. Redraft?`,
        actions: [{ kind: 'verify', label: 'Redraft', primary: true, payload: { id: r.id } }],
      };
    }
  }

  // 4. A rumor is spreading but hasn't been checked yet.
  const fresh = rumors.find(r => r.emerging && r.status === 'new');
  if (fresh) return {
    mood: 'alert', rumor: fresh, draft: null,
    line: `“${shortClaim(fresh.claim)}” is spreading. Let me check the sources.`,
    actions: [{ kind: 'verify', label: 'Check sources', primary: true, payload: { id: fresh.id } }],
  };

  // 5. Delivery trouble.
  const failed = newestFirst(state.outbound || []).slice(0, 3).find(o => o.state === 'failed');
  if (failed) return {
    mood: 'alert', rumor: null, draft: null, actions: [],
    line: `A text to ${failed.to.startsWith('zone:') ? zoneNames(state, failed.to) : failed.to} failed to deliver. I'm showing it, not hiding it.`,
  };

  // 6. Watching / done.
  const watching = rumors.find(r => r.status === 'monitoring');
  if (watching) return {
    mood: 'watch', rumor: watching, draft: null, actions: [],
    line: `Sent. Watching whether “${shortClaim(watching.claim)}” dies down…`,
  };
  const stale = [...shelters, ...(state.bulletins || [])].some(x => x.expired && x.status !== 'superseded');
  const resolved = rumors.find(r => r.status === 'resolved');
  if (stale) return {
    mood: 'watch', rumor: null, draft: null, actions: [],
    line: "Some official info has expired. Until it's refreshed, I answer “can't confirm.”",
  };
  if (resolved) return {
    mood: 'good', rumor: resolved, draft: null, actions: [],
    line: `“${shortClaim(resolved.claim)}” has died down. Nice work.`,
  };
  if (state.system?.city_site_online === false) return {
    mood: 'watch', rumor: null, draft: null, actions: [],
    line: `The city site is down. I'm answering from official bulletins cached at ${state.system.cache_as_of}.`,
  };
  return {
    mood: 'calm', rumor: null, draft: null, actions: [],
    line: 'All quiet. Official information is current.',
  };
}

const MOOD_RANK = { calm: 0, good: 1, informed: 2, alert: 3, critical: 4 };

/** zone id -> calm | good | informed | alert | critical */
export function zoneMoods(state) {
  const rumors = byId(state.rumors);
  const moods = Object.fromEntries((state.zones || []).map(z => [z.id, 'calm']));
  const bump = (zone, mood) => {
    if (zone in moods && MOOD_RANK[mood] > MOOD_RANK[moods[zone]]) moods[zone] = mood;
  };
  for (const m of state.messages || []) {
    const r = rumors[m.cluster_id];
    if (!r) continue;
    const mood = r.status === 'reopened' ? 'critical'
      : r.status === 'resolved' ? 'good'
        : r.status === 'monitoring' ? 'informed'
          : r.emerging || r.status === 'drafted' ? 'alert' : 'calm';
    bump(m.zone, mood);
  }
  return moods;
}

export function shelterTone(s) {
  if (s.expired) return 'stale';
  return { open: 'open', full: 'full', closed: 'closed' }[s.status] || 'unknown';
}

/** Latest step results for the trace strip: one entry per step kind. */
export function latestTrace(trace) {
  const seen = new Map();
  for (const t of trace || []) if (!seen.has(t.step)) seen.set(t.step, t);
  return ['step1', 'step2', 'validator', 'send'].map(step => ({ step, entry: seen.get(step) || null }));
}

/** Situation rail status: done | running | next | idle. */
export function situationStatus(state) {
  const sys = state.system || {};
  const done = new Set(sys.situations_done || []);
  const running = sys.active_situation?.running ? sys.active_situation.id : null;
  const next = (state.situations || []).find(s => !done.has(s.id))?.id;
  return Object.fromEntries((state.situations || []).map(s => [s.id,
    s.id === running ? 'running' : done.has(s.id) ? 'done' : s.id === next ? 'next' : 'idle']));
}

/** The demo phone's newest text and TrueSignal's answer, for the resident box.
 *  `ms` is Bedrock time for that message (Understand + Verify, from the trace). */
export function lastExchange(state, phone) {
  if (!phone) return null;
  const msg = newestFirst((state.messages || []).filter(m => m.from === phone))[0];
  if (!msg) return null;
  const steps = (state.trace || []).filter(t => t.message_id === msg.id);
  const reply = msg.reply_id ? (state.outbound || []).find(o => o.id === msg.reply_id) || null : null;
  const ms = steps.filter(t => t.step === 'step1' || t.step === 'step2').reduce((n, t) => n + (Number(t.ms) || 0), 0);
  const understood = steps.some(t => t.step === 'step1');
  return { msg, reply, ms: ms || null, pending: !understood && !reply, rumor: Boolean(msg.cluster_id) };
}

/** IDs in `rows` not present in `seen` (a Set). */
export const unseen = (rows, seen) => (rows || []).filter(r => !seen.has(r.id));
