import test from 'node:test';
import assert from 'node:assert/strict';
import { replayTo } from './replay.js';

const situations = [{ id: 'one', title: 'One' }, { id: 'two', title: 'Two' }, { id: 'three', title: 'Three' }];
const base = { system: { approver: 'Dana' }, situations, sources: [], shelters: [], outbound: [], rumors: [], bulletins: [] };

test('replayTo resets, runs earlier situations, takes Dana\'s primary action, stops before the target', async () => {
  const calls = [];
  let pendingDraft = false;
  const api = {
    act: async (action, payload, _signal, opts) => {
      calls.push([action, payload?.id, opts?.replay]);
      if (action === 'situation' && payload.id === 'one') pendingDraft = true;
      if (action === 'approve') pendingDraft = false;
      return { ok: true };
    },
    state: async () => pendingDraft
      ? { ...base, rumors: [{ id: 'R-1', claim: 'x', clarification_id: 'O-1', status: 'new' }],
          outbound: [{ id: 'O-1', state: 'draft', to: 'zone:all', text: 't' }] }
      : base,
  };
  const progress = [];
  const n = await replayTo(api, 'three', p => progress.push(p.done));
  assert.equal(n, 2);
  assert.deepEqual(calls, [
    ['reset', undefined, true], ['situation', 'one', true], ['approve', 'O-1', true], ['situation', 'two', true],
  ]);
  assert.deepEqual(progress, [0, 1, 2]);
});
