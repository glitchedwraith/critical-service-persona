import { situationStatus } from '../lib/derive.js';
import ResidentInput from './ResidentInput.jsx';

export default function SituationRail({ state, onRun, onJump, replaying, busy, danaWaiting, zone, onZone, onSend }) {
  const status = situationStatus(state);
  return (
    <aside className="rail glass" data-tour="situations">
      <div className="rail-head">
        <small>SITUATIONS</small>
        {replaying
          ? <span className="replaying">Fast-forwarding{replaying.total ? ` ${replaying.done}/${replaying.total}` : '…'}</span>
          : <span className="muted">{(state.system.situations_done || []).length}/{state.situations.length}</span>}
      </div>
      <ol className="situations">
        {state.situations.map((s, i) => (
          <li key={s.id} className={`sit ${status[s.id]}`}>
            <button data-tour={status[s.id] === 'next' ? 'situation-next' : undefined} onClick={() => onRun(s.id)} disabled={busy} title={s.narration}>
              <span className="num">{status[s.id] === 'done' ? '✓' : i + 1}</span>
              <span className="sit-title">{s.title}</span>
              {status[s.id] === 'next' && <span className="next-tag">{danaWaiting ? 'Dana first' : 'Next'}</span>}
            </button>
            {(status[s.id] === 'done' || status[s.id] === 'idle') && (
              <button className="jump" onClick={() => onJump(s.id)} disabled={busy}
                title={`Reset your demo and fast-forward to “${s.title}”`}>Start here</button>
            )}
          </li>
        ))}
      </ol>
      <ResidentInput phone={state.system.demo_phone} zones={state.zones} zone={zone} onZone={onZone} onSend={onSend} busy={busy} />
    </aside>
  );
}
