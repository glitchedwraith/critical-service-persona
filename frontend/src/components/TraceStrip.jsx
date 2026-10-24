import { latestTrace } from '../lib/derive.js';

const LABEL = { step1: 'Understand', step2: 'Verify', validator: 'Safety check', send: 'Send' };

/** One chip per pipeline stage: what Bedrock did and what code enforced. */
export default function TraceStrip({ trace }) {
  return (
    <footer className="trace glass" data-tour="trace" aria-label="Pipeline trace">
      {latestTrace(trace).map(({ step, entry }, i) => (
        <div key={step} className={`chip ${entry ? (entry.ok ? 'ok' : 'warn') : 'idle'}`} title={entry?.detail || ''}>
          {i > 0 && <span className="arrow">→</span>}
          <span className="dot" />{LABEL[step]}
          {entry && <span className="ms">{entry.ms ? `${entry.ms}ms` : entry.at}</span>}
        </div>
      ))}
    </footer>
  );
}
