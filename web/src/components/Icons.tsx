import type {CSSProperties} from 'react';

const paths = {
  settings: 'M4 6h16M4 12h16M4 18h16M8 3v6M16 9v6M10 15v6',
  paperclip: 'M8 12l7-7a4 4 0 0 1 6 6L11 21a6 6 0 0 1-8-8L13 3M6 15l10-10',
  person: 'M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0M4 21v-2a8 8 0 0 1 16 0v2',
  phone: 'M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6 19.8 19.8 0 0 1-3.1-8.7A2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.4 2.1L8.1 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2z',
  arrow: 'M5 12h14M12 5l7 7-7 7', close: 'M6 6l12 12M6 18L18 6',
  check: 'M5 12l4 4L19 6', clock: 'M12 8v4l3 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
  send: 'M22 2 9 15M22 2l-7 20-6-7-7-6 20-7z',
  camera: 'M23 7l-7 5 7 5V7zM3 5h11a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z',
  lock: 'M5 11h14v10H5V11zM8 11V7a4 4 0 0 1 8 0v4',
  edit: 'M16 3l5 5M4 20l4-1L21 6a2 2 0 0 0-3-3L5 16l-1 4z',
  plus: 'M12 5v14M5 12h14', back: 'M19 12H5m7-7-7 7 7 7',
  logout: 'M9 5H4v14h5M14 8l4 4-4 4M8 12h13',
  file: 'M14 2H5v20h14V7l-5-5zM14 2v6h5M8 12h8M8 16h8',
  hand: 'M8 13V5a2 2 0 0 1 4 0v7-9a2 2 0 0 1 4 0v9-6a2 2 0 0 1 4 0v9c0 5-3 7-7 7-3 0-5-1-7-4l-3-4a2 2 0 0 1 3-3l2 2',
  shield: 'M12 2 3 6v6c0 5 9 10 9 10s9-5 9-10V6l-9-4zM8 12l3 3 5-6',
} as const;
export function Icon({name, size = 20}: {name: keyof typeof paths; size?: number}) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>;
}
export function Mark({small = false}: {small?: boolean}) {
  return <span className={`mark ${small ? 'mark-small' : ''}`} aria-hidden="true">{[.46, .7, .62, .38].map((h, i) => <i key={i} style={{'--bar-height': `${h * 100}%`} as CSSProperties} />)}</span>;
}
