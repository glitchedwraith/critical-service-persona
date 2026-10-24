import { useMemo, useState } from 'react';
import useLiveState from './hooks/useLiveState.js';
import { danaFocus } from './lib/derive.js';
import CityMap from './components/map/CityMap.jsx';
import TopBar from './components/TopBar.jsx';
import SituationRail from './components/SituationRail.jsx';
import Narration from './components/Narration.jsx';
import DanaPanel from './components/DanaPanel.jsx';
import TraceStrip from './components/TraceStrip.jsx';
import useGuidedTour from './tour/useGuidedTour.js';

export default function App() {
  const { state, connected, error, arrivals, act } = useLiveState();
  const [pending, setPending] = useState(false);
  const [zone, setZone] = useState(null);
  const focus = useMemo(() => danaFocus(state), [state]);
  const running = Boolean(state.system.active_situation?.running);
  const busy = pending || running || !connected;
  const tour = useGuidedTour({ state, focus, busy, running, connected });

  // Fly to the zones Dana is talking about (drafts carry their target zones).
  const focusZones = useMemo(() => {
    const m = /^zone:(.+)$/.exec(focus.draft?.to || '');
    return m && m[1] !== 'all' ? m[1].split(',') : null;
  }, [focus.draft?.to]);

  async function onAction(action, payload) {
    setPending(true);
    try { return Boolean(await act(action, payload)); } finally { setPending(false); }
  }

  return (
    <div className="app">
      <div className="map-layer">
        <CityMap state={state} arrivals={arrivals} focusZones={focusZones}
          selectedZone={zone} onZoneClick={setZone} />
      </div>
      <div className="overlay">
        <TopBar system={state.system} connected={connected} busy={busy} onReset={() => onAction('reset', {})} onTour={() => tour.replay(() => onAction('reset', {}))} />
        <div className="middle">
          <SituationRail state={state} busy={busy} danaWaiting={focus.actions.length > 0}
            onRun={id => onAction('situation', { id })}
            zone={zone || state.zones[0]?.id} onZone={setZone}
            onSend={payload => onAction('sms', payload)} />
          <div className="center">
            <Narration situation={state.system.active_situation} />
            {error && <div className="toast" role="alert">{error}</div>}
          </div>
          <DanaPanel focus={focus} state={state} onAction={onAction} busy={busy} />
        </div>
        <TraceStrip trace={state.trace} />
      </div>
    </div>
  );
}
