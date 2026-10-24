import { useEffect, useState } from 'react';

const STEP = { understand: 'understanding', verify: 'verifying' };
const OFFLINE = {
  expired: 'credentials expired',
  missing: 'no credentials',
  denied: 'access denied',
  error: 'unreachable',
};
const secs = ms => `${(ms / 1000).toFixed(1)}s`;

/** Bedrock health + live "thinking" timer, from system.ai in GET /state. */
export default function AiPill({ ai }) {
  const call = ai?.thinking?.[0];
  const [, tick] = useState(0);
  const [polledAt, setPolledAt] = useState(Date.now());
  useEffect(() => { setPolledAt(Date.now()); }, [call?.elapsed_ms]);
  useEffect(() => {
    if (!call) return undefined;
    const id = setInterval(() => tick(t => t + 1), 100);
    return () => clearInterval(id);
  }, [call]);

  if (!ai?.status) return null;
  if (ai.status !== 'ok') {
    return (
      <div className="pill bad ai" role="status"
        title={`Bedrock ${ai.detail || ai.status}. Answers use the safe rule-based fallback until credentials are refreshed.`}>
        AI offline · {OFFLINE[ai.status] || ai.status}
      </div>
    );
  }
  if (call) {
    const elapsed = call.elapsed_ms + (Date.now() - polledAt);
    return (
      <div className="pill ai thinking" role="status" title="Amazon Bedrock · Claude Haiku 4.5">
        <span className="spinner" />Bedrock {STEP[call.step] || 'thinking'}… {secs(elapsed)}
      </div>
    );
  }
  return (
    <div className="pill good ai" title="Amazon Bedrock · Claude Haiku 4.5 · time of the last model call">
      Bedrock {ai.last_ms ? `· answered in ${secs(ai.last_ms)}` : 'ready'}
    </div>
  );
}
