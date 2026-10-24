import { useEffect, useMemo, useState } from 'react';
import L from 'leaflet';
import { MapContainer, Marker, Polygon, TileLayer, Tooltip, useMap } from 'react-leaflet';
import { shelterTone, zoneMoods, zonesFromTarget } from '../../lib/derive.js';
import StreamText from '../StreamText.jsx';

// CARTO dark basemap when a key is configured (keyless CARTO tiles are now
// watermarked); otherwise fall back to Esri's keyless dark canvas.
const CARTO_KEY = import.meta.env?.VITE_CARTO_API_KEY;
const ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas';
const LAYERS = CARTO_KEY
  ? [{ url: `https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png?key=${CARTO_KEY}`, subdomains: 'abcd', maxZoom: 19,
       attribution: '© OpenStreetMap contributors, © CARTO' }]
  : [{ url: `${ESRI}/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}`, maxZoom: 16,
       attribution: 'Tiles © Esri — Esri, HERE, Garmin, © OpenStreetMap contributors' },
     { url: `${ESRI}/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}`, maxZoom: 16, opacity: 0.45 }];
const PING_MS = 9000;
const RIPPLE_MS = 2600;
const MOOD_COLOR = { calm: '#64748b', good: '#34d399', informed: '#60a5fa', alert: '#fbbf24', critical: '#f87171' };

const iconCache = new Map();
const shelterIcon = (s) => {
  const key = `${s.id}:${shelterTone(s)}`;
  if (!iconCache.has(key)) iconCache.set(key, makeShelterIcon(s));
  return iconCache.get(key);
};
const makeShelterIcon = (s) => L.divIcon({
  className: '',
  iconSize: [34, 34], iconAnchor: [17, 17],
  html: `<div class="shelter-pin tone-${shelterTone(s)}"><span>${s.id.split('-').pop()}</span></div>`,
});
const pingIcon = (tone) => L.divIcon({ className: '', iconSize: [18, 18], iconAnchor: [9, 9],
  html: `<div class="ping tone-${tone}"><i></i></div>` });
// Zone name sits just inside the zone's northern edge, clear of shelter pins.
const labelPoint = z => [Math.max(...z.polygon.map(p => p[0])) - 0.006, z.centroid[1]];
const zoneLabel = z => L.divIcon({ className: '', iconSize: [120, 16], iconAnchor: [60, 8],
  html: `<div class="zone-label">${z.label}</div>` });
const rippleIcon = L.divIcon({ className: '', iconSize: [10, 10], iconAnchor: [5, 5], html: '<div class="ripple"></div>' });

/** Fit all zones once they load; fly to a focus when one is set. */
function Camera({ zones, focus }) {
  const map = useMap();
  const [fitted, setFitted] = useState(false);
  useEffect(() => {
    if (fitted || !zones.length) return;
    map.fitBounds(zones.flatMap(z => z.polygon), { paddingTopLeft: [320, 110], paddingBottomRight: [390, 70], maxZoom: 13 });
    setFitted(true);
  }, [zones, fitted, map]);
  useEffect(() => {
    if (focus?.length) map.flyToBounds(focus, { paddingTopLeft: [320, 200], paddingBottomRight: [390, 70], maxZoom: 14, duration: 0.9 });
  }, [focus, map]);
  return null;
}

/** Keep transient items (pings, ripples) alive for `ttl` ms after they arrive. */
function useTransient(items, ttl) {
  const [live, setLive] = useState([]);
  useEffect(() => {
    if (!items.length) return undefined;
    const stamped = items.map(i => ({ ...i, _until: Date.now() + ttl }));
    setLive(prev => [...prev.filter(p => p._until > Date.now()), ...stamped]);
    const t = setTimeout(() => setLive(prev => prev.filter(p => p._until > Date.now())), ttl + 50);
    return () => clearTimeout(t);
  }, [items, ttl]);
  return live;
}

export default function CityMap({ state, arrivals, focusZones, onZoneClick, selectedZone }) {
  const moods = useMemo(() => zoneMoods(state), [state]);
  const rumors = useMemo(() => Object.fromEntries(state.rumors.map(r => [r.id, r])), [state.rumors]);
  const pings = useTransient(arrivals.messages || [], PING_MS);
  const ripples = useTransient(useMemo(() => (arrivals.broadcasts || []).flatMap(o =>
    zonesFromTarget(o.to).map(zid => ({ id: `${o.id}-${zid}`, zone: zid }))), [arrivals.broadcasts]), RIPPLE_MS);
  const messagesById = useMemo(() => Object.fromEntries(state.messages.map(m => [m.id, m])), [state.messages]);
  const zonesById = useMemo(() => Object.fromEntries(state.zones.map(z => [z.id, z])), [state.zones]);
  const focus = useMemo(() => focusZones?.flatMap(id => zonesById[id]?.polygon || []), [focusZones, zonesById]);
  const latest = pings.filter(p => p.lat != null).at(-1);

  return (
    <MapContainer className="city-map" center={[37.3382, -121.8863]} zoom={13}
      zoomControl={false}>
      {LAYERS.map(l => <TileLayer key={l.url} {...l} />)}
      <Camera zones={state.zones} focus={focus} />

      {state.zones.map(z => {
        const mood = moods[z.id] || 'calm';
        return (
          <Polygon key={z.id} positions={z.polygon}
            eventHandlers={{ click: () => onZoneClick?.(z.id) }}
            pathOptions={{
              color: MOOD_COLOR[mood], weight: selectedZone === z.id ? 3 : 1.5,
              fillColor: MOOD_COLOR[mood], fillOpacity: mood === 'calm' ? 0.06 : 0.16,
              className: `zone zone-${mood}`,
            }}>
          </Polygon>
        );
      })}

      {state.zones.map(z => (
        <Marker key={`label-${z.id}`} position={labelPoint(z)} icon={zoneLabel(z)} interactive={false} />
      ))}

      {state.shelters.filter(s => s.lat != null).map(s => (
        <Marker key={s.id} position={[s.lat, s.lng]} icon={shelterIcon(s)}>
          <Tooltip direction="top" offset={[0, -16]} className="glass-tip">
            <b>{s.name}</b><br />
            {s.status}{s.capacity ? ` · ${s.occupancy}/${s.capacity}` : ''}<br />
            <span className="muted">as of {s.status_updated_at}{s.expired ? ' · expired' : ''}</span>
          </Tooltip>
        </Marker>
      ))}

      {pings.filter(p => p.lat != null).map(m => {
        // Step 1 assigns the cluster after the message row lands; read it fresh.
        const r = rumors[messagesById[m.id]?.cluster_id || m.cluster_id];
        const tone = r ? (r.status === 'reopened' ? 'critical' : 'alert') : 'calm';
        return (
          <Marker key={m.id} position={[m.lat, m.lng]} icon={pingIcon(tone)}>
            {latest?.id === m.id && (
              <Tooltip permanent direction="right" offset={[12, 0]} className="bubble-tip">
                <StreamText text={m.text} speed={18} />
              </Tooltip>
            )}
          </Marker>
        );
      })}

      {ripples.map(r => zonesById[r.zone] && (
        <Marker key={r.id} position={zonesById[r.zone].centroid} icon={rippleIcon} interactive={false} />
      ))}
    </MapContainer>
  );
}
