# TrueSignal frontend

A full-screen San Jose map with three glass panels on top:

- **Situations (left):** the 14 guided demo situations. Click one and its one-line story streams into the caption at the top while the backend runs it. A small box at the bottom lets you text as a resident. Clicking a zone on the map picks the zone.
- **Map (center):** zones are tinted by what their residents are saying:
  - grey: calm
  - amber: rumor spreading
  - red: rumor reopened
  - blue: clarification sent
  - green: rumor resolved

  Shelter pins are coloured by status and drawn dashed when their status has expired. New texts appear as pings with a streamed bubble. Approved clarifications ripple across their target zones.
- **Dana (right):** the officer. She says what's happening in one streamed line and offers the next action: approve or edit a correction, trust one of two disagreeing sources, or redraft something that went stale.
- **Trace (bottom):** Understand (Step 1) → Verify (Step 2) → Safety check (validator) → Send, with latency.

The frontend holds **no demo data**. Everything comes from `GET /state`, which is loaded from `backend/seed/`. `src/test/no-demo-data.test.js` fails if seed IDs, phone numbers or venue names show up in `src/`.

## Run locally

Start the backend first (`scripts/start_backend.sh` from the repo root, port 3000), then:

```sh
cp .env.example .env      # set VITE_API_BASE_URL; optionally VITE_CARTO_API_KEY
npm install
npm run dev
```

`VITE_CARTO_API_KEY` turns on CARTO's dark basemap. Keyless CARTO tiles are now watermarked "API key required". Without a key the map falls back to Esri's keyless dark canvas. The key is embedded in the built bundle like any browser tile key, so restrict it by domain in the CARTO dashboard.

## Test

```sh
npm test
```

## Layout

```
src/
  App.jsx                    overlay layout
  hooks/useLiveState.js      polls /state every 1.5 s, reports new messages / broadcasts
  lib/derive.js              pure view-model: Dana's line + actions, zone moods, trace
  components/map/CityMap.jsx Leaflet map: zones, shelters, pings, ripples
  components/DanaPanel.jsx   avatar + streamed speech + actions
  components/StreamText.jsx  left-to-right text streaming
  components/…               TopBar, SituationRail, Narration, TraceStrip, ResidentInput
```
