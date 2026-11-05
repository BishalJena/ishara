import {useState, type ReactNode} from 'react';
import type {Contact, Profile, Setup} from '../lib/types';
import {indianNumber} from '../lib/state';
import {CameraPanel} from './CameraPanel';
import {Icon} from './Icons';
import {Sheet} from './PhoneShell';

export function SetupForm({demo, unlocked, contacts, starting, problem, profile, backendStatus, onSettings, onStart}: {
  demo: boolean; unlocked: boolean; contacts: Contact[]; starting: boolean; problem: string; profile: Profile;
  backendStatus?: ReactNode; onSettings: () => void; onStart: (setup: Setup) => void;
}) {
  const [number, setNumber] = useState('');
  const [contactName, setContactName] = useState('');
  const [request, setRequest] = useState('Book a check-up tomorrow morning.');
  const [sheet, setSheet] = useState<'contacts' | 'attach' | 'camera' | null>(null);
  const [documentName, setDocumentName] = useState('');
  const [documentText, setDocumentText] = useState('');
  const [detailLabel, setDetailLabel] = useState('');
  const [detailValue, setDetailValue] = useState('');
  const valid = profile.name.trim() && request.trim() && (demo || (unlocked && indianNumber(number)));
  return <div className="setup-screen">
    <header className="native-topbar"><span className="initial-avatar yellow">{profile.name.charAt(0) || 'I'}</span><strong>Hi {profile.name.split(' ')[0] || 'there'}</strong><button className="circle-button settings-button" aria-label="Settings" onClick={onSettings}><Icon name="settings" /></button></header>
    <h1>Who are we<br />calling today?</h1>
    <form className="native-composer" onSubmit={event => {
      event.preventDefault(); if (!valid || starting) return;
      onStart({number, contactName: demo ? 'City Clinic' : contactName || 'Your contact', request: request.trim(), profile: {...profile,
        details: detailLabel.trim() && detailValue.trim() ? [{label: detailLabel.trim(), value: detailValue.trim()}] : [],
        documents: documentText.trim() ? [{name: documentName.trim() || 'Attached text', text: documentText.trim()}] : [],
      }});
    }}>
      <div className="recipient-line"><span>To</span><span className="country-code">+91</span><input aria-label="Phone number" type="tel" inputMode="tel" autoComplete="tel-national" placeholder={demo ? 'City Clinic · demo' : '10-digit number'} value={number} maxLength={20} onChange={event => { setNumber(event.target.value); setContactName(''); }} />{number && <button type="button" className="clear-number" aria-label="Clear number" onClick={() => { setNumber(''); setContactName(''); }}><Icon name="close" size={15} /></button>}</div>
      <label className="sr-only" htmlFor="request">What’s the call about?</label><textarea id="request" value={request} maxLength={600} rows={4} placeholder="What should Ishara do? e.g. Book a check-up next week, mornings only." onChange={event => setRequest(event.target.value)} />
      {documentText && <button type="button" className="attachment-chip" onClick={() => setSheet('attach')}><Icon name="file" size={17} />{documentName || 'Attached text'}<Icon name="check" size={15} /></button>}
      {problem && <p className="error-message" role="alert">{problem}</p>}
      <div className="composer-toolbar"><button type="button" className="circle-button" aria-label="Attach details or document" onClick={() => setSheet('attach')}><Icon name="paperclip" /></button><button type="button" className="circle-button" aria-label="Contacts" onClick={() => setSheet('contacts')}><Icon name="person" /></button><button type="button" className="circle-button" aria-label="Open signing" onClick={() => setSheet('camera')}><Icon name="hand" /></button><button className="native-call-button" type="submit" disabled={!valid || starting} aria-label={demo ? 'Start scripted call' : 'Place live call'}><Icon name="phone" size={17} />{starting ? 'Calling…' : 'Call'}</button></div>
    </form>
    {backendStatus}
    <p className="setup-disclosure">Ishara leads the call from what you wrote and never adds anything else. It calls from Ishara’s number, not yours. {demo ? 'This is a scripted demo. Nothing is dialled.' : 'Live calls use Bolna credits.'}</p>
    {demo && <div className="native-demo-hint"><Icon name="phone" size={17} /><span>A clinic appointment, ready to try.<small>Tap Call, follow the captions, and step in any time.</small></span></div>}
    {sheet === 'contacts' && <Sheet title="Contacts" onClose={() => setSheet(null)}>{demo ? <button className="contact-choice" onClick={() => { setContactName('City Clinic'); setSheet(null); }}><span className="initial-avatar purple">C</span><span>City Clinic<small>Scripted recipient · no number dialled</small></span><Icon name="check" /></button> : contacts.map(contact => <button className="contact-choice" key={contact.id} onClick={() => { setNumber(contact.number.replace(/^\+91/, '')); setContactName(contact.name); setSheet(null); }}><span className="initial-avatar purple">{contact.name.charAt(0)}</span><span>{contact.name}<small>{contact.number}</small></span></button>)}{!demo && !contacts.length && <p className="secondary">No approved contacts are available. Check your connection or unlock the call desk.</p>}</Sheet>}
    {sheet === 'attach' && <Sheet title="Details for the call" onClose={() => setSheet(null)}><p className="secondary">Ishara shares only what you provide, and quotes documents word for word only when asked.</p><label>Detail label<input value={detailLabel} maxLength={40} onChange={event => setDetailLabel(event.target.value)} placeholder="For example, patient ID" /></label><label>Detail value<input value={detailValue} maxLength={80} onChange={event => setDetailValue(event.target.value)} /></label><label>Document title<input value={documentName} maxLength={80} onChange={event => setDocumentName(event.target.value)} placeholder="Appointment letter" /></label><label>Document text<textarea value={documentText} maxLength={20000} rows={5} onChange={event => setDocumentText(event.target.value)} placeholder="Paste the text to quote on the call" /></label>{documentText && <button className="text-button danger" onClick={() => { setDocumentText(''); setDocumentName(''); }}>Remove document</button>}</Sheet>}
    {sheet === 'camera' && <Sheet title="Sign your request" onClose={() => setSheet(null)}><CameraPanel enabled={unlocked} onWords={text => { setRequest(old => `${old.trim()} ${text}`.trim().slice(0, 600)); setSheet(null); }} /></Sheet>}
  </div>;
}
