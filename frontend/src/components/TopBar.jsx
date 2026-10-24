export default function TopBar({ system, connected, onReset, busy }) {
  const online = system.city_site_online;
  return (
    <header className="topbar glass">
      <div className="brand"><span className="logo">◉</span> TrueSignal <span className="sim-pill">SIMULATION</span></div>
      <div className="vitals">
        <div className="clock"><small>SIM CLOCK</small>{system.sim_clock || '--:--'}</div>
        <div className={`pill ${online === false ? 'bad' : 'good'}`}>City site {online === false ? 'offline' : 'online'}</div>
        {system.cache_as_of && <div className="pill">Cache {system.cache_as_of}</div>}
        {system.delivery_fail_mode && <div className="pill bad">SMS gateway failing</div>}
      </div>
      <div className="top-actions">
        <span className={`conn ${connected ? 'on' : ''}`}>{connected ? 'Live' : 'Connecting…'}</span>
        <button className="ghost" onClick={onReset} disabled={busy}>Reset demo</button>
      </div>
    </header>
  );
}
