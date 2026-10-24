# Readability refinement and requirements audit

October 23, 2026. Local frontend only. No Git operations, deployment, real backend requests, new features, or dependency installation.

## Changes and verification

- **CSS/layout file:** `src/App.css` only. The colors, three-column proportions, main panel arrangement, and component structure remain unchanged.
- **Typography:** message and clarification text is 15px; other main content and buttons are 14px; panel headings are 18px; secondary labels, validator badges, evidence timestamps, and metadata are at least 12px. Main branding and page-title sizes retain their existing hierarchy. Desktop overrides no longer shrink phone text back to its earlier size.
- **Spacing:** buttons have a 36px minimum height, including the phone send control. Header, metadata, draft labels, and status groups can wrap rather than collide. Evidence timestamps have their own wrapping line. Phone padding is a consistent 18px, its conversation is 350px high on large desktops, and outbound/trace scroll areas are 280px high. Independent scrolling remains in place; the document may grow vertically.
- **Tests:** `npm.cmd test` completed with **42 passed, 0 failed, 0 skipped**. All 38 previously passing tests remain passing. Four new React DOM tests cover polling cadence, both forms of unmount cleanup, unsaved edits, and scroll-container reuse. No application JavaScript, mock logic, state management, or API contracts were changed.
- **Build:** `npm.cmd run build` succeeded, with 40 modules transformed and no unresolved imports or compilation errors. The sandbox initially blocked Vite's ancestor-directory access; the same command succeeded outside that restriction.
- **Browser:** automation inventory exposed no apps or browsers. No 1920×1080 visual inspection was performed in this session. jsdom verifies React DOM behavior, not physical layout, text clipping, or scrollbar geometry.

## Requirement checklist

Status terms: **Implemented and tested**, **Implemented but not fully tested**, **Missing or broken**, **Waiting for backend/AI integration**. Tests below use local state, stubbed Fetch responses, and controlled timers. None exercise a real backend or AI service.

| Requirement | Status | Evidence / limits |
| --- | --- | --- |
| Live activation immediately starts GET `/state` | Implemented and tested | New cadence test checks zero reads in Mock Mode and the first read on activation. |
| Poll approximately every two seconds | Implemented and tested | Checks 1999ms, 2000ms, and the next interval. The next timer starts two seconds after the previous response completes, deliberately avoiding overlap during slow responses. |
| Stop polling when returning to Mock Mode | Implemented and tested | Timer advancement produces no new reads; the pending read signal is aborted and the mock snapshot is restored. |
| Cleanup on unmount | Implemented and tested | Separate tests cover aborting a pending read and clearing an already-scheduled timer. Late completion cannot schedule more reads. |
| Prevent overlapping polling requests | Implemented and tested | Existing delayed-read test advances six seconds without allowing a second request. The `inFlight` guard reuses the pending promise; action locking pauses polling during mutations. |
| Handle network errors without crashing | Implemented and tested | Service and DOM tests cover connection failure, visible feedback, and returning to a usable Mock Mode. |
| Preserve unsaved clarification edits during polling | Implemented and tested | A refreshed backend snapshot updates other displayed data while the same textarea retains the officer's unsaved wording. Cancel reveals the refreshed saved draft. |
| Avoid resetting panel scroll positions during polling | Implemented but not fully tested | New DOM test confirms all five scroll containers retain identity and assigned `scrollTop` values. Actual browser anchoring and scroll geometry require manual verification. |
| All seven dashboard sections and a wider center rumor panel | Implemented but not fully tested | Section rendering is tested. Existing three-column CSS and wider center proportions are retained; final typography/layout needs visual confirmation. |
| Independent feed, rumor, phone, outbound, and trace scrolling | Implemented but not fully tested | Bounded heights, `overflow-y: auto`, and contained overscroll confirmed in CSS. Browser wheel/trackpad behavior remains manual. |
| Readable typography without horizontal clipping or overlap | Implemented but not fully tested | CSS uses moderate sizes, wrapping, minimum-width safeguards, and existing responsive grids. Visual proof at 1920×1080 is still required. |
| Mock and Live modes, loading and error feedback | Implemented and tested | Existing mode-preservation, pending-action, network-failure, validator-rejection, and reset-error tests pass. |
| Evidence expiry indicators and validator flags | Implemented and tested | Seed rendering and service regression tests cover expired/missing evidence, blocking flags, and outdated outbound versions. |
| Rumor lifecycle states | Implemented and tested | Tests cover new claims, drafting, monitoring on approval, resolution on clock advance, and reopening when evidence expires or reports conflict. |
| Clarification editing and human approval | Implemented and tested | Load, save, cancel, empty-text rejection, correct ID relationships, duplicate-send prevention, validator restrictions, and pending controls are covered. |
| Resident SMS simulation | Implemented and tested | Sender, role, zone, feed update, conversation replies, pending/error states, blank text, and zero Mock Mode Fetch calls are covered. |
| Six chaos controls and Reset | Implemented and tested | All six controls, selected bulletin ID, repeated transitions, unavailable actions, and exact seed restoration are covered. |
| Simulated clock and SIMULATION indicator | Implemented and tested | Dashboard rendering includes the indicator; clock advancement and reset are exercised. No real-world clock replaces simulated timestamps. |
| Real API connectivity, backend validation, AI analysis, and real delivery outcomes | Waiting for backend/AI integration | Deliberately not contacted or implemented as real services in this frontend task. |

No missing or broken frontend requirement was found in this audit. No feature or business-logic change was necessary.

## API contract checklist

All requests remain centralized in `src/services/api.js`. IDs in URL paths are encoded. The base URL remains `VITE_API_BASE_URL`, with the documented local fallback. The API contract is unchanged.

| Endpoint | Method / payload confirmed | Status |
| --- | --- | --- |
| `/state` | GET, no JSON request body | Implemented and tested |
| `/sms/inbound` | POST `{ from, role, zone, text }` | Implemented and tested |
| `/rumors/{id}/verify` | POST `{}` | Implemented and tested |
| `/outbound/{id}/edit` | POST `{ text }` | Implemented and tested |
| `/outbound/{id}/approve` | POST `{ approver }` | Implemented and tested |
| `/chaos/{action}` | POST `{}` for ordinary actions; `{ minutes: 45 }` for clock advance; `{ id }` from current bulletins for expiry | Implemented and tested |
| `/reset` | POST `{}`; explicit `seed_imported: false` produces incomplete-reset feedback | Implemented and tested |

Actual payload compatibility, CORS, source authority, approval rejections, delivery failures, and real latency remain **Waiting for backend/AI integration**. Mocked request tests establish frontend behavior only.

## Future extension assessment — no implementation added

| Future information | Existing extension point | Suitable placement |
| --- | --- | --- |
| AI analysis details | `EmergingRumors` / `RumorCard`, `PipelineTrace` | Expandable analysis details in a rumor card; latency or processing events in trace. |
| Additional evidence | Existing evidence array and disclosure in `RumorCard` | Continue the source list inside the disclosure; use internal tabs or a modal if records become extensive. |
| Backend health | `StatusBanner` and existing connection indicator in `App` | Compact status with expandable diagnostics rather than a permanent extra column. |
| Rumor filtering | `EmergingRumors` heading and scrollable rumor list | A compact filter row or internal tabs while keeping stable rumor IDs. |
| Approval history | Clarification details and `OutboundLog` | Expandable history or a record modal; avoid expanding every card permanently. |
| Delivery failures | `OutboundLog`, phone conversation, `PipelineTrace` | Per-record failure state/detail; phone representation will need to include failed outbound records if that behavior is desired. |

The current layout can accommodate these additions through disclosures, modals, and internal tabs. The center panel already has the greatest width; each long list scrolls independently. More permanently visible columns are unnecessary.

Coupling to keep in mind later:

- `App` currently combines polling, mode snapshots, global action locking, and feedback. That is manageable at this scale; per-record concurrency or more complex retries may justify a small controller hook later, without changing panel structure.
- `RumorCard` combines evidence display, draft lookup, editing, and approval controls. Additional AI/history displays should become small child components if this grows.
- `normalizeState` retains a fixed set of top-level arrays. A new top-level health/history payload needs an explicit normalization update; extra per-record fields are preserved.
- Source display resolves evidence against bulletin/shelter records, and the mock intentionally uses fixture-specific associations. Additional source kinds need an agreed backend schema; the existing mock is not semantic AI verification.
- Phone history filters by exact sender number and currently displays sent/delivered replies. Failure states and broadcast recipient expansion need an explicit integration decision.
- Existing fixed panel heights are useful presentation defaults, not a fixed viewport height. Future detail should expand inside a panel or modal rather than requiring more columns.

## Manual review at 1920×1080

Check the enlarged labels, evidence timestamps, validator badges, rumor action row, phone bubbles/composer, and wrapped chaos buttons. Confirm there is no horizontal scrollbar, clipping, overlap, or excessive whitespace. Scroll each of the five long-content areas independently and verify normal page scrolling. The automated suite cannot replace these visual checks.
