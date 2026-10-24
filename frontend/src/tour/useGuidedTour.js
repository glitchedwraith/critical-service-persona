import { useCallback, useEffect, useRef } from 'react';
import { driver } from 'driver.js';
import 'driver.js/dist/driver.css';
import './tour.css';

export const TOUR_SEEN_KEY = 'truesignal.tour.v1.seen';
const WAIT_MS = 5 * 60 * 1000; // situations can take a while when Bedrock is slow

const NEXT_SITUATION = '[data-tour="situation-next"]:not(:disabled)';
const DANA_PRIMARY = '[data-tour="dana-primary"]:not(:disabled)';

const doneCount = v => (v.state.system.situations_done || []).length;
const titleOf = el => el?.querySelector('.sit-title')?.textContent || 'the highlighted situation';

/** Dana's "what changed" key: her line plus the buttons she offers. */
const danaKey = v => `${v.focus.line}|${v.focus.actions.map(a => a.label).join(',')}`;

/** A step the user completes by clicking the highlighted element itself.
 *  We listen for the click ourselves instead of driver.js `advanceOnClick`,
 *  which ignores clicks made during the ~400ms step transition and would
 *  leave a fast clicker stuck on a step whose action already ran. */
const clickStep = (ctx, id, element, title, describe, extra = {}) => ({
  element, waitForElement: WAIT_MS, data: { id },
  popover: {
    // The label is read from the live button, so the copy never hardcodes seed data.
    // driver.js hides an empty description, so give it a placeholder to overwrite.
    title, description: 'Click the highlighted item.', side: 'right', align: 'start', showButtons: ['close'],
    onPopoverRender: (p, { state }) => { p.description.textContent = describe(state.activeElement); },
    ...extra.popover,
  },
  onHighlightStarted: (el, _step, { driver: d, index }) => {
    el?.addEventListener('click', () => {
      ctx.baseline = doneCount(ctx.view);
      ctx.danaKey = danaKey(ctx.view);
      setTimeout(() => { if (d.isActive() && d.getActiveIndex() === index) d.moveNext(); }, 0);
    }, { once: true });
  },
});

/** A step with no buttons that advances by itself once `waitFor(view, ctx)` is truthy.
 *  Returning a step id (string) jumps to that step instead of the next one. */
const waitStep = (id, element, title, description, waitFor, side = 'bottom') => ({
  element, data: { id, waitFor },
  popover: { title, description, side, align: 'center', showButtons: ['close'] },
});

function buildSteps(ctx) {
  const situationFinished = v => doneCount(v) > ctx.baseline && !v.running && !v.busy;
  const danaMoved = v => !v.busy && danaKey(v) !== ctx.danaKey;
  return [
    { data: { id: 'welcome' }, popover: {
      title: 'Welcome to TrueSignal',
      description: 'This is a simulated emergency in San Jose. Residents text rumors; Dana, the public-information officer, checks them against official sources and sends corrections. This tour walks you through your first few situations. You do the clicking.',
      showButtons: ['next', 'close'], nextBtnText: 'Start' } },
    { element: '[data-tour="situations"]', data: { id: 'rail' }, popover: {
      title: 'Situations', side: 'right', align: 'start', showButtons: ['next', 'previous', 'close'],
      description: 'Each situation plays out one event in the emergency. Run them in order, top to bottom. You can also text as a resident from the box at the bottom.' } },

    clickStep(ctx, 'run-1', NEXT_SITUATION, 'Run your first situation',
      el => `Click “${titleOf(el)}” to start it.`),
    waitStep('watch-1', '[data-tour="narration"]', 'Watch it play out',
      'The story streams here while the simulation runs. The map and status bar update live.', situationFinished),
    { element: '[data-tour="vitals"]', data: { id: 'vitals' }, popover: {
      title: 'City status', side: 'bottom', align: 'center', showButtons: ['next', 'close'],
      description: 'Sim clock, whether the city website is up, how old Dana’s cached bulletins are, and SMS gateway health. When the site goes down, Dana answers from the cache and says how old it is.' } },

    clickStep(ctx, 'run-2', NEXT_SITUATION, 'Next situation',
      el => `Click “${titleOf(el)}”.`),
    waitStep('watch-2', '[data-tour="trace"]', 'The pipeline at work',
      'Each incoming text goes through Understand → Verify → Safety check → Send. These chips show what ran and how long it took.',
      situationFinished, 'top'),

    clickStep(ctx, 'run-3', NEXT_SITUATION, 'Now a rumor',
      el => `Click “${titleOf(el)}”. Watch the zones on the map turn amber as the rumor spreads.`),
    waitStep('watch-3', '[data-tour="dana"]', 'Dana needs you',
      'Residents are repeating a rumor. Dana will ask for your call once the texts are in.',
      v => situationFinished(v) && (v.focus.actions.length > 0 || 'finish'), 'left'),

    clickStep(ctx, 'dana-1', DANA_PRIMARY, 'Your decision',
      el => `Click “${el?.textContent || 'the highlighted button'}”. Dana only acts after you approve.`,
      { popover: { side: 'left' } }),
    waitStep('dana-wait', '[data-tour="dana"]', 'Dana is working',
      'She checks official sources and drafts a reply. The safety check runs before anything goes out.',
      v => danaMoved(v) && (v.focus.actions.length > 0 || 'finish'), 'left'),
    clickStep(ctx, 'dana-2', DANA_PRIMARY, 'Send it',
      el => `Read Dana’s draft, then click “${el?.textContent || 'the highlighted button'}”. The text ripples across the target zones on the map.`,
      { popover: { side: 'left' } }),

    { element: '[data-tour="top-actions"]', data: { id: 'finish' }, popover: {
      title: 'You’re on your own now', side: 'bottom', align: 'end', showButtons: ['next'], doneBtnText: 'Got it',
      description: 'Keep going through the remaining situations. “Reset demo” starts the simulation over, and “Take the tour” resets it and replays this guide.' } },
  ];
}

/**
 * First-visit guided tour. `view` = { state, focus, busy, running, connected }.
 * Auto-starts once per browser (localStorage), or with ?tour=1.
 */
export default function useGuidedTour(view) {
  const ctx = useRef({ view, baseline: 0, drv: null, lastDone: 0 });
  ctx.current.view = view;

  const check = useCallback(() => {
    const c = ctx.current;
    const d = c.drv;
    if (!d?.isActive()) return;
    const step = d.getActiveStep();
    const result = step?.data?.waitFor?.(c.view, c);
    if (!result) return;
    if (typeof result === 'string') {
      const i = d.getConfig().steps.findIndex(s => s.data?.id === result);
      if (i >= 0) { d.moveTo(i); return; }
    }
    d.moveNext();
  }, []);

  const start = useCallback(() => {
    const c = ctx.current;
    c.drv?.destroy();
    localStorage.setItem(TOUR_SEEN_KEY, '1');
    c.baseline = doneCount(c.view);
    c.drv = driver({
      steps: buildSteps(c),
      showProgress: false,
      overlayClickBehavior: 'none',
      allowKeyboardControl: false, // arrow keys would skip the click steps
      popoverClass: 'ts-tour',
      onHighlighted: () => setTimeout(check, 0),
      onDestroyed: () => { c.drv = null; },
    });
    c.drv.drive();
  }, [check]);

  /** "Take the tour": reset first if the simulation has progressed, then start
   *  once the reseed is visible in polled state (act() doesn't await the poll). */
  const replay = useCallback(async reset => {
    const c = ctx.current;
    c.drv?.destroy();
    if (doneCount(c.view) === 0) { start(); return; }
    c.startAfterReset = true;
    if (!(await reset())) c.startAfterReset = false;
  }, [start]);

  // Re-evaluate wait steps whenever live state changes.
  useEffect(() => { check(); }, [view.state, view.busy, view.running, check]);

  // A reset (situations_done shrinks) mid-tour invalidates the baselines: start over.
  const done = doneCount(view);
  useEffect(() => {
    const c = ctx.current;
    if (c.drv?.isActive() && done < c.lastDone) start();
    c.lastDone = done;
  }, [done, start]);

  // Pending replay: the reset has landed.
  useEffect(() => {
    const c = ctx.current;
    if (!c.startAfterReset || done !== 0 || view.busy) return;
    c.startAfterReset = false;
    start();
  }, [done, view.busy, start]);

  // First visit: start once the backend is reachable and situations are loaded.
  const ready = view.connected && view.state.situations.length > 0;
  useEffect(() => {
    if (!ready || ctx.current.autoTried) return;
    ctx.current.autoTried = true;
    const forced = new URLSearchParams(window.location.search).has('tour');
    if (forced || !localStorage.getItem(TOUR_SEEN_KEY)) start();
  }, [ready, start]);

  useEffect(() => () => ctx.current.drv?.destroy(), []);

  return { start, replay };
}
