import { useState } from 'react';

/** Free-form resident text. Zone can also be picked by clicking the map. */
export default function ResidentInput({ zones, zone, onZone, onSend, busy, phone }) {
  const [text, setText] = useState('');
  async function submit(e) {
    e.preventDefault();
    if (!text.trim() || !zone || !phone) return;
    if (await onSend({ from: phone, role: 'resident', zone, text: text.trim() })) setText('');
  }
  return (
    <form className="resident" onSubmit={submit}>
      <small>TEXT AS A RESIDENT</small>
      <div className="resident-row">
        <select aria-label="Zone" value={zone || ''} onChange={e => onZone(e.target.value)}>
          {zones.map(z => <option key={z.id} value={z.id}>{z.label}</option>)}
        </select>
        <input aria-label="Message" placeholder="Ask anything…" value={text} onChange={e => setText(e.target.value)} />
        <button className="send" disabled={busy || !text.trim()} aria-label="Send">↑</button>
      </div>
    </form>
  );
}
