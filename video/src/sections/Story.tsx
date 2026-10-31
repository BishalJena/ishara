import React from 'react';
import {AbsoluteFill, Audio, Easing, interpolate, Sequence, staticFile, useCurrentFrame} from 'remotion';
import {CountUp, Line, Lines, Source, useRise, useSectionFade} from '../components/motion';
import {C, FONT, s} from '../theme';

const center: React.CSSProperties = {justifyContent: 'center', alignItems: 'center'};

/** A two-sided voice waveform; `flatRight` (0..1) silences the far side. */
const Waveform: React.FC<{color: string; flatRight?: number; width?: number; height?: number}> = ({color, flatRight = 0, width = 1100, height = 220}) => {
  const frame = useCurrentFrame();
  const bars = 64;
  return (
    <div style={{display: 'flex', alignItems: 'center', gap: 6, width, height, justifyContent: 'center'}}>
      {Array.from({length: bars}, (_, i) => {
        const side = i < bars / 2 ? 0 : 1;
        const env = Math.sin((i / bars) * Math.PI);
        const wave = 0.35 + 0.65 * Math.abs(Math.sin(frame * 0.18 + i * 0.55) * Math.cos(frame * 0.07 + i * 0.21));
        const amp = side === 1 ? 1 - flatRight : 1;
        const h = Math.max(4, height * env * wave * amp);
        return <div key={i} style={{width: 8, height: h, borderRadius: 4, background: color, opacity: side === 1 ? 0.55 + 0.45 * amp : 1}} />;
      })}
    </div>
  );
};

/** Concentric rings pulsing out of a point, like a phone ringing. */
const RingPulse: React.FC<{start: number; color: string}> = ({start, color}) => {
  const frame = useCurrentFrame() - start;
  return (
    <div style={{position: 'relative', width: 0, height: 0}}>
      {[0, 12, 24].map((d) => {
        const t = ((frame - d) % 45) / 45;
        if (frame < d) return null;
        return (
          <div
            key={d}
            style={{
              position: 'absolute',
              left: -60 - t * 120,
              top: -60 - t * 120,
              width: 120 + t * 240,
              height: 120 + t * 240,
              borderRadius: '50%',
              border: `3px solid ${color}`,
              opacity: (1 - t) * 0.6,
            }}
          />
        );
      })}
    </div>
  );
};

const PhoneGlyph: React.FC<{color: string; size?: number}> = ({color, size = 120}) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill={color}>
    <path d="M6.6 10.8a15.1 15.1 0 0 0 6.6 6.6l2.2-2.2a1 1 0 0 1 1-.25c1.1.37 2.3.57 3.6.57a1 1 0 0 1 1 1V20a1 1 0 0 1-1 1A17 17 0 0 1 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.25.2 2.45.57 3.57a1 1 0 0 1-.25 1L6.6 10.8z" />
  </svg>
);

// ---- 1. Cold open --------------------------------------------------------------------

export const COLD_OPEN = s(12);
export const ColdOpen: React.FC = () => {
  const frame = useCurrentFrame();
  const fade = useSectionFade(COLD_OPEN, 1, 12);
  const question = 'How do you book an appointment at your local clinic?';
  const typed = question.slice(0, Math.floor(interpolate(frame, [8, 95], [0, question.length], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})));
  const up = interpolate(frame, [130, 150], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.inOut(Easing.cubic)});
  const wave = useRise(245);
  return (
    <AbsoluteFill style={{background: C.paper, opacity: fade}}>
      <AbsoluteFill style={center}>
        <div style={{transform: `translateY(${-up * 300}px) scale(${1 - up * 0.45})`, opacity: 1 - up * 0.65, maxWidth: 1400, textAlign: 'center', fontFamily: FONT.display, fontSize: 92, fontWeight: 600, color: C.ink, letterSpacing: '-0.02em', lineHeight: 1.1}}>
          {typed}
          <span style={{opacity: frame % 30 < 15 && frame < 130 ? 1 : 0, color: C.purple}}>|</span>
        </div>
      </AbsoluteFill>
      {frame >= 145 && frame < 245 && (
        <AbsoluteFill style={center}>
          <div style={{display: 'flex', alignItems: 'center', gap: 70}}>
            <div style={{position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center', width: 160, height: 160}}>
              <div style={{position: 'absolute', left: 80, top: 80}}><RingPulse start={150} color={C.green} /></div>
              <PhoneGlyph color={C.green} size={120} />
            </div>
            <Lines lines={['You call.']} start={152} size={110} align="left" />
          </div>
        </AbsoluteFill>
      )}
      {frame >= 245 && (
        <AbsoluteFill style={{...center, flexDirection: 'column', gap: 50}}>
          <div style={{opacity: wave}}><Waveform color={C.ink} /></div>
          <Lines lines={['You talk. Two minutes. Done.']} start={255} size={84} />
        </AbsoluteFill>
      )}
      <Sequence from={158} durationInFrames={s(2.6)}>
        <Audio src={staticFile('audio/ring.wav')} volume={0.32} />
      </Sequence>
    </AbsoluteFill>
  );
};

// ---- 2. The barrier --------------------------------------------------------------------

export const BARRIER = s(16);
const Node: React.FC<{label: string; start: number; dim?: number; glow?: boolean}> = ({label, start, dim = 1, glow}) => {
  const p = useRise(start);
  return (
    <div style={{display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 22, opacity: p * dim, transform: `scale(${0.85 + 0.15 * p})`}}>
      <div style={{width: 120, height: 120, borderRadius: 60, border: `3px solid ${glow ? C.fact : '#fff'}`, boxShadow: glow ? `0 0 60px ${C.fact}66` : 'none', background: '#111'}} />
      <div style={{fontFamily: FONT.display, fontSize: 34, color: '#fff', fontWeight: 500}}>{label}</div>
    </div>
  );
};

export const Barrier: React.FC = () => {
  const frame = useCurrentFrame();
  const fade = useSectionFade(BARRIER, 10, 14);
  const flat = interpolate(frame, [20, 60], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
  const lonely = interpolate(frame, [400, 430], [1, 0.12], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const arrow = (start: number) => interpolate(frame, [start, start + 18], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return (
    <AbsoluteFill style={{background: C.black, opacity: fade}}>
      {frame < 150 && (
        <AbsoluteFill style={{...center, flexDirection: 'column', gap: 70}}>
          <Waveform color="#fff" flatRight={flat} />
          <Lines lines={["Now imagine you can't hear the other side."]} start={50} size={72} color="#fff" out={135} />
        </AbsoluteFill>
      )}
      {frame >= 150 && (
        <AbsoluteFill style={{...center, flexDirection: 'column', gap: 90}}>
          <div style={{display: 'flex', alignItems: 'center', gap: 40}}>
            <Node label="You" start={155} />
            <div style={{width: 200 * arrow(165), height: 3, background: '#666'}} />
            <Node label="A family member" start={172} dim={lonely} glow={frame > 300 && frame < 400} />
            <div style={{width: 200 * arrow(182), height: 3, background: '#666', opacity: lonely}} />
            <Node label="The clinic" start={190} dim={lonely} />
          </div>
          <div style={{height: 200, display: 'flex', alignItems: 'center'}}>
            {frame < 300 && <Lines lines={['Most Deaf people ask someone else', 'to make the call.']} start={205} size={64} color="#fff" out={290} />}
            {frame >= 300 && frame < 400 && <Lines lines={['On their time.', 'With your private details.']} start={302} size={64} color="#fff" out={390} />}
            {frame >= 400 && <Lines lines={['Every call becomes a favour.']} start={405} size={72} color="#fff" />}
          </div>
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
};

// ---- 3. The scale ----------------------------------------------------------------------

export const SCALE = s(22);
const Stat: React.FC<{start: number; end: number; to: number; format: (n: number) => string; line: string; source: string}> = ({start, end, to, format, line, source}) => {
  const frame = useCurrentFrame();
  const p = useRise(start);
  if (frame < start - 2 || frame > end + 10) return null;
  const out = interpolate(frame, [end, end + 10], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return (
    <AbsoluteFill style={{...center, flexDirection: 'column', opacity: out}}>
      <div style={{opacity: p, transform: `translateY(${(1 - p) * 30}px)`}}>
        <CountUp to={to} start={start} format={format} style={{fontFamily: FONT.display, fontSize: 210, fontWeight: 700, color: C.ink, letterSpacing: '-0.04em'}} />
      </div>
      <Line start={start + 10} style={{fontFamily: FONT.display, fontSize: 54, color: C.ink, fontWeight: 500, marginTop: 6}}>{line}</Line>
      <Source start={start + 18}>{source}</Source>
    </AbsoluteFill>
  );
};

export const Scale: React.FC = () => {
  const frame = useCurrentFrame();
  const fade = useSectionFade(SCALE, 12, 14);
  return (
    <AbsoluteFill style={{background: C.paper, opacity: fade}}>
      <Stat start={6} end={120} to={430} format={(n) => `${Math.round(n)} million`} line="people live with disabling hearing loss." source="World Health Organization, Deafness and hearing loss fact sheet, 2026" />
      <Stat start={132} end={246} to={70} format={(n) => `${Math.round(n)} million+`} line="Deaf people use a sign language." source="World Federation of the Deaf, via the United Nations" />
      <Stat start={258} end={372} to={50} format={(n) => `${Math.round(n)} lakh`} line="Deaf people in India." source="Census of India 2011: 5,071,007, via ISLRTC and PIB" />
      <Stat start={384} end={498} to={300} format={(n) => `< ${Math.round(n)}`} line="certified Indian Sign Language interpreters." source="Indian Sign Language Research and Training Centre" />
      {frame >= 505 && (
        <AbsoluteFill style={{...center, flexDirection: 'column'}}>
          <Lines lines={['About one certified interpreter', 'for every 17,000 Deaf people in India.']} start={510} size={78} />
          <Source start={530}>The ratio of the two figures above</Source>
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
};

// ---- 4. Ishara -----------------------------------------------------------------------------

/** The mark: four rounded bars, a voice's waveform that reads as a raised hand's fingers. */
export const Mark: React.FC<{size: number; start: number}> = ({size, start}) => {
  const frame = useCurrentFrame();
  const heights = [0.46, 0.7, 0.62, 0.38];
  return (
    <div style={{width: size, height: size, borderRadius: size * 0.27, background: `linear-gradient(150deg, #A56BFF, ${C.purple} 55%, #6A1FE0)`, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: size * 0.07, boxShadow: `0 ${size * 0.12}px ${size * 0.35}px ${C.purple}55`}}>
      {heights.map((h, i) => {
        const grow = interpolate(frame, [start + i * 4, start + i * 4 + 16], [0.15, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
        return <div key={i} style={{width: size * 0.1, height: size * h * grow, borderRadius: size * 0.05, background: '#fff'}} />;
      })}
    </div>
  );
};

export const BRAND = s(7);
export const Brand: React.FC = () => {
  const fade = useSectionFade(BRAND, 12, 14);
  const p = useRise(0, 22);
  return (
    <AbsoluteFill style={{background: '#fff', opacity: fade, ...center, flexDirection: 'column', gap: 40}}>
      <div style={{transform: `scale(${0.8 + 0.2 * p})`, opacity: p}}><Mark size={180} start={4} /></div>
      <Lines lines={['Ishara']} start={18} size={140} weight={700} tracking={-0.03} />
      <Lines lines={['Your conversation. Your control.']} start={40} size={54} weight={400} color={C.muted} />
    </AbsoluteFill>
  );
};

// ---- 6. How it works ---------------------------------------------------------------------

export const HOW = s(14);
const Block: React.FC<{start: number; title: string; items: string[]; accent: string; active: number}> = ({start, title, items, accent, active}) => {
  const p = useRise(start);
  return (
    <div style={{width: 360, padding: '34px 30px', borderRadius: 32, background: '#fff', border: `2px solid ${active > 0 ? accent : C.line}`, boxShadow: active > 0 ? `0 20px 60px ${accent}33` : '0 8px 30px rgba(0,0,0,0.05)', opacity: p, transform: `translateY(${(1 - p) * 30}px)`}}>
      <div style={{fontFamily: FONT.display, fontSize: 36, fontWeight: 700, color: C.ink, marginBottom: 18}}>{title}</div>
      {items.map((item) => (
        <div key={item} style={{fontFamily: FONT.text, fontSize: 24, color: '#3a3a40', lineHeight: 1.45, marginBottom: 6}}>{item}</div>
      ))}
    </div>
  );
};

export const How: React.FC = () => {
  const frame = useCurrentFrame();
  const fade = useSectionFade(HOW, 12, 14);
  const step = Math.floor(interpolate(frame, [60, 400], [0, 4], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}));
  const captions = [
    'Signs are recognised on the phone.',
    "A language model phrases; a fact-checker rejects anything you didn't say.",
    'Bolna runs the call: Deepgram listens, Sarvam speaks, Plivo connects.',
    'The clinic just answers its phone.',
  ];
  return (
    <AbsoluteFill style={{background: C.paper, opacity: fade, flexDirection: 'column', alignItems: 'center', paddingTop: 110}}>
      <Lines lines={['How it works']} start={0} size={76} />
      <div style={{display: 'flex', gap: 34, marginTop: 70, alignItems: 'stretch'}}>
        <Block start={10} active={step >= 0 ? 1 : 0} accent={C.blue} title="Your iPhone" items={['SwiftUI · captions, steer, Live Activity', 'MediaPipe + ASL model, on device', 'Vision + PDFKit read documents']} />
        <Block start={18} active={step >= 1 ? 1 : 0} accent={C.purple} title="Ishara backend" items={['FastAPI', 'Groq · gpt-oss-120b phrases', 'A fact-checker blocks invented days, times, numbers, names']} />
        <Block start={26} active={step >= 2 ? 1 : 0} accent={C.green} title="Bolna voice agent" items={['Deepgram: speech to text', 'Sarvam: text to voice', 'Plivo: the phone line']} />
        <Block start={34} active={step >= 3 ? 1 : 0} accent={C.ink} title="The clinic" items={['Its own phone', 'Nothing to install']} />
      </div>
      <div style={{height: 110, marginTop: 56, display: 'flex', alignItems: 'center'}}>
        <Lines key={step} lines={[captions[Math.min(step, 3)]]} start={60 + step * 85} size={40} weight={500} />
      </div>
      <Source start={40}>Calls come from Ishara's calling number (a Bolna number), not yours · Signing: ASL today, Indian Sign Language next</Source>
    </AbsoluteFill>
  );
};

// ---- 7. Why now, and how big ---------------------------------------------------------

export const MARKET = s(16);
const Bar: React.FC<{start: number; label: string; value: string; width: number; color: string}> = ({start, label, value, width, color}) => {
  const frame = useCurrentFrame();
  const grow = interpolate(frame, [start, start + 30], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
  return (
    <div style={{display: 'flex', alignItems: 'center', gap: 30, marginBottom: 26, opacity: Math.min(1, grow * 3)}}>
      <div style={{width: 430, fontFamily: FONT.display, fontSize: 34, color: C.ink, textAlign: 'right'}}>{label}</div>
      <div style={{width: Math.max(6, width * grow), height: 56, borderRadius: 14, background: color}} />
      <div style={{fontFamily: FONT.display, fontSize: 40, fontWeight: 700, color: C.ink}}>{value}</div>
    </div>
  );
};

export const Market: React.FC = () => {
  const frame = useCurrentFrame();
  const fade = useSectionFade(MARKET, 12, 14);
  return (
    <AbsoluteFill style={{background: C.paper, opacity: fade}}>
      {frame < 175 && (
        <AbsoluteFill style={{...center, flexDirection: 'column'}}>
          <CountUp to={1.48} start={8} format={(n) => `$${n.toFixed(2)} billion`} style={{fontFamily: FONT.display, fontSize: 170, fontWeight: 700, color: C.ink, letterSpacing: '-0.04em'}} />
          <Lines lines={['a year: what the US pays for phone relay', 'for Deaf and hard-of-hearing callers.']} start={20} size={52} weight={500} out={165} />
          <Source start={30}>FCC, Telecommunications Relay Services Fund, 2025–26</Source>
        </AbsoluteFill>
      )}
      {frame >= 175 && frame < 345 && (
        <AbsoluteFill style={{...center, flexDirection: 'column'}}>
          <Lines lines={['Per minute of a call']} start={178} size={64} />
          <div style={{marginTop: 60}}>
            <Bar start={190} label="Human video relay" value="$4.07–$8.06" width={760} color={C.muted} />
            <Bar start={210} label="An AI voice agent" value="from $0.06" width={8} color={C.purple} />
          </div>
          <Source start={225}>FCC DA 24-620 (VRS compensation, 2024–25) · Bolna pricing, before telephony</Source>
        </AbsoluteFill>
      )}
      {frame >= 345 && (
        <AbsoluteFill style={{...center, flexDirection: 'column'}}>
          <Lines lines={['70 million people sign.', 'Phone calls still assume you can hear.']} start={350} size={70} />
          <Line start={380} style={{fontFamily: FONT.display, fontSize: 40, color: C.muted, marginTop: 40}}>
            If 5% paid $5 a month: about $210 million a year.
          </Line>
          <Source start={392}>WFD via UN · the 5% and $5 are Ishara planning assumptions (MARKET.md), not a forecast</Source>
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
};

// ---- 8. Close --------------------------------------------------------------------------

export const CLOSE = s(7);
export const Close: React.FC = () => {
  const fade = useSectionFade(CLOSE, 14, 24);
  return (
    <AbsoluteFill style={{background: '#fff', opacity: fade, ...center, flexDirection: 'column', gap: 36}}>
      <Mark size={140} start={2} />
      <Lines lines={['Ishara']} start={10} size={120} weight={700} tracking={-0.03} />
      <Lines lines={['Your conversation. Your control.']} start={26} size={50} weight={400} color={C.muted} />
      <Source start={50}>Built for the Bolna buildathon · github.com/BishalJena/ishara</Source>
    </AbsoluteFill>
  );
};
