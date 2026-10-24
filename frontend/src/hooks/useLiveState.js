import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../services/api.js';
import { replayTo } from '../lib/replay.js';

const POLL_MS = 1500;
const FAST_POLL_MS = 500; // while Bedrock or a situation is working, so short calls aren't missed
const EMPTY = { system: {}, zones: [], sources: [], situations: [], messages: [], rumors: [],
  outbound: [], shelters: [], bulletins: [], trace: [] };

function normalize(value) {
  const out = { ...EMPTY, system: value?.system || {} };
  for (const key of Object.keys(EMPTY)) if (key !== 'system' && Array.isArray(value?.[key])) out[key] = value[key];
  return out;
}

/**
 * Polls GET /state and reports what is new since the previous poll, so the
 * map can animate arrivals. The backend is threaded, so polling continues
 * while a long situation runs and messages appear as they are processed.
 */
export default function useLiveState() {
  const [state, setState] = useState(EMPTY);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState('');
  const [arrivals, setArrivals] = useState({ messages: [], broadcasts: [] });
  const seen = useRef(null);
  const timer = useRef(null);
  const inflight = useRef(0);
  const quiet = useRef(false); // fast-forwarding: don't animate replayed traffic
  const fast = useRef(false);

  const poll = useCallback(async () => {
    clearTimeout(timer.current);
    try {
      const next = normalize(await api.state());
      const sentNow = next.outbound.filter(o => o.kind === 'clarification' && ['sent', 'delivered'].includes(o.state));
      if (seen.current && !quiet.current) {
        const messages = next.messages.filter(m => !seen.current.messages.has(m.id));
        const broadcasts = sentNow.filter(o => !seen.current.broadcasts.has(o.id));
        if (messages.length || broadcasts.length) setArrivals({ messages, broadcasts, at: Date.now() });
      }
      seen.current = {
        messages: new Set(next.messages.map(m => m.id)),
        broadcasts: new Set(sentNow.map(o => o.id)),
      };
      fast.current = Boolean(next.system.active_situation?.running || next.system.ai?.thinking?.length);
      setState(next); setConnected(true); setError('');
    } catch (e) {
      setConnected(false); setError(e.message);
    } finally {
      timer.current = setTimeout(poll, fast.current || inflight.current ? FAST_POLL_MS : POLL_MS);
    }
  }, []);

  useEffect(() => { poll(); return () => clearTimeout(timer.current); }, [poll]);

  const act = useCallback(async (action, payload) => {
    setError('');
    inflight.current += 1;
    poll(); // switch to fast polling right away
    try {
      const result = await api.act(action, payload);
      if (action === 'reset') seen.current = null; // don't animate the reseed
      return result;
    } catch (e) {
      setError(e.message);
      return null;
    } finally {
      inflight.current -= 1;
      poll();
    }
  }, [poll]);

  /** Reset this session and fast-forward to just before situation `id`. */
  const jump = useCallback(async (id, onProgress) => {
    setError('');
    inflight.current += 1; quiet.current = true;
    try {
      await replayTo(api, id, onProgress);
      return true;
    } catch (e) {
      setError(e.message);
      return false;
    } finally {
      inflight.current -= 1; quiet.current = false; seen.current = null;
      poll();
    }
  }, [poll]);

  return { state, connected, error, arrivals, act, jump };
}
