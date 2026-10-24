# TrueSignal frontend

A single-page emergency operations dashboard. **All emergency data and SMS delivery are fictional simulations.** Starts in Mock Mode; no backend is needed.

## Run locally

Development/build requires Node.js 20.19+ or 22.12+ and npm. Use Node.js 24+ for the complete automated test suite (the JSX test loader uses Node's module hooks).

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

Open the local URL printed by Vite (usually http://127.0.0.1:5173). On other shells, `npm` can replace `npm.cmd`.

```powershell
npm.cmd test
npm.cmd run build
npm.cmd run preview
```

## Implementation

- `src/components/`: all seven requested dashboard sections and small shared presentation helpers.
- `src/mock/state.json`: fictional flood scenario, 24 messages, five rumors, shelter/bulletin sources, drafts, delivered messages, and pipeline events.
- `src/services/mockService.js`: independent, immutable mock state transitions; no network calls.
- `src/services/api.js`: native Fetch client, endpoint mapping, encoded record IDs, JSON and network error handling.
- `src/App.jsx`: mode switching, action feedback, independent mock-state preservation, abortable sequential live polling every two seconds after a response completes.
- `src/App.css`: desktop-first three-column layout, independent panel scrolling, responsive fallback, keyboard focus styles.

## Try the demo

1. Send an SMS about Shelter A. Its cluster count grows and a simulated holding reply appears in the phone.
2. Verify R-001, review its evidence and validator, then approve its draft. It enters monitoring and its outbound record becomes sent.
3. Advance the clock. Sent records become delivered. Quiet monitoring rumors resolve; expired evidence can reopen them immediately.
4. Reset, then choose Shelter A full. Its old clarification is flagged and its rumor reopens. Verify to generate a clarification using the updated official capacity.
5. Try the rumor wave, conflicting report, city website outage, and bulletin expiry controls. The bulletin selector always uses current state IDs.
6. Edit any draft. In the mock, arbitrary edited text requires source reverification; verification regenerates the supported clarification. This is intentionally a simple simulation of validation, not semantic claim verification.

Mock records survive mode switching within the same page session. Reloading starts a fresh demo. Reset restores the fixture. Mock delivery progresses through the simulated clock action, not real-world timers. Unknown claims receive no invented evidence. All mock clarifications require officer approval; `auto_send_ok` is never used to bypass it.

## Connect the backend

Copy `.env.example` to `.env` inside `frontend/`, set `VITE_API_BASE_URL`, and restart Vite. Defaults to `http://localhost:8000`. Select **Live API**. The backend must allow CORS from the Vite origin. No credentials or authentication scheme is assumed.

Live mode implements all specified endpoints. POST actions refresh state afterward; polling never intentionally overlaps another poll. Switching modes aborts outstanding reads. Mock fixtures are never shown as backend state. Backend rejection remains visible even after a successful state refresh. A reset with `seed_imported: false` reports an incomplete reset.

API assumptions to confirm with teammates:

- `/state` returns the state object directly; action responses return objects directly, without a `data` wrapper.
- `rate_per_10min` is an array of counts; a scalar and objects with `count`, `rate`, or `value` are also accepted for display.
- Evidence `ref` or `source_id` may reference a shelter or bulletin ID. Unresolvable sources display only the supplied reference and metadata.
- `clarification_id` identifies the actual outbound record. No claim-text or array-position matching is used.
- Only outbound records with state `draft` are editable. Approval requires explicit `validator.passed: true` and fresh evidence; the backend remains responsible for authoritative validation and rejection.
- Times are simulated HH:MM strings. Mock freshness assumes a same-day scenario; multi-day rollover needs a backend-provided date or monotonic clock.
- Chaos actions accept the contract bodies. Reset may omit `seed_imported`; explicit `false` is a partial failure.
- Phone conversation includes messages from the exact selected number and sent/delivered outbound records addressed to that number. Zone-wide broadcasts remain in the outbound log because recipient expansion is a backend concern.

Live backend validation still required: CORS, actual payload shapes, source relationships, validator/rejection semantics, reset seed errors, real delivery transitions, and end-to-end polling under backend latency. Unit tests use stubbed Fetch responses and do not require the backend.

Verification: see [TEST_REPORT.md](./TEST_REPORT.md) for the latest executed tests, regression fixes, and manual checks. `npm.cmd test` runs the Node service tests and React interaction tests in jsdom. `npm.cmd run test:services` runs only the service tests. jsdom is a simulated DOM; it does not verify rendered layout, scrolling, or browser visuals. Live-mode tests replace Fetch with local stubs and never connect to a backend.

The subsequent readability pass and original-requirements audit are recorded in [UI_REFINEMENT_AUDIT.md](./UI_REFINEMENT_AUDIT.md): 42 tests passed, including four additional polling checks; the production build passed. The original functional test report above records the earlier 38-test run.
