/** The app's own palette and type (docs/demo/video/BRIEF.md, Look). */
export const C = {
  ink: '#0B0B0F',
  paper: '#FAFAF7',
  purple: '#8B3DFF',
  blue: '#0A84FF',
  green: '#1EA84B',
  fact: '#F6D77A',
  factBg: '#FFF6D6',
  muted: '#8A8A93',
  line: '#E4E4E0',
  black: '#000000',
};

export const FONT = {
  display: '"SF Pro Display", -apple-system, system-ui, "Helvetica Neue", sans-serif',
  text: '"SF Pro Text", -apple-system, system-ui, "Helvetica Neue", sans-serif',
  mono: '"SF Mono", ui-monospace, Menlo, monospace',
};

export const FPS = 30;
export const W = 1920;
export const H = 1080;

/** Seconds to frames. */
export const s = (seconds: number) => Math.round(seconds * FPS);
