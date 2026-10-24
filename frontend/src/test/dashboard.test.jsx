import './dom.js';
import test, { afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { act } from 'react';
import { createRoot } from 'react-dom/client';
import App from '../App.jsx';
import EmergingRumors from '../components/EmergingRumors.jsx';
import ResidentPhoneSimulator from '../components/ResidentPhoneSimulator.jsx';
import IncomingFeed from '../components/IncomingFeed.jsx';
import OutboundLog from '../components/OutboundLog.jsx';
import PipelineTrace from '../components/PipelineTrace.jsx';
import StatusBanner from '../components/StatusBanner.jsx';
import ChaosBar from '../components/ChaosBar.jsx';
import { normalizeState } from '../services/mockService.js';
import seed from '../mock/state.json';

let root, host;
const originalFetch = globalThis.fetch;
afterEach(async () => {
  if (root) await act(async () => root.unmount());
  host?.remove(); root = null; globalThis.fetch = originalFetch;
});
async function mount(element = <App />) {
  host = document.createElement('div'); document.body.append(host); root = createRoot(host);
  await act(async () => root.render(element));
}
function button(label, parent = host) {
  const result = [...parent.querySelectorAll('button')].find(b => b.textContent.toLowerCase().includes(label.toLowerCase()) || b.getAttribute('aria-label') === label);
  assert.ok(result, `Button exists: ${label}`); return result;
}
async function click(label, parent = host) { await act(async () => button(label,parent).click()); }
async function input(element, value) {
  const prototype = element.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : element.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
  await act(async () => {
    Object.getOwnPropertyDescriptor(prototype,'value').set.call(element,value);
    element.dispatchEvent(new Event(element.tagName === 'SELECT' ? 'change' : 'input', { bubbles:true }));
  });
}
const card = id => [...host.querySelectorAll('.rumor-card')].find(el => el.querySelector('.record-id').textContent === id);
const draft = id => card(id).querySelector('.draft p')?.textContent;

test('all dashboard sections render the seed; feed is newest first',async()=>{
  await mount();
  for(const title of ['TrueSignal','Incoming feed','Emerging rumors','Phone simulator','Outbound log','Pipeline trace','Stress-test the signal']) assert.ok(host.textContent.includes(title));
  assert.equal(host.querySelectorAll('.feed-item').length,24);
  assert.match(host.querySelector('.feed-item .item-meta').textContent,/04:35/);
  assert.equal(host.querySelectorAll('.rumor-card').length,5);
  assert.equal(host.querySelectorAll('.trace-item').length,18);
  assert.match(card('R-003').textContent,/Evidence expired/);
  assert.match(card('R-005').textContent,/No evidence supplied/);
  assert.equal(card('R-001').querySelector('details').open,false);
  assert.match(card('R-001').textContent,/contradicted/);
});
test('phone input sends to feed and conversation with no Fetch calls in Mock Mode',async()=>{
  let requests=0;globalThis.fetch=async()=>{requests++;throw new Error('Mock mode must not fetch');};
  await mount();
  await input(host.querySelector('[aria-label="Sender number"]'),'+1-555-0999');
  const selects=host.querySelectorAll('.phone-form select');await input(selects[0],'volunteer');await input(selects[1],'C');
  await input(host.querySelector('[aria-label="SMS message"]'),'Is Shelter A closed?');
  await click('Send simulated SMS');
  assert.equal(host.querySelectorAll('.feed-item').length,25);
  const newest=host.querySelector('.feed-item');assert.match(newest.textContent,/0999/);assert.match(newest.textContent,/Zone C/);assert.match(newest.textContent,/volunteer/);
  assert.equal(host.querySelectorAll('.bubble.in').length,1);assert.equal(host.querySelectorAll('.bubble.out').length,1);
  assert.equal(host.querySelector('[aria-label="SMS message"]').value,'');assert.equal(requests,0);
});
test('editing loads existing text, cancel preserves it, whitespace disables save, and save targets its outbound',async()=>{
  await mount();const before=draft('R-001');
  await click('Edit draft',card('R-001'));assert.equal(card('R-001').querySelector('textarea').value,before);
  await input(card('R-001').querySelector('textarea'),'Uncommitted change');await click('Cancel',card('R-001'));assert.equal(draft('R-001'),before);
  await click('Edit draft',card('R-001'));await input(card('R-001').querySelector('textarea'),'   ');assert.equal(button('Save draft',card('R-001')).disabled,true);
  await input(card('R-001').querySelector('textarea'),'Officer edited clarification');await click('Save draft',card('R-001'));
  assert.equal(draft('R-001'),'Officer edited clarification');assert.match(host.querySelector('.outbound-item:last-child').textContent,/Officer edited clarification/);
  assert.equal(button('Approve & send',card('R-001')).disabled,true);assert.equal(draft('R-002'),seed.outbound[1].text);
  assert.ok(![...card('R-004').querySelectorAll('button')].some(b=>b.textContent==='Edit draft'));
});
test('verify and approve update the related record without remounting the card or duplicating sends',async()=>{
  await mount();const initial=card('R-001');
  await click('Verify sources',initial);assert.equal(card('R-001'),initial);assert.equal(button('Approve & send',initial).disabled,false);
  await act(async()=>{const b=button('Approve & send',initial);b.click();b.click();});
  assert.match(initial.textContent,/monitoring/);assert.equal(host.querySelectorAll('.outbound-item').length,5);
  const o=[...host.querySelectorAll('.outbound-item')].find(x=>x.textContent.includes('O-001'));assert.match(o.textContent,/sent/);
  assert.equal(button('Approve & send',card('R-003')).disabled,true);
});
test('all six chaos controls update state and reset restores all data',async()=>{
  let requests=0;globalThis.fetch=async()=>{requests++;throw new Error('Unexpected mock request');};
  await mount();
  await click('City site down');assert.match(host.querySelector('.status-banner').textContent,/Offline/);
  await click('Rumor wave');assert.equal(host.querySelectorAll('.feed-item').length,32);
  await click('Shelter A full');assert.match(card('R-001').textContent,/reopened/);
  await click('Verify sources',card('R-001'));assert.match(draft('R-001'),/full/);
  await click('Conflicting report');assert.equal(host.querySelectorAll('.feed-item').length,33);
  await click('Clock +45 min');assert.match(host.querySelector('.status-banner').textContent,/05:20/);
  await click('Expire bulletin');assert.match(card('R-002').textContent,/Evidence expired/);
  await click('Reset demo');assert.equal(host.querySelectorAll('.feed-item').length,24);assert.equal(host.querySelectorAll('.outbound-item').length,5);assert.equal(host.querySelectorAll('.trace-item').length,18);assert.match(host.querySelector('.status-banner').textContent,/04:35/);
  assert.equal(draft('R-001'),seed.outbound[0].text);
  assert.equal(requests,0);
});
test('empty arrays and absent optional fields render safely',async()=>{
  const empty=normalizeState({});await mount(<EmergingRumors state={empty} onAction={async()=>true}/>);assert.match(host.textContent,/No rumors detected/);
  await act(async()=>root.render(<EmergingRumors state={normalizeState({rumors:[{id:'R-min',rate_per_10min:[null,2]}]})} onAction={async()=>true}/>));
  assert.match(host.textContent,/Claim unavailable/);assert.match(host.textContent,/No evidence supplied/);
});
test('rapid sequential mock actions retain both state transitions',async()=>{
  await mount();await act(async()=>{button('Rumor wave').click();button('Rumor wave').click();});
  assert.equal(host.querySelectorAll('.feed-item').length,40);
});
test('reset closes stale draft edits',async()=>{
  await mount();await click('Edit draft',card('R-001'));await input(card('R-001').querySelector('textarea'),'Stale unsaved draft');
  await click('Reset demo');assert.ok(card('R-001').querySelector('textarea') === null,'Reset closes the editor');assert.equal(draft('R-001'),seed.outbound[0].text);
});
test('phone rejects whitespace and shows pending and failed submission feedback',async()=>{
  let complete,calls=0;
  const action=()=>{calls++;return new Promise(resolve=>{complete=resolve;});};
  await mount(<ResidentPhoneSimulator state={normalizeState(seed)} onAction={action} mode="mock"/>);
  assert.equal(button('Send simulated SMS').disabled,true);await click('Send simulated SMS');assert.equal(calls,0);
  await input(host.querySelector('[aria-label="SMS message"]'),'   ');assert.equal(button('Send simulated SMS').disabled,true);
  await click('Send simulated SMS');assert.equal(calls,0);
  await input(host.querySelector('[aria-label="SMS message"]'),'A valid question');await click('Send simulated SMS');assert.equal(calls,1);assert.equal(button('Send simulated SMS').disabled,true);
  await act(async()=>complete(false));assert.match(host.querySelector('[role="alert"]').textContent,/could not be sent/);assert.equal(button('Send simulated SMS').disabled,false);
});
test('mode switching preserves mock data and aborts live polling using stubbed Fetch only',async()=>{
  let reads=0,signal;
  globalThis.fetch=async(url,options)=>{reads++;signal=options.signal;return new Response(JSON.stringify({system:{sim_clock:'09:00'},messages:[]}));};
  await mount();await click('Rumor wave');await click('Live API');assert.equal(reads,1);assert.equal(host.querySelectorAll('.feed-item').length,0);assert.match(host.textContent,/09:00/);
  await click('Mock demo');assert.equal(signal.aborted,true);assert.equal(host.querySelectorAll('.feed-item').length,32);
});

test('same-minute phone replies stay next to their related incoming messages',async()=>{
 await mount();await input(host.querySelector('[aria-label="Sender number"]'),'+1-555-0998');
 for(const text of ['First question','Second question']) {await input(host.querySelector('[aria-label="SMS message"]'),text);await click('Send simulated SMS');}
 assert.deepEqual([...host.querySelectorAll('.bubble')].map(el=>el.classList.contains('in')?'in':'out'),['in','out','in','out']);
});
test('feed caps at 50 records while retaining the total received count',async()=>{
 await mount();for(let i=0;i<4;i++) await click('Rumor wave');
 assert.equal(host.querySelectorAll('.feed-item').length,50);assert.match(host.querySelector('.panel-footer').textContent,/56 messages received/);
});
test('failed live reads display errors and switching back restores a usable mock',async()=>{
 let calls=0;globalThis.fetch=async()=>{calls++;throw new TypeError('Offline');};
 await mount();await click('Live API');assert.match(host.querySelector('[role="alert"]').textContent,/Cannot reach/);assert.equal(button('Rumor wave').disabled,true);
 await click('Mock demo');await click('Rumor wave');assert.equal(host.querySelectorAll('.feed-item').length,32);assert.equal(calls,1);
});
test('pending live approval disables actions; backend rejection stays visible after state refresh',async()=>{
 let rejectPost;const calls=[];
 globalThis.fetch=async(url,options)=>{calls.push(options.method);if(options.method==='POST') return new Promise(resolve=>{rejectPost=()=>resolve(new Response('{"error":"Approval rejected by validator"}',{status:409}));});return new Response(JSON.stringify(seed));};
 await mount();await click('Live API');await click('Approve & send',card('R-001'));
 assert.equal(button('Rumor wave').disabled,true);assert.equal(button('Live API').disabled,true);assert.equal(button('Approve & send',card('R-001')).disabled,true);
 await act(async()=>rejectPost());assert.match(host.querySelector('[role="alert"]').textContent,/Approval rejected by validator/);assert.deepEqual(calls,['GET','POST','GET']);
 assert.equal(button('Rumor wave').disabled,false);
});
test('an incomplete reset reports the seed import failure using stubbed API responses',async()=>{
 globalThis.fetch=async(url,options)=>new Response(options.method==='POST'?JSON.stringify({ok:true,seed_imported:false,seed_error:'Fixture unavailable'}):JSON.stringify(seed));
 await mount();await click('Live API');await click('Reset demo');assert.match(host.querySelector('[role="alert"]').textContent,/Reset incomplete: Fixture unavailable/);
});
test('live polling waits for an outstanding read and mode cleanup cancels it',async t=>{
 t.mock.timers.enable({apis:['setTimeout']});let calls=0,finish,signal;
 globalThis.fetch=async(url,options)=>{calls++;signal=options.signal;return new Promise(resolve=>{finish=()=>resolve(new Response(JSON.stringify(seed)));});};
 await mount();await click('Live API');await act(async()=>t.mock.timers.tick(6000));assert.equal(calls,1);
 await act(async()=>finish());await act(async()=>t.mock.timers.tick(2000));assert.equal(calls,2);
 await click('Mock demo');assert.equal(signal.aborted,true);await act(async()=>{finish();t.mock.timers.tick(6000);});assert.equal(calls,2);assert.equal(host.querySelectorAll('.feed-item').length,24);
});

test('evidence disclosure toggles and remains open across a mock update',async()=>{
 await mount();const details=card('R-001').querySelector('details');
 await act(async()=>details.querySelector('summary').click());assert.equal(details.open,true);
 await click('Rumor wave');assert.ok(card('R-001').querySelector('details')===details);assert.equal(details.open,true);
 await act(async()=>details.querySelector('summary').click());assert.equal(details.open,false);
});
test('empty lists and minimal optional records render across the remaining panels',async()=>{
 await mount(<><IncomingFeed messages={[]}/><OutboundLog records={[]}/><PipelineTrace records={[]}/><StatusBanner system={{}} mode="mock" onMode={()=>{}}/></>);
 assert.match(host.textContent,/No incoming messages/);assert.match(host.textContent,/No outbound records/);assert.match(host.textContent,/Waiting for pipeline activity/);
 await act(async()=>root.render(<><IncomingFeed messages={[{id:'M-min'}]}/><OutboundLog records={[{id:'O-min'}]}/><PipelineTrace records={[{}]}/><ResidentPhoneSimulator state={normalizeState({})} mode="mock" onAction={async()=>true}/></>));
 assert.match(host.textContent,/Unknown sender/);assert.match(host.textContent,/Delivery: not sent/);assert.match(host.textContent,/No detail supplied/);
});
test('unavailable bulletin expiry and pending chaos controls cannot dispatch actions',async()=>{
 let calls=0;const action=()=>{calls++;};
 await mount(<ChaosBar bulletins={[]} onAction={action} busy={false}/>);
 assert.equal(button('Expire bulletin').disabled,true);await click('Expire bulletin');assert.equal(calls,0);
 await act(async()=>root.render(<ChaosBar bulletins={seed.bulletins} onAction={action} busy/>));
 assert.ok([...host.querySelectorAll('button')].every(b=>b.disabled));await click('Rumor wave');assert.equal(calls,0);
});
test('UI sends the selected current bulletin ID when expiring it',async()=>{
 const calls=[];await mount(<ChaosBar bulletins={seed.bulletins} onAction={async(...args)=>{calls.push(args);return true;}}/>);
 await input(host.querySelector('select'),'B-002');await click('Expire bulletin');assert.deepEqual(calls,[['expire_bulletin',{id:'B-002'}]]);
 assert.match(host.querySelector('[role="status"]').textContent,/complete/);
});

test('live polling starts immediately and repeats two seconds after each completed read',async t=>{
 t.mock.timers.enable({apis:['setTimeout']});
 let reads=0;
 globalThis.fetch=async(url,options)=>{
   assert.equal(options.method,'GET');assert.match(url,/\/state$/);reads++;
   return new Response(JSON.stringify(seed));
 };
 await mount();assert.equal(reads,0);
 await click('Live API');assert.equal(reads,1);
 await act(async()=>t.mock.timers.tick(1999));assert.equal(reads,1);
 await act(async()=>t.mock.timers.tick(1));assert.equal(reads,2);
 await act(async()=>t.mock.timers.tick(2000));assert.equal(reads,3);
 await click('Mock demo');await act(async()=>t.mock.timers.tick(10000));assert.equal(reads,3);
});

test('unmount cancels a pending live read and prevents rescheduling after late completion',async t=>{
 t.mock.timers.enable({apis:['setTimeout']});
 let reads=0,signal,complete;
 globalThis.fetch=async(url,options)=>{
   reads++;signal=options.signal;
   return new Promise(resolve=>{complete=()=>resolve(new Response(JSON.stringify(seed)));});
 };
 await mount();await click('Live API');assert.equal(reads,1);
 await act(async()=>root.unmount());root=null;
 assert.equal(signal.aborted,true);
 await act(async()=>{complete();t.mock.timers.tick(10000);});
 assert.equal(reads,1);assert.equal(host.childElementCount,0);
});

test('unmount clears a scheduled live polling timer',async t=>{
 t.mock.timers.enable({apis:['setTimeout']});let reads=0;
 globalThis.fetch=async()=>{reads++;return new Response(JSON.stringify(seed));};
 await mount();await click('Live API');assert.equal(reads,1);
 await act(async()=>root.unmount());root=null;
 await act(async()=>t.mock.timers.tick(10000));assert.equal(reads,1);
});

test('live snapshots update data while preserving unsaved edits and scroll-container identity',async t=>{
 t.mock.timers.enable({apis:['setTimeout']});let reads=0;
 globalThis.fetch=async()=>{
   const snapshot=structuredClone(seed);reads++;
   snapshot.outbound[0].text=`Backend snapshot ${reads}`;
   snapshot.system.sim_clock=reads===1?'04:35':'04:36';
   return new Response(JSON.stringify(snapshot));
 };
 await mount();await click('Live API');
 await click('Edit draft',card('R-001'));
 const editor=card('R-001').querySelector('textarea');
 await input(editor,'Unsaved officer wording');
 const containers=[...host.querySelectorAll('.panel-scroll,.conversation')];
 assert.equal(containers.length,5);
 containers.forEach((element,i)=>{element.scrollTop=70+i;});
 await act(async()=>t.mock.timers.tick(2000));assert.equal(reads,2);
 assert.match(host.querySelector('.status-banner').textContent,/04:36/);
 assert.ok(card('R-001').querySelector('textarea')===editor);
 assert.equal(editor.value,'Unsaved officer wording');
 const updated=[...host.querySelectorAll('.panel-scroll,.conversation')];
 containers.forEach((element,i)=>{assert.ok(updated[i]===element);assert.equal(updated[i].scrollTop,70+i);});
 await click('Cancel',card('R-001'));assert.equal(draft('R-001'),'Backend snapshot 2');
 // jsdom confirms DOM reuse/property retention, not physical browser scroll geometry.
});
