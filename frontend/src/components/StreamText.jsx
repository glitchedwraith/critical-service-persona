import { useEffect, useState } from 'react';

/** Reveals `text` left to right, ChatGPT-style. Restarts when text changes. */
export default function StreamText({ text = '', speed = 22, onStreaming, className = '' }) {
  const [shown, setShown] = useState(0);
  useEffect(() => {
    setShown(0);
    if (!text) return undefined;
    onStreaming?.(true);
    let n = 0;
    const id = setInterval(() => {
      n += Math.max(1, Math.round(text.length / 120)); // long lines finish in ~3s
      setShown(Math.min(n, text.length));
      if (n >= text.length) { clearInterval(id); onStreaming?.(false); }
    }, speed);
    return () => { clearInterval(id); onStreaming?.(false); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, speed]);
  const done = shown >= text.length;
  return (
    <span className={`stream ${className}`} aria-label={text}>
      <span aria-hidden="true">{text.slice(0, shown)}</span>
      {!done && <span className="caret" aria-hidden="true" />}
    </span>
  );
}
