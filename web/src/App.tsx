import {useEffect, useState} from 'react';
import {api} from './lib/api';
import {useCall} from './lib/useCall';
import {useBackendStatus} from './lib/useBackendStatus';
import {BackendStatus} from './components/BackendStatus';
import type {Contact, Profile, Record as CallRecord} from './lib/types';
import {SetupForm} from './components/SetupForm';
import {CallPanel} from './components/CallPanel';
import {NotesPanel} from './components/NotesPanel';
import {Unlock} from './components/Unlock';
import {Icon, Mark} from './components/Icons';
import {PhoneShell, Sheet} from './components/PhoneShell';

function savedCalls(): CallRecord[] {
  try { const value: unknown = JSON.parse(localStorage.getItem('ishara.calls') ?? '[]'); return Array.isArray(value) ? value.filter(r => r && typeof r.id === 'string' && r.notes && Array.isArray(r.notes.transcript)).slice(0, 10) : []; }
  catch { return []; }
}
function savedProfile(): Profile {
  try { const p = JSON.parse(localStorage.getItem('ishara.profile') ?? '{}'); return {name: typeof p.name === 'string' ? p.name : 'Riya', callback: typeof p.callback === 'string' ? p.callback : '', details: [], documents: []}; }
  catch { return {name: 'Riya', callback: '', details: [], documents: []}; }
}
export function App() {
  const [authenticated, setAuthenticated] = useState<boolean | null>(false);
  const [unlocking, setUnlocking] = useState(false);
  const [settings, setSettings] = useState(false);
  const [profile, setProfile] = useState<Profile>(savedProfile);
  const [demo, setDemo] = useState(true);
  const {status: backendStatus, check: checkBackend} = useBackendStatus();
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [records, setRecords] = useState<CallRecord[]>(savedCalls);
  const [selected, setSelected] = useState<CallRecord | null>(null);
  const [problem, setProblem] = useState('');
  const call = useCall();
  useEffect(() => { void api<{authenticated: boolean}>('/web/session').then(value => setAuthenticated(old => Boolean(old || value.authenticated))).catch(() => {}); }, []);
  useEffect(() => {
    if (!authenticated) { setContacts([]); return; }
    void api<{contacts: Contact[]}>('/web/contacts').then(value => setContacts(value.contacts)).catch(() => {});
  }, [authenticated]);
  useEffect(() => {
    if (!call.notes || !call.setup || !call.callId || !authenticated) return;
    const record: CallRecord = {id: call.callId, contact: call.setup.contactName, request: call.setup.request, at: Date.now(), demo: call.demo, notes: call.notes};
    setRecords(old => {
      const prior = old.find(item => item.id === record.id); if (prior) record.at = prior.at;
      const next = [record, ...old.filter(item => item.id !== record.id)].slice(0, 10);
      try { localStorage.setItem('ishara.calls', JSON.stringify(next)); } catch { /* Storage may be unavailable. */ }
      return next;
    });
  }, [call.notes, call.callId, call.setup, call.demo, authenticated]);
  useEffect(() => {
    if (!authenticated) return;
    void api<{calls: CallRecord['notes'][]}>('/calls/recent').then(value => setRecords(old => {
      const merged = new Map(old.map(record => [record.id, record]));
      for (const notes of value.calls) {
        if (!notes.ready) continue;
        const existing = merged.get(notes.call_id);
        merged.set(notes.call_id, existing ? {...existing, notes} : {id: notes.call_id, contact: 'Recovered call', request: notes.brief ?? 'Recovered conversation', at: notes.transcript[0]?.at ? notes.transcript[0].at * 1000 : Date.now(), demo: false, notes});
      }
      const next = [...merged.values()].sort((a,b) => b.at - a.at).slice(0,10);
      try { localStorage.setItem('ishara.calls', JSON.stringify(next)); } catch { /* Storage is optional. */ }
      return next;
    })).catch(() => {});
  }, [authenticated]);
  const active = Boolean(call.setup && call.view.state !== 'ended');
  const latest = call.notes && call.setup && call.callId ? {id: call.callId, contact: call.setup.contactName, request: call.setup.request, at: Date.now(), demo: call.demo, notes: call.notes} : null;
  const home = () => { if (!active) { call.reset(); setSelected(null); } };
  const chooseMode = (value: boolean) => {
    if (active) return;
    if (!value && !authenticated) { setSettings(false); setUnlocking(true); return; }
    home(); setDemo(value);
  };
  const closeSettings = () => { setSettings(false); try { localStorage.setItem('ishara.profile', JSON.stringify({name: profile.name, callback: profile.callback})); } catch { /* Optional convenience. */ } };
  return <PhoneShell demo={demo} active={active} onMode={chooseMode}>
    {authenticated === null ? <div className="loading-page"><Mark /><p>Opening Ishara…</p></div> : unlocking ? <Unlock onUnlock={() => { setAuthenticated(true); setUnlocking(false); setDemo(false); }} onExplore={() => { setUnlocking(false); setDemo(true); }} /> : selected || latest ? <NotesPanel record={(selected || latest)!} onDone={home} /> : call.setup ? <CallPanel view={call.view} setup={call.setup} demo={call.demo} unlocked={Boolean(authenticated)} onSend={call.send} onSay={call.say} onHold={call.hold} onDone={home} notesProblem={call.notesProblem} onRetryNotes={() => void call.retryNotes()} /> : <div className="setup-scroll">
      <SetupForm demo={demo} unlocked={Boolean(authenticated)} contacts={contacts} starting={call.starting} problem={call.view.problem} profile={profile} onSettings={() => setSettings(true)} onStart={setup => void call.start(setup, demo)} />
      {authenticated && records.length > 0 && <section className="recent-section"><header><h2>Recent</h2><button className="text-button" onClick={() => { setRecords([]); try { localStorage.removeItem('ishara.calls'); } catch { /* Storage may be unavailable. */ } }}>Clear</button></header>{records.map(record => <button className="recent-row" key={record.id} onClick={() => setSelected(record)}><span className="initial-avatar purple">{record.contact.charAt(0)}</span><span><strong>{record.notes.outcome === 'booked' ? 'Appointment booked' : 'Call with ' + record.contact}</strong><small>{record.contact} · {new Date(record.at).toLocaleDateString([], {month: 'short', day: 'numeric'})}</small></span><Icon name="arrow" size={16} /></button>)}</section>}
      <button className="phone-mode-label" onClick={() => setSettings(true)}>{demo ? 'Scripted demo · no phone is dialled' : 'Live calling · approved recipients'}<Icon name="settings" size={13} /></button>
    </div>}
    {settings && <Sheet title="Settings" onClose={closeSettings}><h3>About you</h3><div className="settings-fields"><label>Your name on the call<input value={profile.name} maxLength={60} autoComplete="given-name" onChange={event => setProfile(old => ({...old, name: event.target.value}))} /></label><label>Callback number (optional)<input type="tel" value={profile.callback ?? ''} maxLength={40} onChange={event => setProfile(old => ({...old, callback: event.target.value}))} /></label></div><p className="secondary">Ishara gives your callback number only if they ask how to reach you. Details stay in this browser.</p><h3>Calling mode</h3><div className="mode-switch"><button aria-pressed={demo} onClick={() => chooseMode(true)}>Scripted demo</button><button aria-pressed={!demo} onClick={() => chooseMode(false)}>Live call</button></div><p className="secondary">{demo ? 'A scripted clinic conversation. No telephone request is made.' : 'Calls come from Ishara’s Bolna number and use credits.'}</p><BackendStatus status={backendStatus} check={checkBackend} />{problem && <p className="error-message" role="alert">{problem}</p>}{authenticated ? <button className="button button-outline" onClick={() => void api('/web/logout', {}).then(() => { setAuthenticated(false); setDemo(true); closeSettings(); }).catch(() => setProblem('Couldn’t lock the desk. Check your connection and try again.'))}><Icon name="lock" />Lock live calling</button> : <button className="button button-purple" onClick={() => { setSettings(false); setUnlocking(true); }}><Icon name="lock" />Unlock live calling and signing</button>}</Sheet>}
  </PhoneShell>;
}
