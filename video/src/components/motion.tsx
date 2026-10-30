import React from 'react';
import {Easing, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {C, FONT} from '../theme';

/** A settled spring (no overshoot) from 0 to 1, starting at `start`. */
export const useRise = (start: number, frames = 18) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  return spring({frame: frame - start, fps, config: {damping: 200, mass: 0.8}, durationInFrames: frames});
};

/** Fades a whole section in at its start and out at its end. */
export const useSectionFade = (duration: number, fadeIn = 12, fadeOut = 12) => {
  const frame = useCurrentFrame();
  return interpolate(frame, [0, fadeIn, duration - fadeOut, duration], [0, 1, 1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
};

/** Lines that rise 24 px and un-blur, staggered (BRIEF: type reveals by line). */
export const Lines: React.FC<{
  lines: string[];
  start: number;
  size?: number;
  weight?: number;
  color?: string;
  align?: 'left' | 'center';
  stagger?: number;
  lineHeight?: number;
  out?: number;
  font?: string;
  tracking?: number;
}> = ({lines, start, size = 96, weight = 600, color = C.ink, align = 'center', stagger = 4, lineHeight = 1.08, out, font = FONT.display, tracking = -0.02}) => {
  const frame = useCurrentFrame();
  const fadeOut = out === undefined ? 1 : interpolate(frame, [out, out + 9], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return (
    <div style={{textAlign: align, opacity: fadeOut}}>
      {lines.map((line, i) => (
        <Line key={i} start={start + i * stagger} style={{fontSize: size, fontWeight: weight, color, lineHeight, fontFamily: font, letterSpacing: `${tracking}em`}}>
          {line}
        </Line>
      ))}
    </div>
  );
};

export const Line: React.FC<{start: number; style?: React.CSSProperties; children: React.ReactNode}> = ({start, style, children}) => {
  const p = useRise(start);
  return (
    <div style={{...style, opacity: p, transform: `translateY(${(1 - p) * 24}px)`, filter: `blur(${(1 - p) * 8}px)`}}>
      {children}
    </div>
  );
};

/** A number that counts up over 1.2 s with ease-out and lands exactly on `to`. */
export const CountUp: React.FC<{to: number; start: number; format: (n: number) => string; style?: React.CSSProperties}> = ({to, start, format, style}) => {
  const frame = useCurrentFrame();
  const value = interpolate(frame, [start, start + 36], [0, to], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.out(Easing.cubic),
  });
  return <span style={style}>{format(frame >= start + 36 ? to : value)}</span>;
};

/** A source line under a number, in small grey type. */
export const Source: React.FC<{start: number; children: React.ReactNode; align?: 'left' | 'center'}> = ({start, children, align = 'center'}) => {
  const p = useRise(start);
  return (
    <div style={{opacity: p * 0.9, fontFamily: FONT.text, fontSize: 22, color: C.muted, marginTop: 18, textAlign: align, letterSpacing: '0.01em'}}>
      {children}
    </div>
  );
};
