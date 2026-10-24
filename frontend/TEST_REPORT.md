# TrueSignal functional verification

Date: October 23, 2026. Scope: local frontend testing and bug fixes only. No Git operations, deployment, backend integration, or real AI testing. The dashboard layout, theme, styles, and seven-section component structure were preserved.

## Final results

| Executed check | Result |
| --- | --- |
| Original `npm.cmd test`, before changes | 9 passed, 0 failed |
| Final `npm.cmd test` | **38 passed, 0 failed, 0 skipped** |
| Final service tests | 14 mock workflow tests + 4 API-client tests passed |
| Final React interaction tests | 20 passed in jsdom |
| Final `npm.cmd run build` | **Passed**, 40 modules transformed, no unresolved imports or build-blocking errors |
| Browser automation availability | Checked; no apps or browsers exposed |
| Real-browser interaction / visual testing | **Not performed** |
| Real backend / AI verification | **Not performed**, as requested |

The first sandboxed build was blocked by filesystem access to an ancestor directory. The same build command succeeded outside that restriction, both before and after the fixes. This was an environment restriction, not a source compilation failure.

The existing Node test runner was retained. Added jsdom as a development-only dependency, plus a small JSX loader using the existing Vite/esbuild transformer. No new production dependency, UI library, or separate test framework was added. Run the full suite with Node.js 24+.

Regression tests reproduced failures before their fixes. One early failing assertion tried to format an entire DOM element and exhausted the test process; the assertion now checks a boolean without serializing the DOM. The complete final test run finished cleanly.

## Bugs discovered and fixed

| Bug / cause | Minimal fix and regression coverage |
| --- | --- |
| Two rapid mock actions read the same pre-render state, dropping one update. | Update the current-state ref immediately with each successful transition. Two waves dispatched in one React batch now retain both updates. |
| Reset restored records but left an old unsaved draft editor open. Mode switches also carried local form/editor state between data sources. | Reset a session key only on successful reset or mode change. Draft editors and phone forms reset; ordinary updates retain rumor-card DOM identity and open evidence disclosures. |
| A null rate-history entry crashed the rumor card while reading `count`. | Accept absent entries and clamp invalid, nonfinite, or negative chart values to zero. Optional-data DOM test passes. |
| Null state normalization threw, and an absent rumor message count became `NaN` on inbound SMS. | Normalize a null state to empty sections and initialize missing counts to zero. Partial-state regression test passes. |
| Mock verification checked cached source expiry but ignored the evidence snapshot deadline and silently discarded unresolved evidence references. | Check all supplied evidence references and their deadlines. Missing or expired evidence prevents a passing validator and approval. |
| Mock approval trusted validator metadata without rejecting empty text, missing approver, incorrect rumor/clarification linkage, or an expired outbound deadline. | Validate these conditions before mutation. Regression tests cover each rejection and ensure repeated approval does not create another send. |
| Expiry flagged only the currently linked clarification; older sent versions could appear current in the log. | Mark all outbound versions with expired source IDs or deadlines as outdated. Regression test covers a sent version followed by a newer draft. |
| SMS bubbles with the same simulated minute grouped all incoming messages before their replies. | Use the actual `message_id` / `reply_id` relationship to break timestamp ties. DOM test confirms incoming/reply/incoming/reply order. |
| An empty API response could appear successful; JSON `null` caused an internal property-access error. | Reject empty, null, and array payloads with clear API errors. Stubbed-response tests cover these cases. |

## Workflows actually exercised

The following are automated behavior checks, not visual browser checks.

- **Incoming feed:** fixture messages render, newest item is first, a newly sent SMS appears first, role/sender/zone are retained, the visible feed stops at 50 while the footer retains the total count.
- **Rumors and evidence:** all five fixtures render, statuses/verdicts and expired/missing evidence appear, source verification updates the correct clarification, native disclosure state toggles and survives an unrelated update, the rumor card DOM node remains stable.
- **Draft editing:** existing text loads, cancel leaves the record unchanged, whitespace disables save, save updates the linked outbound record, another rumor is untouched, delivered records have no Edit control. Edited mock drafts remain blocked pending source reverification, as documented.
- **Approval:** eligible drafts become sent and the linked rumor enters monitoring; rejected, blank, expired, unvalidated, or mismatched drafts do not send. Repeated approval cannot duplicate a send. Advancing the simulated clock delivers sent records and reevaluates rumor monitoring/expiry.
- **Phone:** sender/role/zone/text fields accept changes; sending updates both conversation and feed; a holding reply appears; empty/whitespace messages cannot submit through the button; sending disables the button and failed submissions show feedback.
- **Outbound/trace:** seed records render, draft/sent/delivered states and expiry warnings are exercised, mock actions append trace events, minimal optional records and empty lists render safely.
- **Chaos:** all six controls update mock state; three repeated sequences preserve unique message/rumor/outbound IDs; expiry uses the selected current bulletin ID; no-bulletin expiry and pending controls cannot dispatch actions.
- **Reset:** the service returns a deep copy equal to the complete original fixture, including clock, messages, rumors, outbound, sources, and trace. The DOM restores record counts and original clarification text, closes unsaved editing, and remains usable for subsequent actions.
- **Mode separation:** SMS and all chaos/reset actions make zero Fetch calls in the dedicated Mock Mode checks. Mode switching preserves modified mock data. Live tests use only locally stubbed Fetch; returning to Mock Mode aborts the read signal and prevents additional polling.
- **API preparedness:** all required endpoint mappings and POST bodies, encoded IDs, JSON/network/empty-response errors, abort propagation, pending action locks, validator rejection feedback after refresh, partial reset failure, and nonoverlapping polling were executed with stubs and controlled timers.

## Code inspection only: layout and scrolling

- All seven requested dashboard sections are wired in `App.jsx`.
- Feed, rumors, outbound, and trace use bounded-height `.panel-scroll` containers with `overflow-y: auto`, horizontal clipping, and contained overscroll.
- The phone conversation has its own bounded height, `overflow-y: auto`, and contained overscroll.
- No fixed-height or hidden-overflow rule locks the document; the overall page can grow vertically.
- Grid children use `min-width: 0`; content wraps and responsive grid rules remain in place. No CSS was changed during this task.
- API URL construction and native Fetch remain centralized in `src/services/api.js`. Mock state transitions do not import or call the API client.

These observations establish the intended implementation. jsdom has no layout engine, so independent wheel scrolling, actual scrollbar geometry, scroll position preservation, and absence of rendered horizontal overflow were **not** proven by the automated tests.

## Manual browser checks still required

Run `npm.cmd run dev`, keep Mock Mode selected, and check:

1. At 1920×1080, all sections are readable and the document has no horizontal scrollbar. Resize to a narrower window to check the existing fallback layout.
2. Scroll the feed, rumors, phone conversation, outbound, and trace individually; confirm other panels stay still and scroll does not chain into the page at panel boundaries.
3. Confirm focus visibility, keyboard access, textarea resizing, native required-field feedback, and evidence disclosure behavior in the actual browser.
4. Check the visible button walkthrough, conversation position after sending, and retention of panel scroll positions during ordinary mock updates. Automated tests cover DOM state, not the rendered experience.

No known build-blocking or automated-workflow failure remains. Browser-specific behavior remains unverified. Existing mock limitations remain: source timestamps assume a same-day scenario; freeform draft edits require reverification that regenerates a source-supported mock clarification; zone-wide broadcasts are shown in the outbound log rather than expanded to individual phone conversations. These are documented simulation boundaries, not real AI verification.

## Future backend and AI integration

Teammates must still confirm CORS, configured API origin, actual response schemas, source authority/ref relationships, authoritative validator policies, genuine model outputs, reset seed import behavior, outbound delivery transitions, and polling under real latency. No real backend endpoint, SMS provider, or AI service was contacted during these checks. Missing backend/AI services were not treated as frontend defects.

## Files changed

- Functional fixes: `src/App.jsx`, `src/components/EmergingRumors.jsx`, `src/components/ResidentPhoneSimulator.jsx`, `src/services/mockService.js`, `src/services/api.js`.
- Tests: expanded `src/services/mockService.test.js` and `src/services/api.test.js`; added `src/test/register.js`, `src/test/dom.js`, and `src/test/dashboard.test.jsx`.
- Test setup/documentation: `package.json`, `package-lock.json`, `README.md`, and this report. Generated production output is inside ignored `dist/`.

All work stayed inside `frontend/`.
