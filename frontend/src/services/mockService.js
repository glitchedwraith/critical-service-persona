// Pure state transitions: mock mode never calls the network.
const clone = value => structuredClone(value);
const minutes = clock => { const [h,m] = String(clock || '00:00').split(':').map(Number); return h*60+m; };
const clock = value => `${String(Math.floor(value/60)%24).padStart(2,'0')}:${String(value%60).padStart(2,'0')}`;
const nextId = (records, prefix) => `${prefix}-${String(Math.max(0,...records.map(r => Number(String(r.id).split('-').pop()) || 0))+1).padStart(3,'0')}`;
export function normalizeState(value = {}) {
  value = value && typeof value === 'object' ? value : {};
  const result = { system: value.system || {} };
  for (const key of ['messages','rumors','outbound','shelters','bulletins','trace']) result[key] = Array.isArray(value[key]) ? value[key] : [];
  return result;
}
function trace(s, step, detail, ok = true, message_id = null) { s.trace.push({ at:s.system.sim_clock, step, detail, ok, message_id, ms:step === 'step2' ? 740 : 18 }); }
function evidenceHealth(s, r) {
  const evidence = r.evidence || [];
  const sources = [...s.bulletins,...s.shelters];
  const refs = evidence.map(e => sources.find(x => x.id === e.ref) || sources.find(x => x.id === e.source_id));
  const expired = evidence.some((e,i) => refs[i]?.expired || (e.expires_at && minutes(e.expires_at) <= minutes(s.system.sim_clock)));
  const missing = !evidence.length || refs.some(source => !source);
  return { refs: refs.filter(Boolean), expired, missing, usable: !missing && !expired };
}
function markStale(s) {
  const now = minutes(s.system.sim_clock);
  for (const source of [...s.bulletins,...s.shelters]) {
    const expires = source.expires_at || source.status_expires_at;
    source.expired = Boolean(source.expired || (expires && minutes(expires) <= now));
    if (source.published_at) source.age_min = Math.max(0,now-minutes(source.published_at));
  }
  for (const r of s.rumors) {
    r.evidence_expired = evidenceHealth(s,r).expired;
    if (r.evidence_expired) {
      r.outdated = true; r.current_status_known = false; r.verdict = 'unverified';
      if (['resolved','monitoring'].includes(r.status)) r.status = 'reopened';
      r.validator = {passed:false,flags:['evidence_expired'],fallback_used:true};
      const out = s.outbound.find(o => o.id === r.clarification_id);
      if (out) { out.outdated = true; out.validator = clone(r.validator); }
    }
  }
  // Older sent versions also remain in the log after a new draft is generated.
  for (const out of s.outbound) {
    const expiredSource = (out.source_ids || []).some(id => [...s.bulletins,...s.shelters].some(source => source.id === id && source.expired));
    if (expiredSource || (out.valid_until && minutes(out.valid_until) <= now)) out.outdated = true;
  }
}
function verify(s,id) {
  const r = s.rumors.find(r => r.id === id);
  if (!r) throw new Error('Rumor not found.');
  const { refs, usable, expired, missing } = evidenceHealth(s,r);
  r.evidence_expired = expired; r.outdated = !usable; r.current_status_known = usable;
  r.validator = {passed:usable,flags:[...(expired ? ['evidence_expired'] : []),...(missing ? ['missing_official_source'] : [])],fallback_used:!usable};
  let body = 'Current conditions cannot be confirmed. Please wait for updated official guidance.';
  if (usable) {
    body = refs.map(source => source.body ? `As of ${source.published_at}, ${source.body}` : `As of ${source.status_updated_at}, ${source.name} is ${source.status}. Address: ${source.address}.`).join(' ');
    r.verdict = r.entity_ids?.includes('SH-A') ? (refs[0].status === 'full' ? 'confirmed' : 'contradicted') : r.verdict === 'unverified' ? 'confirmed' : r.verdict;
  } else r.verdict = 'unverified';
  let out = s.outbound.find(o => o.id === r.clarification_id && o.state === 'draft' && (!o.rumor_id || o.rumor_id === r.id));
  if (!out) { out = {id:nextId(s.outbound,'O'),kind:'clarification',to:'Affected zones',rumor_id:r.id,state:'draft',created_at:s.system.sim_clock,lang:'en'}; s.outbound.push(out); }
  const deadlines = [...refs.map(x => x.expires_at || x.status_expires_at),...(r.evidence || []).map(e => e.expires_at)].filter(Boolean).sort((a,b) => minutes(a)-minutes(b));
  Object.assign(out,{text:body,rumor_id:r.id,validator:clone(r.validator),outdated:!usable,source_ids:refs.map(x => x.id),valid_until:deadlines[0]});
  r.clarification_id = out.id; r.status = 'drafted';
  trace(s,'step2',`Verified ${r.id} against ${refs.length} official sources.`);
  trace(s,'validator',usable ? 'Draft ready for officer approval.' : 'Draft blocked: fresh official evidence required.',usable);
}
function inbound(s,p) {
  if (!p.text?.trim() || !p.from?.trim()) throw new Error('Sender and message are required.');
  const text = p.text.toLowerCase();
  const matched = text.includes('shelter a') ? s.rumors.find(r => r.entity_ids?.includes('SH-A')) : text.includes('water') ? s.rumors.find(r => r.entity_ids?.includes('B-001')) : text.includes('bridge') ? s.rumors.find(r => r.entity_ids?.includes('B-002')) : text.includes('shelter b') || text.includes('north community') ? s.rumors.find(r => r.entity_ids?.includes('SH-B')) : null;
  let r = matched;
  if (!r) {r = {id:nextId(s.rumors,'R'),claim:p.text,entity_ids:[],message_count:0,rate_per_10min:[0],first_seen:s.system.sim_clock,status:'new',verdict:'unverified',evidence:[],current_status_known:false,emerging:false}; s.rumors.unshift(r);}
  r.message_count = (Number(r.message_count) || 0) + 1; r.rate_per_10min = [...(Array.isArray(r.rate_per_10min) ? r.rate_per_10min : []),r.message_count].slice(-8); r.emerging = r.message_count >= 3;
  if (r.status === 'resolved') r.status = 'reopened';
  const m = {...p,id:nextId(s.messages,'M'),received_at:s.system.sim_clock,claims:[r.claim],cluster_id:r.id}; s.messages.push(m);
  const reply = {id:nextId(s.outbound,'O'),kind:'holding_reply',to:p.from,text:`We received your question. We are checking official information. Last cache update: ${s.system.cache_as_of}. Current conditions may change.`,state:'delivered',created_at:s.system.sim_clock,message_id:m.id,rumor_id:r.id,lang:'en',outdated:false};
  m.reply_id = reply.id; s.outbound.push(reply);
  trace(s,'step1',`Message linked to ${r.id}.`,true,m.id); trace(s,'send','Simulated holding reply delivered.',true,m.id);
}
export function applyMockAction(current,action,p = {},seed = current) {
  if (action === 'reset') return clone(seed);
  const s = clone(current);
  if (action === 'sms') inbound(s,p);
  else if (action === 'verify') {markStale(s); verify(s,p.id);}
  else if (action === 'edit' || action === 'approve') {
    const out = s.outbound.find(o => o.id === p.id);
    if (!out || out.state !== 'draft') throw new Error('Only draft outbound records can be edited or approved.');
    if (action === 'edit') {
      if (!p.text?.trim()) throw new Error('Clarification cannot be empty.');
      out.text = p.text.trim();
      // Freeform edits require reverification: a local mock cannot validate arbitrary safety claims.
      out.validator = {passed:false,flags:['edited_text_requires_reverification'],fallback_used:false};
      trace(s,'validator','Edited draft saved. Reverify sources to regenerate a validated clarification.',false);
    } else {
      if (!out.text?.trim()) throw new Error('Clarification cannot be empty.');
      if (!p.approver?.trim()) throw new Error('An approver is required.');
      const r = s.rumors.find(r => r.id === out.rumor_id && r.clarification_id === out.id);
      if (!r) throw new Error('Invalid rumor and clarification relationship.');
      markStale(s);
      if (out.validator?.passed !== true || out.outdated || r.outdated || !evidenceHealth(s,r).usable) throw new Error('Approval blocked. Reverify fresh evidence first.');
      out.state = 'sent'; out.approved_by = p.approver; out.approved_at = s.system.sim_clock;
      r.status = 'monitoring'; r.emerging = false;
      trace(s,'send',`${out.id} approved by ${p.approver}; simulated delivery pending.`);
    }
  } else if (action === 'city_site_down') {s.system.city_site_online = false; trace(s,'step2','City website unavailable. Cached sources remain available.');}
  else if (action === 'rumor_wave') { for(let i=0;i<8;i++) inbound(s,{from:`+1-555-${300+i}`,role:'resident',zone:'A',text:'Is Shelter A closed? People are saying it is turning families away.'}); }
  else if (action === 'shelter_a_full') {
    const shelter = s.shelters.find(x => x.id === 'SH-A');
    if (!shelter) throw new Error('Shelter A is unavailable in current state.');
    shelter.status = 'full'; shelter.expired = false; shelter.status_updated_at = s.system.sim_clock; shelter.status_expires_at = clock(minutes(s.system.sim_clock)+60);
    for(const r of s.rumors.filter(r => r.entity_ids?.includes(shelter.id))) {r.status='reopened'; r.outdated=true; r.emerging=true; r.current_status_known=false; const out=s.outbound.find(o => o.id===r.clarification_id); if(out) out.outdated=true; r.evidence=(r.evidence || []).map(e => ({...e,last_verified_at:s.system.sim_clock,expires_at:shelter.status_expires_at}));}
    trace(s,'step2','Official Shelter A capacity changed to full. Related clarifications require review.');
  } else if (action === 'conflicting_report') {inbound(s,{from:'+1-555-0199',role:'volunteer',zone:'C',text:'Conflicting report: East bridge is open, but a resident says access is blocked.'}); const r=s.rumors.find(r => r.entity_ids?.includes('B-002')); if(r) {r.status='reopened';r.emerging=true;r.verdict='unverified';r.current_status_known=false;} trace(s,'validator','Conflicting resident reports require fresh official evidence.',false);}
  else if (action === 'advance_clock') {
    s.system.sim_clock = clock(minutes(s.system.sim_clock)+(p.minutes || 45));
    for(const out of s.outbound.filter(o => o.state==='sent')) {out.state='delivered';trace(s,'send',`${out.id} simulated delivery acknowledged.`);}
    for(const r of s.rumors.filter(r => r.status==='monitoring')) {r.status='resolved';r.emerging=false;}
    markStale(s); trace(s,'validator','Clock advanced. Evidence freshness and monitoring reevaluated.');
  } else if (action === 'expire_bulletin') {
    const b=s.bulletins.find(b => b.id === p.id); if(!b) throw new Error('Select an existing bulletin.');
    b.expired=true;b.status='expired';b.expires_at=s.system.sim_clock;markStale(s);trace(s,'validator',`${b.id} expired. Dependent clarifications flagged.`,false);
  } else throw new Error(`Unknown mock action: ${action}`);
  return s;
}
