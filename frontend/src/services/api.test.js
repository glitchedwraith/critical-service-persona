import test from 'node:test';
import assert from 'node:assert/strict';
import { api } from './api.js';
test('API encodes record IDs and sends contract bodies',async()=>{
 const original=globalThis.fetch;const calls=[];
 globalThis.fetch=async(url,options)=>{calls.push({url,...options});return new Response(JSON.stringify({ok:true}));};
 try {
  await api.act('approve',{id:'O/1',approver:'Dana'});await api.act('expire_bulletin',{id:'B-001'});await api.state();
  assert.match(calls[0].url,/\/outbound\/O%2F1\/approve$/);assert.deepEqual(JSON.parse(calls[0].body),{approver:'Dana'});
  assert.deepEqual(JSON.parse(calls[1].body),{id:'B-001'});assert.equal(calls[2].method,'GET');
 }finally{globalThis.fetch=original;}
});
test('API surfaces JSON rejection, invalid JSON, and connection failure',async()=>{
 const original=globalThis.fetch;
 try {
  globalThis.fetch=async()=>new Response(JSON.stringify({error:'Officer approval rejected'}),{status:409});
  await assert.rejects(api.act('approve',{id:'O-001',approver:'Dana'}),/Officer approval rejected/);
  globalThis.fetch=async()=>new Response('not json');await assert.rejects(api.state(),/invalid JSON/);
  globalThis.fetch=async()=>{throw new TypeError('Failed to fetch');};await assert.rejects(api.state(),/Cannot reach/);
 }finally{globalThis.fetch=original;}
});

test('missing API payloads produce clear errors instead of crashes or false success',async()=>{
 const original=globalThis.fetch;
 try {
  for(const body of ['', 'null', '[]']) {
   globalThis.fetch=async()=>new Response(body);
   await assert.rejects(api.state(),/empty|object|payload/i);
  }
 }finally{globalThis.fetch=original;}
});
test('all POST endpoints use the contract and preserve abort errors',async()=>{
 const original=globalThis.fetch;const calls=[];
 try {
  globalThis.fetch=async(url,options)=>{calls.push({url,...options});return new Response('{"ok":true}');};
  const sms={from:'demo',role:'resident',zone:'A',text:'Question'};
  await api.act('sms',sms);await api.act('verify',{id:'R-001'});await api.act('edit',{id:'O-001',text:'Edited'});await api.act('advance_clock',{minutes:45});await api.act('reset');
  assert.deepEqual(calls.map(c=>new URL(c.url).pathname),['/sms/inbound','/rumors/R-001/verify','/outbound/O-001/edit','/chaos/advance_clock','/reset']);
  assert.deepEqual(calls.map(c=>JSON.parse(c.body)),[sms,{}, {text:'Edited'},{minutes:45},{}]);
  globalThis.fetch=async()=>{throw new DOMException('Cancelled','AbortError');};await assert.rejects(api.state(),{name:'AbortError'});
 }finally{globalThis.fetch=original;}
});

test('API sends a stable per-browser session id and the replay flag only when asked',async()=>{
 const original=globalThis.fetch;const calls=[];const store={};
 globalThis.localStorage={getItem:k=>store[k]??null,setItem:(k,v)=>{store[k]=v;}};
 try {
  globalThis.fetch=async(url,options)=>{calls.push(options);return new Response('{"ok":true}');};
  await api.state();await api.act('reset',{},undefined,{replay:true});
  const [a,b]=calls.map(c=>c.headers);
  assert.match(a['X-Session-Id'],/^[a-z0-9]{8,32}$/);assert.equal(a['X-Session-Id'],b['X-Session-Id']);
  assert.equal(a['X-Replay'],undefined);assert.equal(b['X-Replay'],'1');
 }finally{globalThis.fetch=original;delete globalThis.localStorage;}
});
