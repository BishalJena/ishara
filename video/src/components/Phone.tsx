import React from 'react';

/** The recording's pixel size (iPhone 17, 3×) and the frame's proportions around it. */
export const SCREEN = {w: 1206, h: 2622};

/**
 * An iPhone 17 frame (natural titanium edge, Dynamic Island) drawn around `children`, which
 * fill the screen at the recording's aspect ratio. `height` is the screen's height in px.
 */
export const Phone: React.FC<{height: number; children: React.ReactNode; shadow?: number}> = ({height, children, shadow = 1}) => {
  const width = (height * SCREEN.w) / SCREEN.h;
  const bezel = height * 0.018;
  const radius = height * 0.077;
  return (
    <div
      style={{
        position: 'relative',
        width: width + bezel * 2,
        height: height + bezel * 2,
        borderRadius: radius + bezel,
        background: 'linear-gradient(145deg, #D9D6CF 0%, #A9A59D 35%, #E7E4DD 55%, #9C988F 100%)',
        padding: bezel * 0.22,
        boxShadow: `0 ${40 * shadow}px ${90 * shadow}px rgba(20,20,30,${0.22 * shadow}), 0 ${8 * shadow}px ${20 * shadow}px rgba(20,20,30,${0.12 * shadow})`,
      }}
    >
      <div style={{width: '100%', height: '100%', borderRadius: radius + bezel * 0.78, background: '#050505', padding: bezel * 0.78}}>
        <div style={{position: 'relative', width, height, borderRadius: radius, overflow: 'hidden', background: '#fff'}}>
          {children}
        </div>
      </div>
    </div>
  );
};
