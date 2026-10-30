import manifest from '../../public/audio/manifest.json';
import {FPS} from '../theme';

/** One piece of the app recording, in recording seconds, played at `rate`. */
export type Seg = {from: number; to: number; rate: number};

type Event = {t: number; kind: string; text?: string; origin?: string; state?: string; outcome?: string};
export type VoiceLine = {t: number; who: 'ishara' | 'rohan'; text: string; file: string; duration: number};

const events = (manifest as {events: Event[]}).events;
export const voiceLines = (manifest as unknown as {lines: VoiceLine[]}).lines;
export const ring = (manifest as {ring: {file: string; t: number; duration: number}}).ring;
const appStart = (manifest as {appStart?: number}).appStart ?? 14;

const first = (test: (e: Event) => boolean) => {
  const found = events.find(test);
  if (!found) throw new Error('film timeline is missing an event');
  return found;
};
const after = (e: Event, test: (x: Event) => boolean) => {
  const found = events.find((x) => x.t > e.t && test(x));
  if (!found) throw new Error('film timeline is missing an event');
  return found;
};

export const T = {
  ringing: first((e) => e.kind === 'status' && e.state === 'ringing').t,
  inCall: first((e) => e.kind === 'status' && e.state === 'inCall').t,
  ended: first((e) => e.kind === 'status' && e.state === 'ended').t,
  greeting: first((e) => e.kind === 'caption' && !!e.text?.startsWith('Good morning')).t,
  disclosure: first((e) => e.kind === 'caption' && !!e.text?.startsWith('Hello, I')).t,
  opening: first((e) => e.kind === 'caption' && !!e.text?.startsWith("I'm calling on behalf")).t,
  registered: first((e) => e.kind === 'caption' && !!e.text?.includes('registered')).t,
  p1: first((e) => e.kind === 'proposal' && !!e.text?.includes('patient ID')).t,
  wednesday: first((e) => e.kind === 'caption' && !!e.text?.includes('Wednesday at 4 pm')).t,
  p2: first((e) => e.kind === 'proposal' && !!e.text?.includes("doesn't work")).t,
  thursday: first((e) => e.kind === 'caption' && !!e.text?.includes('Thursday at 10:30 am')).t,
  p3: first((e) => e.kind === 'proposal' && e.origin === 'agent' && !!e.text?.includes('Thursday at 10:30 works')).t,
  userLine: first((e) => e.kind === 'proposal' && e.origin === 'user').t,
  allergies: first((e) => e.kind === 'caption' && !!e.text?.includes('allergies')).t,
  p4: first((e) => e.kind === 'proposal' && !!e.text?.includes('penicillin')).t,
  booked: first((e) => e.kind === 'caption' && !!e.text?.startsWith('Noted.')).t,
  p5: first((e) => e.kind === 'proposal' && !!e.text?.startsWith("That's all")).t,
  draft: first((e) => e.kind === 'draft').t,
  signedSpoken: first((e) => e.kind === 'status' && e.state === 'speaking').t,
};
const resolvedAfter = (t: number) => after({t, kind: ''}, (x) => x.kind === 'resolved').t;
const callTap = T.ringing - 0.8;

/**
 * The cut: Home at 1.6× (typing and attaching), then the call in real time, minus the
 * middle of two of Ishara's timed bars (the first one runs in full, to teach it).
 */
export const segments: Seg[] = [
  {from: appStart + 4.2, to: callTap + 0.3, rate: 1.6},
  {from: callTap + 0.3, to: T.p2 + 1.8, rate: 1},
  {from: resolvedAfter(T.p2) - 1.0, to: T.p4 + 1.8, rate: 1},
  {from: resolvedAfter(T.p4) - 1.0, to: T.ended + 9.5, rate: 1},
];

export const segFrames = (seg: Seg) => Math.round(((seg.to - seg.from) / seg.rate) * FPS);
export const demoFrames = segments.reduce((sum, seg) => sum + segFrames(seg), 0);

/** Frame within the demo for a recording time; times inside a cut snap to the next piece. */
export const at = (t: number): number => {
  let offset = 0;
  for (const seg of segments) {
    if (t < seg.from) return offset;
    if (t <= seg.to) return offset + Math.round(((t - seg.from) / seg.rate) * FPS);
    offset += segFrames(seg);
  }
  return offset;
};

/** The recording time shown at a demo frame (the inverse of `at`). */
export const recAt = (frame: number): number => {
  let offset = 0;
  for (const seg of segments) {
    const frames = segFrames(seg);
    if (frame < offset + frames) return seg.from + ((frame - offset) / FPS) * seg.rate;
    offset += frames;
  }
  const last = segments[segments.length - 1];
  return last.to;
};

/** Whether a sound from `t` for `duration` seconds plays whole inside one real-time piece. */
export const audible = (t: number, duration: number) =>
  segments.some((seg) => seg.rate === 1 && t >= seg.from - 0.05 && t + duration <= seg.to + 0.3);
