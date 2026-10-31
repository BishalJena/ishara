import React from 'react';
import {AbsoluteFill, Audio, Easing, interpolate, OffthreadVideo, Sequence, staticFile, useCurrentFrame} from 'remotion';
import {Line, useRise} from '../components/motion';
import {Phone, SCREEN} from '../components/Phone';
import {at, audible, demoFrames, recAt, ring, segFrames, segments, T, voiceLines} from '../demo/plan';
import signCard from '../../public/sign-card.json';
import {C, FONT} from '../theme';

/** Where the sign panel's camera card is in the recording (pixels), tracked every 0.1 s. */
const cardAt = (t: number) => {
  let best: {t: number; box: number[]} | undefined;
  for (const entry of signCard as {t: number; box: number[]}[]) {
    if (Math.abs(entry.t - t) <= 0.12 && (!best || Math.abs(entry.t - t) < Math.abs(best.t - t))) best = entry;
  }
  return best?.box;
};

/** Set to true once the founder's THANK YOU clip is in public/sign.mp4. */
const SIGN_CLIP = false;

const SCREEN_H = 900;
const callTap = T.ringing - 0.8;

/** Callouts beside the phone, each from a moment in the recording until the next one. */
const CALLOUTS: {t: number; title: string; sub?: string}[] = [
  {t: segments[0].from + 1.0, title: 'Type the number.', sub: '+91 is already there.'},
  {t: segments[0].from + 8.0, title: 'Say what the call is about,', sub: 'in your own words.'},
  {t: callTap - 10.8, title: 'Attach what they might ask for.', sub: 'A card, a letter, your health history.'},
  {t: callTap - 3.2, title: 'Read on this iPhone.', sub: 'Quoted on the call only when asked, word for word.'},
  {t: T.ringing, title: 'Ishara places the call.', sub: "From Ishara's number. Nothing to install at the clinic."},
  {t: T.greeting, title: 'Every word, captioned live.'},
  {t: T.disclosure, title: 'Ishara says who it is.', sub: 'Every call, before anything else.'},
  {t: T.opening, title: 'Your request,', sub: 'retold on your behalf.'},
  {t: T.p1, title: 'Ishara answers from your PDF.', sub: 'The bar fills. Do nothing, and it carries on.'},
  {t: T.p2, title: 'It keeps to what you asked:', sub: 'mornings.'},
  {t: T.thursday + 1.2, title: 'Suggested replies,', sub: 'drawn from what they just said.'},
  {t: T.userLine, title: 'You step in.', sub: 'Ishara polishes your words and shows you first.'},
  {t: T.p4, title: 'Quoted from your health history.', sub: 'Never guessed.'},
  {t: T.p5 + 1.0, title: 'Or sign it.', sub: 'Recognised on the iPhone.'},
  {t: T.signedSpoken + 2.6, title: 'They confirm. The call ends.'},
  {t: T.ended + 2.2, title: 'The gist.', sub: 'What was agreed, quoted from the call.'},
];

/** Push-ins: scale the phone towards its lower half while a detail must be read. */
const ZOOMS: {from: number; to: number; scale: number; origin: number}[] = [
  {from: T.p1 - 0.3, to: T.p1 + 6.2, scale: 1.32, origin: 0.92},
  {from: T.thursday + 0.4, to: T.userLine + 2.4, scale: 1.32, origin: 0.92},
  {from: T.p4 - 0.3, to: T.p4 + 2.4, scale: 1.25, origin: 0.9},
  {from: T.p5 + 0.6, to: T.signedSpoken + 1.6, scale: 1.4, origin: 0.95},
  {from: T.ended + 2.4, to: T.ended + 7.5, scale: 1.12, origin: 0.45},
];

const smooth = (frame: number, start: number, end: number, ramp = 15) =>
  interpolate(frame, [start - ramp, start, end, end + ramp], [0, 1, 1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.inOut(Easing.cubic),
  });

export const DEMO_FRAMES = demoFrames;

export const Demo: React.FC = () => {
  const frame = useCurrentFrame();
  const intro = useRise(0, 24);

  let zoom = 1;
  let origin = 0.9;
  for (const z of ZOOMS) {
    const w = smooth(frame, at(z.from), at(z.to));
    if (w > 0) {
      zoom = 1 + (z.scale - 1) * w;
      origin = z.origin;
    }
  }

  const callout = [...CALLOUTS].reverse().find((c) => frame >= at(c.t));
  const calloutIndex = callout ? CALLOUTS.indexOf(callout) : -1;
  const nextAt = calloutIndex >= 0 && calloutIndex + 1 < CALLOUTS.length ? at(CALLOUTS[calloutIndex + 1].t) : demoFrames;

  let offset = 0;
  const pieces = segments.map((seg, i) => {
    const from = offset;
    offset += segFrames(seg);
    return (
      <Sequence key={i} from={from} durationInFrames={segFrames(seg)} layout="none">
        <OffthreadVideo
          src={staticFile('app.mp4')}
          trimBefore={Math.round(seg.from * 30)}
          playbackRate={seg.rate}
          muted
          style={{width: '100%', height: '100%', objectFit: 'cover'}}
        />
      </Sequence>
    );
  });

  // The sign panel's camera card, followed through the recording (iPhone 17, 3×).
  const box = frame >= at(T.p5) && frame <= at(T.signedSpoken + 3) ? cardAt(recAt(frame)) : undefined;
  const card = box ? {x: box[0], y: box[1], w: box[2], h: box[3]} : undefined;
  const k = SCREEN_H / SCREEN.h;

  return (
    <AbsoluteFill style={{background: C.paper}}>
      <AbsoluteFill style={{justifyContent: 'center', alignItems: 'flex-start', paddingLeft: 330}}>
        <div
          style={{
            transform: `translateY(${(1 - intro) * 120}px) scale(${zoom})`,
            transformOrigin: `50% ${origin * 100}%`,
            opacity: intro,
          }}
        >
          <Phone height={SCREEN_H}>
            {pieces}
            {card && (
              <div
                style={{
                  position: 'absolute',
                  left: card.x * k,
                  top: card.y * k,
                  width: card.w * k,
                  height: card.h * k,
                  borderRadius: 20 * 3 * k,
                  overflow: 'hidden',
                  background: '#1a1a1f',
                }}
              >
                {SIGN_CLIP ? (
                  <OffthreadVideo src={staticFile('sign.mp4')} muted style={{width: '100%', height: '100%', objectFit: 'cover'}} />
                ) : (
                  <SignPlaceholder />
                )}
              </div>
            )}
          </Phone>
        </div>
      </AbsoluteFill>

      {callout && (
        <div key={calloutIndex} style={{position: 'absolute', left: 1010, top: 0, bottom: 0, width: 760, display: 'flex', flexDirection: 'column', justifyContent: 'center'}}>
          <Callout title={callout.title} sub={callout.sub} start={at(callout.t)} end={nextAt} />
        </div>
      )}

      {ring && audible(ring.t, ring.duration) && (
        <Sequence from={at(ring.t)} durationInFrames={Math.round(ring.duration * 30)}>
          <Audio src={staticFile(`audio/${ring.file}`)} volume={0.55} />
        </Sequence>
      )}
      {voiceLines
        .filter((l) => audible(l.t, l.duration))
        .map((l) => (
          <Sequence key={l.file} from={at(l.t)} durationInFrames={Math.ceil(l.duration * 30) + 6}>
            <Audio src={staticFile(`audio/${l.file}`)} volume={l.who === 'rohan' ? 0.95 : 0.9} />
          </Sequence>
        ))}
    </AbsoluteFill>
  );
};

const Callout: React.FC<{title: string; sub?: string; start: number; end: number}> = ({title, sub, start, end}) => {
  const frame = useCurrentFrame();
  const fade = interpolate(frame, [end - 8, end], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const rule = useRise(start, 14);
  return (
    <div style={{opacity: fade}}>
      <div style={{width: 64 * rule, height: 3, background: C.purple, borderRadius: 2, marginBottom: 26}} />
      <Line start={start + 3} style={{fontFamily: FONT.display, fontSize: 56, fontWeight: 600, color: C.ink, letterSpacing: '-0.02em', lineHeight: 1.1}}>
        {title}
      </Line>
      {sub && (
        <Line start={start + 8} style={{fontFamily: FONT.display, fontSize: 38, fontWeight: 400, color: C.muted, letterSpacing: '-0.01em', lineHeight: 1.25, marginTop: 14}}>
          {sub}
        </Line>
      )}
    </div>
  );
};

/** Until the founder's clip is in: a quiet stand-in that says what goes here. */
const SignPlaceholder: React.FC = () => (
  <div style={{width: '100%', height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: 'linear-gradient(160deg, #2a2a33, #111115)'}}>
    <div style={{width: 26, height: 26, borderRadius: 13, border: '2px solid #888'}} />
    <div style={{fontFamily: FONT.text, fontSize: 9, color: '#bbb', marginTop: 6, letterSpacing: '0.08em'}}>SIGN CLIP</div>
  </div>
);
