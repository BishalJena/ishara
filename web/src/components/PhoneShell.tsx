import {useEffect, useRef, type ReactNode} from 'react';
import {Mark} from './Icons';

export function PhoneShell({children, demo, active, onMode}: {children: ReactNode; demo: boolean; active: boolean; onMode: (demo: boolean) => void}) {
  return <div className="prototype-stage">
    <header className="prototype-brand"><Mark /><span>Ishara<small>Interactive web prototype</small></span></header>
    <div className="phone-device" aria-label="Ishara phone prototype"><div className="phone-display">
      <div className="phone-status" aria-hidden="true"><span>9:41</span><i className="dynamic-island" /><div><svg width="17" height="13" viewBox="0 0 17 13"><path d="M1 12V9h2v3m3 0V6h2v6m3 0V3h2v9m3 0V0" fill="none" stroke="currentColor" strokeWidth="2" /></svg><svg width="16" height="13" viewBox="0 0 16 13" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M1 4a11 11 0 0 1 14 0M3.5 7a7 7 0 0 1 9 0M6 10a3 3 0 0 1 4 0" /><circle cx="8" cy="12" r="1" fill="currentColor" stroke="none" /></svg><span className="battery" /></div></div>
      <div className="phone-content">{children}</div><div className="phone-home-indicator" aria-hidden="true"><i /></div>
    </div></div>
    <footer className="prototype-controls"><div className="mode-switch" role="group" aria-label="Calling mode"><button disabled={active} aria-pressed={demo} onClick={() => onMode(true)}>Scripted demo</button><button disabled={active} aria-pressed={!demo} onClick={() => onMode(false)}>Live call</button></div><p>{demo ? 'Interactive prototype · no phone is dialled' : 'Live calls use your approved recipients and Bolna credits'}</p></footer>
  </div>;
}

export function Sheet({title, onClose, children}: {title: string; onClose: () => void; children: ReactNode}) {
  const panel = useRef<HTMLElement>(null);
  const close = useRef(onClose); close.current = onClose;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    panel.current?.focus();
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); close.current(); }
      if (event.key !== 'Tab') return;
      const fields = Array.from(panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), textarea:not(:disabled), [tabindex="0"]') ?? []);
      if (!fields.length) { event.preventDefault(); return; }
      const first = fields[0], last = fields[fields.length - 1];
      if (event.shiftKey && (document.activeElement === first || document.activeElement === panel.current)) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && (document.activeElement === last || document.activeElement === panel.current)) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', key);
    return () => { document.removeEventListener('keydown', key); previous?.focus(); };
  }, []);
  return <div className="sheet-backdrop" onClick={event => { if (event.target === event.currentTarget) onClose(); }}><section className="sheet-panel" role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} ref={panel}><div className="sheet-grabber" /><header className="sheet-header"><h2>{title}</h2><button onClick={onClose}>Done</button></header><div className="sheet-content">{children}</div></section></div>;
}
