import { situationStatus } from '../lib/derive.js';
import ResidentInput from './ResidentInput.jsx';

export default function SituationRail({ state, onRun, busy, danaWaiting, zone, onZone, onSend }) {
  const status = situationStatus(state);
  return (
    <aside className="rail glass">
      <div className="rail-head">
        <small>SITUATIONS</small>
        <span className="muted">{(state.system.situations_done || []).length}/{state.situations.length}</span>
      </div>
      <ol className="situations">
        {state.situations.map((s, i) => (
          <li key={s.id} className={`sit ${status[s.id]}`}>
            <button onClick={() => onRun(s.id)} disabled={busy} title={s.narration}>
              <span className="num">{status[s.id] === 'done' ? '✓' : i + 1}</span>
              <span className="sit-title">{s.title}</span>
              {status[s.id] === 'next' && <span className="next-tag">{danaWaiting ? 'Dana first' : 'Next'}</span>}
            </button>
          </li>
        ))}
      </ol>
      <ResidentInput phone={state.system.demo_phone} zones={state.zones} zone={zone} onZone={onZone} onSend={onSend} busy={busy} />
    </aside>
  );
}
