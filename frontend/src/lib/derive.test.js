import test from 'node:test';
import assert from 'node:assert/strict';
import { danaFocus, latestTrace, shortClaim, situationStatus, zoneMoods, zonesFromTarget } from './derive.js';

// Minimal synthetic rows: shape-only fixtures for the view-model, not demo data.
const base = (over = {}) => ({
  system: { city_site_online: true, approver: 'Officer', cache_as_of: '01:00' },
  zones: [{ id: 'Z1', label: 'North' }, { id: 'Z2', label: 'South' }],
  sources: [{ id: 'S1', name: 'Source One', authority: 1 }, { id: 'S2', name: 'Source Two', authority: 2 }, { id: 'S3', name: 'Source Three', authority: 2 }],
  shelters: [], bulletins: [], messages: [], rumors: [], outbound: [], trace: [], situations: [],
  ...over,
});

test('shortClaim drops the long venue name', () => {
  assert.equal(shortClaim('Shelter X — Some Long Gym is closed'), 'Shelter X is closed');
  assert.equal(shortClaim('Tap water is contaminated'), 'Tap water is contaminated');
});

test('zonesFromTarget parses broadcast targets', () => {
  assert.deepEqual(zonesFromTarget('zone:Z1,Z2'), ['Z1', 'Z2']);
  assert.deepEqual(zonesFromTarget('zone:all'), []);
  assert.deepEqual(zonesFromTarget('+1-000'), []);
});

test('idle states', () => {
  assert.equal(danaFocus(base()).mood, 'calm');
  const off = danaFocus(base({ system: { city_site_online: false, cache_as_of: '01:00' } }));
  assert.match(off.line, /cached at 01:00/);
});

test('draft awaiting approval offers approve/edit/re-check with target zones', () => {
  const s = base({
    rumors: [{ id: 'R-1', claim: 'Thing is closed', status: 'drafted', verdict: 'contradicted', emerging: true,
      clarification_id: 'O-1', evidence: [{ source_id: 'S1', last_verified_at: '01:10' }] }],
    outbound: [{ id: 'O-1', kind: 'clarification', state: 'draft', to: 'zone:Z1,Z2', text: 'x' }],
  });
  const f = danaFocus(s);
  assert.equal(f.draft.id, 'O-1');
  assert.deepEqual(f.actions.map(a => a.kind), ['approve', 'edit', 'verify']);
  assert.match(f.line, /false — Source One, as of 01:10/);
  assert.match(f.line, /North, South/);
});

test('equal-authority conflict outranks a pending draft and offers both sources', () => {
  const s = base({
    shelters: [{ id: 'SH-1', name: 'Place — Hall', status: 'open', status_source_id: 'S2', conflict: { source_id: 'S3', status: 'closed' } }],
    rumors: [{ id: 'R-2', claim: 'Place is closed', status: 'drafted', entity_ids: ['SH-1'], clarification_id: 'O-2',
      validator: { flags: ['needs_officer_decision'] } }],
    outbound: [{ id: 'O-2', kind: 'clarification', state: 'draft', to: 'zone:Z1', text: 'x' }],
  });
  const f = danaFocus(s);
  assert.equal(f.mood, 'decide');
  assert.deepEqual(f.actions.map(a => a.payload.source_id), ['S2', 'S3']);
});

test('outdated, failed, monitoring and resolved states', () => {
  assert.equal(danaFocus(base({ rumors: [{ id: 'R-1', claim: 'c', status: 'resolved', outdated: true }] })).actions[0].label, 'Redraft');
  assert.match(danaFocus(base({ outbound: [{ id: 'O-1', state: 'failed', to: '+1-000' }] })).line, /failed to deliver/);
  assert.equal(danaFocus(base({ rumors: [{ id: 'R-1', claim: 'c', status: 'monitoring' }] })).mood, 'watch');
  assert.equal(danaFocus(base({ rumors: [{ id: 'R-1', claim: 'c', status: 'resolved' }] })).mood, 'good');
});

test('a monitoring rumor always offers a way to move the clock forward', () => {
  const f = danaFocus(base({ rumors: [{ id: 'R-1', claim: 'c', status: 'monitoring' }] }));
  assert.equal(f.actions.length, 1);
  assert.equal(f.actions[0].kind, 'chaos');
  assert.equal(f.actions[0].action, 'advance_clock');
  assert.deepEqual(f.actions[0].payload, { minutes: 20 });
});

test('zone moods follow the rumors their residents texted about', () => {
  const s = base({
    rumors: [{ id: 'R-1', status: 'reopened' }, { id: 'R-2', status: 'monitoring' }],
    messages: [{ id: 'M-1', zone: 'Z1', cluster_id: 'R-2' }, { id: 'M-2', zone: 'Z1', cluster_id: 'R-1' }],
  });
  assert.deepEqual(zoneMoods(s), { Z1: 'critical', Z2: 'calm' });
});

test('trace keeps the newest entry per step; situations track progress', () => {
  const t = latestTrace([{ step: 'step1', ok: true, ms: 5 }, { step: 'step1', ok: false }]);
  assert.equal(t[0].entry.ms, 5);
  assert.equal(t[1].entry, null);
  const s = base({ situations: [{ id: 'a' }, { id: 'b' }, { id: 'c' }],
    system: { situations_done: ['a'], active_situation: { id: 'c', running: true } } });
  assert.deepEqual(situationStatus(s), { a: 'done', b: 'next', c: 'running' });
});

test('lastExchange pairs the demo phone\'s newest text with its reply and Bedrock time', async () => {
  const { lastExchange } = await import('./derive.js');
  const s = base({
    messages: [{ id: 'M-2', from: 'me', text: 'second', reply_id: 'O-9' }, { id: 'M-1', from: 'me', text: 'first' },
               { id: 'M-3', from: 'other', text: 'not mine' }],
    outbound: [{ id: 'O-9', kind: 'reply', text: 'answer' }],
    trace: [{ step: 'send', message_id: 'M-2', ms: 0 }, { step: 'step2', message_id: 'M-2', ms: 1700 },
            { step: 'step1', message_id: 'M-2', ms: 1200 }, { step: 'step1', message_id: 'M-1', ms: 999 }],
  });
  const x = lastExchange(s, 'me');
  assert.equal(x.msg.text, 'second'); assert.equal(x.reply.text, 'answer'); assert.equal(x.ms, 2900);
  assert.equal(x.pending, false);
  assert.equal(lastExchange(s, null), null);
  const quiet = lastExchange(base({ messages: [{ id: 'M-1', from: 'me', text: 'x' }],
    trace: [{ step: 'step1', message_id: 'M-1', ms: 1100 }] }), 'me');
  assert.equal(quiet.reply, null); assert.equal(quiet.pending, false);
  assert.equal(lastExchange(base({ messages: [{ id: 'M-1', from: 'me', text: 'x' }] }), 'me').pending, true);
});
