import { useState } from 'react';
import StreamText from './StreamText.jsx';

/** Free-form resident text. Zone can also be picked by clicking the map.
 *  `busy` only locks it during a fast-forward: residents text whenever they like,
 *  and a silently swallowed Enter while Bedrock works elsewhere looks broken. */
export default function ResidentInput({ zones, zone, onZone, onSend, busy, phone, exchange }) {
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const current = zone || zones[0]?.id; // the select shows the first zone until one is picked
  async function submit(e) {
    e.preventDefault();
    if (!text.trim() || !current || !phone || sending || busy) return;
    setSending(true);
    try {
      if (await onSend({ from: phone, role: 'resident', zone: current, text: text.trim() })) setText('');
    } finally { setSending(false); }
  }
  return (
    <form className="resident" onSubmit={submit} data-tour="resident-input">
      <small>TEXT AS A RESIDENT</small>
      <div className="resident-row">
        <select aria-label="Zone" value={current || ''} onChange={e => onZone(e.target.value)}>
          {zones.map(z => <option key={z.id} value={z.id}>{z.label}</option>)}
        </select>
        <input aria-label="Message" placeholder="Ask anything…" value={text} onChange={e => setText(e.target.value)} />
        <button className="send" disabled={busy || sending || !text.trim()} aria-label="Send">↑</button>
      </div>
      {exchange && (
        <div className="exchange" aria-live="polite">
          <p className="asked">“{exchange.msg.text}”</p>
          {exchange.reply ? (
            <>
              <p className="answer"><StreamText text={exchange.reply.text} /></p>
              <small>TRUESIGNAL REPLY{exchange.ms ? ` · ${(exchange.ms / 1000).toFixed(1)}s` : ''}</small>
            </>
          ) : (
            <p className="muted">{exchange.pending ? 'Bedrock is reading it…'
              : exchange.rumor ? 'Part of a spreading rumor. Dana will answer it with a correction.'
              : 'No reply: there’s nothing here to check against official records.'}</p>
          )}
        </div>
      )}
    </form>
  );
}
