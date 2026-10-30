import React from 'react';
import {AbsoluteFill, Audio, Composition, interpolate, Sequence, staticFile} from 'remotion';
import {Demo, DEMO_FRAMES} from './sections/Demo';
import {BARRIER, Barrier, Brand, BRAND, CLOSE, Close, COLD_OPEN, ColdOpen, HOW, How, Market, MARKET, Scale, SCALE} from './sections/Story';
import {FPS, H, W} from './theme';

/** The film's sections, in order (docs/demo/video/SCRIPT.md). */
const SECTIONS: {id: string; frames: number; component: React.FC}[] = [
  {id: 'cold-open', frames: COLD_OPEN, component: ColdOpen},
  {id: 'barrier', frames: BARRIER, component: Barrier},
  {id: 'scale', frames: SCALE, component: Scale},
  {id: 'brand', frames: BRAND, component: Brand},
  {id: 'demo', frames: DEMO_FRAMES, component: Demo},
  {id: 'how', frames: HOW, component: How},
  {id: 'market', frames: MARKET, component: Market},
  {id: 'close', frames: CLOSE, component: Close},
];

const starts: Record<string, number> = {};
let total = 0;
for (const section of SECTIONS) {
  starts[section.id] = total;
  total += section.frames;
}

/** The score: quiet under the story, silent for "can't hear", a swell for Ishara, low under the demo. */
const scoreVolume = (f: number) => {
  const b = starts.barrier;
  const demo = starts.demo;
  return interpolate(
    f,
    [0, 30, b, b + 15, b + 140, b + 150, starts.scale, starts.brand, starts.brand + 40, demo, demo + 60, starts.how, starts.how + 30, total - 60, total],
    [0, 0.28, 0.28, 0, 0, 0.12, 0.26, 0.3, 0.5, 0.42, 0.08, 0.08, 0.28, 0.4, 0],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'},
  );
};

export const Film: React.FC = () => (
  <AbsoluteFill style={{background: '#000'}}>
    {SECTIONS.map(({id, frames, component: Section}) => (
      <Sequence key={id} name={id} from={starts[id]} durationInFrames={frames}>
        <Section />
      </Sequence>
    ))}
    <Audio src={staticFile('audio/score.wav')} volume={scoreVolume} />
  </AbsoluteFill>
);

export const RemotionRoot: React.FC = () => (
  <Composition id="IsharaFilm" component={Film} durationInFrames={total} fps={FPS} width={W} height={H} />
);
