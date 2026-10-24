import { useEffect, useRef, useState } from 'react';
import seed from './mock/state.json';
import { api } from './services/api.js';
import { applyMockAction, normalizeState } from './services/mockService.js';
import StatusBanner from './components/StatusBanner.jsx';
import IncomingFeed from './components/IncomingFeed.jsx';
import EmergingRumors from './components/EmergingRumors.jsx';
import ResidentPhoneSimulator from './components/ResidentPhoneSimulator.jsx';
import OutboundLog from './components/OutboundLog.jsx';
import PipelineTrace from './components/PipelineTrace.jsx';
import ChaosBar from './components/ChaosBar.jsx';
export default function App() {
 const [mode,setMode] = useState('mock');
 const [state,setState] = useState(() => normalizeState(structuredClone(seed)));
 const [sessionKey,setSessionKey] = useState(0);
 const [busy,setBusy] = useState(false); const [error,setError] = useState(''); const [pollError,setPollError] = useState(''); const [notice,setNotice] = useState(''); const [connected,setConnected] = useState(false);
 const mockState = useRef(state); const currentState = useRef(state); const locked = useRef(false); const controller = useRef(null); const refresh = useRef(null); const modeRef = useRef(mode);
 currentState.current=state; modeRef.current=mode;
 useEffect(() => {
   setError('');setPollError('');setNotice('');setConnected(false);
   if(mode==='mock') {setState(mockState.current); return;}
   // An empty live workspace prevents mock records from appearing as backend data.
   setState(normalizeState());
   let active=true, timer, inFlight=null;
   async function poll() {
     clearTimeout(timer);
     if (!active) return;
     if(inFlight) return inFlight;
     if(locked.current) {timer=setTimeout(poll,2000);return;}
     const c = new AbortController(); controller.current=c;
     inFlight=(async () => {try {const value=await api.state(c.signal);if(active) {setState(normalizeState(value));setConnected(true);setPollError('');}} catch(e) {if(active && e.name!=='AbortError') {setConnected(false);setPollError(e.message);}} finally {inFlight=null;if(active) timer=setTimeout(poll,2000);}})();
     return inFlight;
   }
   refresh.current=poll;poll();
   return () => {active=false;clearTimeout(timer);controller.current?.abort();refresh.current=null;};
 },[mode]);
 function switchMode(next) { if(locked.current || next===mode) return; if(mode==='mock') mockState.current=currentState.current; setSessionKey(value => value + 1); setMode(next); }
 async function onAction(action,payload={}) {
   if(locked.current) return false;
   locked.current=true;setBusy(true);setError('');setNotice('');
   let success=false;
   try {
     if(modeRef.current==='mock') {
       const next=applyMockAction(currentState.current,action,payload,seed);
       // A second action can run before React commits the first render.
       currentState.current=next;mockState.current=next;setState(next);
     } else {
       // Cancel any older snapshot before mutating. Polling waits until this action completes.
       controller.current?.abort();
       const c=new AbortController();controller.current=c;
       const result=await api.act(action,payload,c.signal);
       if(action==='reset' && result.seed_imported===false) throw new Error(`Reset incomplete: ${result.seed_error || 'seed data was not imported.'}`);
     }
     if(action==='reset') setSessionKey(value => value + 1);
     setNotice(`${action==='sms' ? 'Simulated message received' : action==='edit' ? 'Draft saved' : action==='approve' ? 'Clarification approved and queued for simulated delivery' : action==='verify' ? 'Sources checked; review the validator result' : action==='reset' ? 'Demo reset' : 'Simulation updated'}.`);success=true;
   } catch(e) {if(e.name!=='AbortError') setError(e.message);}
   finally {locked.current=false;setBusy(false);if(modeRef.current==='live') { await refresh.current?.(); }}
   return success;
 }
 return <div className="app"><StatusBanner system={state.system} mode={mode} onMode={switchMode} busy={busy}/><main><div className="page-heading"><div><div className="eyebrow">EMERGENCY OPERATIONS / DEMO ENVIRONMENT</div><h2>Clarity when it matters.</h2><p>Listen to residents. Verify the facts. Keep your community informed.</p></div><div className="connection"><span className={`live-dot ${mode==='live' && !connected ? 'offline' : ''}`}/>{mode==='mock' ? 'Local simulation active' : connected ? 'Backend connected · polling every 2s' : 'Connecting to backend…'}</div></div><div className={`feedback ${(error || pollError) ? 'error' : ''}`} role={(error || pollError) ? 'alert' : 'status'}>{error || pollError || (busy ? 'Processing action…' : notice) || 'Simulation only · Fictional data · Officer approval required for public clarifications'}</div><div className="main-grid"><IncomingFeed messages={state.messages}/><EmergingRumors sessionKey={sessionKey} state={state} onAction={onAction} busy={busy || (mode==='live' && !connected)}/><ResidentPhoneSimulator key={sessionKey} state={state} onAction={onAction} busy={busy || (mode==='live' && !connected)} mode={mode}/></div><div className="secondary-grid"><OutboundLog records={state.outbound}/><PipelineTrace records={state.trace}/></div><ChaosBar bulletins={state.bulletins} onAction={onAction} busy={busy || (mode==='live' && !connected)}/><footer><span><strong>TrueSignal</strong> / Reliable information. Human oversight.</span><span>HACKATHON DEMO · NO REAL EMERGENCY OR SMS SERVICE</span></footer></main></div>;
}
