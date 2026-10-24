import { useEffect, useState } from 'react';
import DanaAvatar from './DanaAvatar.jsx';
import StreamText from './StreamText.jsx';

const STATE_LABEL = { draft: 'Draft', approved: 'Approved', sent: 'Sending', delivered: 'Delivered', failed: 'Failed' };

/** Dana, the officer: says what is happening in one line and offers the next action. */
export default function DanaPanel({ focus, state, onAction, busy }) {
  const [speaking, setSpeaking] = useState(false);
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState('');
  const draft = focus.draft;
  useEffect(() => { setEditing(false); setText(draft?.text || ''); }, [draft?.id, draft?.text]);

  const recent = state.outbound.filter(o => o.kind === 'clarification' && o.state !== 'draft').slice(0, 3);
  const approver = state.system.approver;

  async function run(a) {
    if (a.kind === 'edit') { setEditing(e => !e); return; }
    if (a.kind === 'approve') {
      if (editing && text !== draft.text && !(await onAction('edit', { id: draft.id, text }))) return;
      await onAction('approve', { id: a.payload.id, approver });
    } else if (a.kind === 'verify') await onAction('verify', a.payload);
    else await onAction(a.action, a.payload);
    setEditing(false);
  }

  return (
    <aside className={`dana glass mood-${focus.mood}`}>
      <div className="dana-head">
        <DanaAvatar mood={focus.mood} speaking={speaking} />
        <div>
          <div className="dana-name">{approver || 'Officer'}</div>
          <div className="muted">Public Information Officer · EOC</div>
        </div>
      </div>

      <div className="speech" aria-live="polite">
        <StreamText text={focus.line} onStreaming={setSpeaking} />
      </div>

      {draft && (
        editing
          ? <textarea className="draft edit" value={text} onChange={e => setText(e.target.value)} rows={5} aria-label="Edit draft" />
          : <blockquote className="draft">{draft.text}
              {(draft.validator?.flags || []).length > 0 && <span className="flagline">Safety check: {draft.validator.flags.join(', ').replaceAll('_', ' ')}</span>}
            </blockquote>
      )}

      {focus.actions.length > 0 && (
        <div className="dana-actions">
          {focus.actions.map(a => (
            <button key={a.label} className={a.primary ? 'primary' : 'ghost'} disabled={busy} onClick={() => run(a)}>
              {a.kind === 'edit' && editing ? 'Cancel edit' : a.label}
            </button>
          ))}
        </div>
      )}

      {recent.length > 0 && (
        <ul className="sent-log">
          {recent.map(o => (
            <li key={o.id} className={`st-${o.state} ${o.outdated ? 'outdated' : ''}`}>
              <span className="dot" />{STATE_LABEL[o.state] || o.state}
              <span className="muted"> · {o.approved_at || o.created_at}{o.outdated ? ' · outdated' : ''}</span>
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
