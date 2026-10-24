import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { applyMockAction, normalizeState } from './mockService.js';
const seed=JSON.parse(readFileSync(new URL('../mock/state.json',import.meta.url),'utf8'));
const act=(s,a,p={}) => applyMockAction(s,a,p,seed);
test('SMS links existing rumor, reopens resolved rumors, and delivers a holding reply',() => {
 const s=act(seed,'sms',{from:'+1-555-0100',role:'resident',zone:'B',text:'Is Shelter B open?'});
 const m=s.messages.at(-1);const r=s.rumors.find(x=>x.id===m.cluster_id);
 assert.equal(r.status,'reopened');assert.equal(r.message_count,5);
 assert.equal(s.outbound.at(-1).id,m.reply_id);assert.equal(s.outbound.at(-1).state,'delivered');assert.equal(seed.messages.length,24);
});
test('unknown claims have no invented evidence',()=>{
 const s=act(seed,'sms',{from:'demo',role:'resident',zone:'C',text:'Is the airport open?'});
 const r=s.rumors[0];assert.deepEqual(r.evidence,[]);
 const v=act(s,'verify',{id:r.id});assert.equal(v.rumors[0].validator.passed,false);
});
test('approve, simulated delivery, and expiry reopen the actual linked rumor',()=>{
 const s=act(seed,'approve',{id:'O-001',approver:'Dana'});
 assert.equal(s.outbound[0].state,'sent');assert.equal(s.rumors[0].status,'monitoring');
 const later=act(s,'advance_clock',{minutes:45});
 assert.equal(later.system.sim_clock,'05:20');assert.equal(later.outbound[0].state,'delivered');assert.equal(later.rumors[0].status,'reopened');assert.equal(later.outbound[0].outdated,true);
});
test('expired and edited unvalidated drafts cannot be approved',()=>{
 assert.throws(()=>act(seed,'approve',{id:'O-003',approver:'Dana'}),/blocked/);
 const s=act(seed,'edit',{id:'O-001',text:'Edited clarification'});
 assert.equal(s.outbound[0].text,'Edited clarification');assert.throws(()=>act(s,'approve',{id:'O-001',approver:'Dana'}),/blocked/);
 assert.throws(()=>act(seed,'edit',{id:'O-004',text:'No'}),/Only draft/);
});
test('capacity chaos reopens rumor and verification uses the new official status',()=>{
 const s=act(seed,'shelter_a_full');assert.equal(s.rumors[0].status,'reopened');assert.equal(s.outbound[0].outdated,true);
 const v=act(s,'verify',{id:'R-001'});assert.equal(v.rumors[0].verdict,'confirmed');assert.match(v.outbound[0].text,/full/);assert.equal(v.outbound[0].validator.passed,true);
});
test('bulletin expiration requires an actual ID and invalidates related draft',()=>{
 assert.throws(()=>act(seed,'expire_bulletin',{id:'missing'}),/existing bulletin/);
 const s=act(seed,'expire_bulletin',{id:'B-001'});assert.equal(s.rumors[1].evidence_expired,true);assert.equal(s.outbound[1].outdated,true);
});
test('remaining chaos actions, reset, and optional state fields',()=>{
 assert.equal(act(seed,'city_site_down').system.city_site_online,false);
 const wave=act(seed,'rumor_wave');assert.equal(wave.messages.length,32);assert.equal(wave.rumors[0].message_count,22);
 const conflict=act(seed,'conflicting_report');assert.equal(conflict.rumors[2].status,'reopened');
 assert.deepEqual(act(wave,'reset'),seed);assert.deepEqual(normalizeState({}).messages,[]);
});

test('empty SMS and clarification text and invalid record IDs fail without mutation',()=>{
 for(const text of ['', '   ']) {
  assert.throws(()=>act(seed,'sms',{from:'demo',text}),/required/);
  assert.throws(()=>act(seed,'edit',{id:'O-001',text}),/empty/);
 }
 for(const action of ['verify','edit','approve']) assert.throws(()=>act(seed,action,{id:'unknown',text:'change'}));
 assert.equal(seed.messages.length,24);assert.equal(seed.outbound[0].state,'draft');
});
test('approval rejects blank text, missing approver, and mismatched rumor relationships',()=>{
 const blank=structuredClone(seed);blank.outbound[0].text='   ';
 assert.throws(()=>act(blank,'approve',{id:'O-001',approver:'Dana'}),/empty/);
 assert.throws(()=>act(seed,'approve',{id:'O-001'}),/approver/i);
 const wrong=structuredClone(seed);wrong.outbound[0].rumor_id='R-002';
 assert.throws(()=>act(wrong,'approve',{id:'O-001',approver:'Dana'}),/relationship/i);
});
test('evidence deadlines and unresolved evidence cannot be silently ignored',()=>{
 const expired=structuredClone(seed);expired.rumors[0].evidence[0].expires_at='04:20';
 const checked=act(expired,'verify',{id:'R-001'});assert.equal(checked.rumors[0].validator.passed,false);
 assert.throws(()=>act(expired,'approve',{id:'O-001',approver:'Dana'}),/blocked/);
 const partial=structuredClone(seed);partial.rumors[0].evidence.push({source_id:'missing',expires_at:'05:10'});
 assert.equal(act(partial,'verify',{id:'R-001'}).rumors[0].validator.passed,false);
});
test('expired outbound deadlines block approval and old sent versions are marked outdated',()=>{
 const expired=structuredClone(seed);expired.outbound[0].valid_until='04:20';
 assert.throws(()=>act(expired,'approve',{id:'O-001',approver:'Dana'}),/blocked/);
 const sent=act(seed,'approve',{id:'O-001',approver:'Dana'});
 const revised=act(sent,'verify',{id:'R-001'});
 const later=act(revised,'advance_clock',{minutes:45});
 assert.equal(later.outbound.find(o=>o.id==='O-001').outdated,true);
 assert.equal(later.outbound.find(o=>o.id===later.rumors[0].clarification_id).outdated,true);
});
test('repeated verification uses a single draft and repeated approval cannot send twice',()=>{
 let s=act(seed,'verify',{id:'R-001'});s=act(s,'verify',{id:'R-001'});assert.equal(s.outbound.length,5);
 s=act(s,'approve',{id:'O-001',approver:'Dana'});assert.throws(()=>act(s,'approve',{id:'O-001',approver:'Dana'}),/Only draft/);assert.equal(s.trace.filter(t=>t.detail.includes('O-001 approved')).length,1);
});
test('repeated chaos actions preserve unique IDs and reset restores the exact seed',()=>{
 let s=seed;for(let i=0;i<3;i++) for(const action of ['city_site_down','rumor_wave','shelter_a_full','conflicting_report','advance_clock','expire_bulletin']) s=act(s,action,action==='expire_bulletin'?{id:'B-001'}:{});
 for(const records of [s.messages,s.rumors,s.outbound]) assert.equal(new Set(records.map(r=>r.id)).size,records.length);
 assert.deepEqual(act(s,'reset'),seed);
});
test('null or partial state normalizes safely and missing counts start at zero',()=>{
 assert.deepEqual(normalizeState(null),normalizeState({}));
 const partial=normalizeState({rumors:[{id:'R-001',entity_ids:['SH-A']}]});
 const s=act(partial,'sms',{from:'demo',text:'Shelter A?'});assert.equal(s.rumors[0].message_count,1);
});
