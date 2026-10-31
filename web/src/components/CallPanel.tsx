import {useEffect, useRef, useState} from 'react';
import type {CallView, Event, Setup} from '../lib/types';
import {CameraPanel} from './CameraPanel';
import {Icon} from './Icons';
import {Sheet} from './PhoneShell';

export function CallPanel({view, setup, demo, unlocked, onSend, onSay, onHold, onDone, notesProblem, onRetryNotes}: {
  view: CallView; setup: Setup; demo: boolean; unlocked: boolean;
  onSend: (event: Event) => void; onSay: (text: string) => boolean; onHold: (value: boolean) => void; onDone: () => void; notesProblem?: string; onRetryNotes?: () => void;
}) {
  const [reply, setReply] = useState('');
  const [lastReply, setLastReply] = useState('');
  const [now, setNow] = useState(Date.now());
  const [ending, setEnding] = useState(false);
  const [signing, setSigning] = useState(false);
  const [connectedAt, setConnectedAt] = useState<number | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const field = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { end.current?.scrollIntoView({behavior: 'smooth', block: 'nearest'}); }, [view.captions.length]);
  useEffect(() => { if (view.state === 'in_call' && !connectedAt) setConnectedAt(Date.now()); }, [view.state, connectedAt]);
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 100); return () => clearInterval(timer); }, []);
  const proposal = view.proposal;
  const remaining = proposal ? Math.max(0, (proposal.deadline - now) / 1000) : 0;
  const canReply = view.online && ['in_call', 'speaking'].includes(view.state);
  const seconds = connectedAt ? Math.max(0, Math.floor((now - connectedAt) / 1000)) : 0;
  const clock = `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
  const held = view.held || Boolean(reply.trim()) || signing;
  const status = view.state === 'ended' ? 'Call ended' : !view.online ? 'Connecting…' : view.state === 'ringing' ? 'Ringing…' : view.state === 'dialing' ? 'Calling…' : held ? 'You’re replying — Ishara is covering' : 'Ishara is handling it — step in any time';
  const facts = [...new Set(view.captions.filter(c => c.speaker === 'receptionist').flatMap(c => c.text.match(/\b\d{1,2}:\d{2}(?:\s*[ap]m)?\b|\b(?:today|tomorrow|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)(?:\s+(?:morning|afternoon|evening))?\b/gi) ?? []))].slice(-4);
  return <section className="call-screen">
    <header className="native-call-header"><span className="initial-avatar purple">{setup.contactName.charAt(0)}</span><div><h1>{setup.contactName}</h1><p>{connectedAt ? `${clock} · ` : ''}{demo ? 'scripted demo' : 'from Ishara’s number'}</p></div>{view.state === 'ended' ? <button className="pill-button" onClick={onDone}>Done</button> : <button className="end-button" aria-label="End call" disabled={!view.online || ending} onClick={() => { setEnding(true); onSend({type: 'end'}); }}><Icon name="phone" size={16} />{ending ? 'Ending…' : 'End'}</button>}</header>
    <div className="native-call-status"><span className={`status-pill ${held ? 'is-held' : ''}`}><span aria-hidden="true">✧</span>{status}</span></div>
    {facts.length > 0 && <div className="facts-strip">{facts.map(fact => <span key={fact}><Icon name="clock" size={13} />{fact}</span>)}</div>}
    {notesProblem && <div className="error-banner" role="alert">{notesProblem}<button className="notes-retry" onClick={onRetryNotes}>Retry notes</button></div>}
    {view.problem && <div className="error-banner" role="alert">{view.problem}{lastReply && <button className="notes-retry" onClick={() => { setReply(lastReply); onHold(true); field.current?.focus(); }}>Edit last reply</button>}</div>}
    <div className="native-transcript" role="log" aria-label="Call captions" aria-live="polite" aria-relevant="additions">
      {view.captions.length === 0 && <div className="connecting-empty"><Icon name="phone" size={32} /><h2>{view.state === 'ringing' ? 'Waiting for an answer…' : 'Making the connection…'}</h2><p>Follow the conversation here.</p></div>}
      {view.captions.map((caption, i) => <div className={`native-caption ${caption.speaker === 'receptionist' ? 'caption-them' : 'caption-us'} ${i === view.captions.length - 1 ? 'latest' : ''}`} key={caption.id}><div className="caption-label"><Icon name={caption.speaker === 'receptionist' ? 'person' : 'hand'} size={13} />{caption.speaker === 'receptionist' ? setup.contactName : caption.speaker === 'you' ? 'You' : 'Ishara for you'}</div><p>{caption.text}</p></div>)}
      {view.followUps.length > 0 && <div className="follow-up-box"><h2>Saved for you to follow up</h2><p>{view.followUps[view.followUps.length - 1]}</p></div>}<div ref={end} />
    </div>
    <div className="native-reply-tray">
      {proposal && <div className="proposal" role="status"><div className="proposal-heading"><span>{proposal.origin === 'user' ? 'Your reply, polished' : 'Ishara is about to say'}</span><span aria-hidden="true">{remaining.toFixed(1)}s</span></div><p>{proposal.text}</p><div className="proposal-progress" style={{transform: `scaleX(${Math.min(1, remaining / proposal.window_s)})`}} /><div className="proposal-actions"><button onClick={() => { setReply(proposal.text); onHold(true); field.current?.focus(); }}>Edit this line</button><button onClick={() => onSend({type: 'approve', turn_id: proposal.turn_id, text: proposal.text})}>Say now</button></div></div>}
      <div className="quick-replies">{['Could you repeat that?', 'One moment, please'].map(text => <button key={text} disabled={!canReply} onClick={() => onSay(text)}>{text}</button>)}</div>
      <form className="native-reply-form" onSubmit={event => { event.preventDefault(); if (!reply.trim() || !canReply) return; if (onSay(reply)) { setLastReply(reply); setReply(''); } }}><button type="button" className="circle-button" aria-label="Open signing" disabled={!canReply} onClick={() => { setSigning(true); onHold(true); }}><Icon name="hand" /></button><label className="sr-only" htmlFor="reply">Your reply</label><textarea ref={field} id="reply" value={reply} rows={1} maxLength={300} disabled={!canReply} placeholder="Step in…" onFocus={() => { if (canReply) onHold(true); }} onChange={event => { setReply(event.target.value); onHold(true); }} onKeyDown={event => { if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) { event.preventDefault(); if (reply.trim() && canReply) { if (onSay(reply)) { setLastReply(reply); setReply(''); } } } }} /><button className="send-circle" type="submit" disabled={!reply.trim() || !canReply} aria-label="Preview and send reply"><Icon name="arrow" size={22} /></button></form>
      <div className="reply-hint">{(reply || view.held) ? <button className="text-button" onClick={() => { setReply(''); onHold(false); }}>Let Ishara continue</button> : <span>Type or sign to step in. Review before it’s spoken.</span>}</div>
    </div>
    {signing && <Sheet title="Sign your reply" onClose={() => { setSigning(false); if (!reply) onHold(false); }}><CameraPanel enabled={unlocked} onComposing={onHold} onWords={text => { setReply(old => `${old.trim()} ${text}`.trim().slice(0, 300)); setSigning(false); onHold(true); field.current?.focus(); }} /></Sheet>}
  </section>;
}
