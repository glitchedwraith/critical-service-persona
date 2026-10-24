import AiPill from './AiPill.jsx';

export default function TopBar({ system, connected, onReset, onTour, busy }) {
  const online = system.city_site_online;
  return (
    <header className="topbar glass">
      <div className="brand"><span className="logo">◉</span> TrueSignal <span className="sim-pill">SIMULATION</span></div>
      <div className="vitals" data-tour="vitals">
        <div className="clock"><small>SIM CLOCK</small>{system.sim_clock || '--:--'}</div>
        <div className={`pill ${online === false ? 'bad' : 'good'}`}>City site {online === false ? 'offline' : 'online'}</div>
        {system.cache_as_of && <div className="pill">Cache {system.cache_as_of}</div>}
        {system.delivery_fail_mode && <div className="pill bad">SMS gateway failing</div>}
        <AiPill ai={system.ai} />
        {system.session === 'shared' && (
          <div className="pill warn" title="The demo is busy, so you're sharing one copy with other visitors. Their clicks and resets show up here too.">
            Shared demo
          </div>
        )}
      </div>
      <div className="top-actions" data-tour="top-actions">
        <span className={`conn ${connected ? 'on' : ''}`}>{connected ? 'Live' : 'Connecting…'}</span>
        <button className="ghost" onClick={onTour} data-tour="tour-button">Take the tour</button>
        <button className="ghost" onClick={onReset} disabled={busy} data-tour="reset">Reset demo</button>
      </div>
    </header>
  );
}
