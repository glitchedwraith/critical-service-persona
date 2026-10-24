import { danaFocus } from './derive.js';

const MAX_DANA_STEPS = 4; // per situation; a guard against a draft that never settles

/** Run Dana's primary action the way DanaPanel would. */
function runPrimary(api, state, action, opts) {
  if (action.kind === 'approve')
    return api.act('approve', { id: action.payload.id, approver: state.system.approver }, undefined, opts);
  if (action.kind === 'verify') return api.act('verify', action.payload, undefined, opts);
  return api.act(action.action, action.payload, undefined, opts);
}

/**
 * "Start from here": reset this visitor's session, then fast-forward every
 * situation before `targetId`, taking Dana's primary action after each one —
 * the same choice the rail's "Dana first" hint asks the user to make.
 * Replayed requests skip Bedrock (X-Replay), so this takes seconds.
 */
export async function replayTo(api, targetId, onProgress = () => {}) {
  const opts = { replay: true };
  await api.act('reset', {}, undefined, opts);
  let state = await api.state(undefined, opts);
  const before = [];
  for (const s of state.situations || []) {
    if (s.id === targetId) break;
    before.push(s);
  }
  for (const [i, s] of before.entries()) {
    onProgress({ done: i, total: before.length, title: s.title });
    await api.act('situation', { id: s.id }, undefined, opts);
    for (let n = 0; n < MAX_DANA_STEPS; n++) {
      state = await api.state(undefined, opts);
      const primary = danaFocus(state).actions.find(a => a.primary);
      if (!primary) break;
      await runPrimary(api, state, primary, opts);
    }
  }
  onProgress({ done: before.length, total: before.length });
  return before.length;
}
