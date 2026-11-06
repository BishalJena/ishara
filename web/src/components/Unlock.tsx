import {useState} from 'react';
import {APIError, api} from '../lib/api';
import {Icon, Mark} from './Icons';

export function Unlock({onUnlock, onExplore}: {onUnlock: () => void; onExplore: () => void}) {
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState('');
  return <main className="unlock-screen"><button className="text-button" onClick={onExplore}><Icon name="back" size={18} />Back</button><div className="unlock-brand"><Mark /><strong>Ishara</strong></div><h1>Your conversation.<br />Your control.</h1><p className="secondary">Unlock live calling and webcam signing with your demo access code.</p><form onSubmit={event => {
    event.preventDefault(); if (!code || busy) return; setBusy(true); setProblem('');
    void api('/web/session', {code}).then(() => { setCode(''); onUnlock(); }).catch(error => setProblem(error instanceof APIError && error.status === 401 ? 'That access code wasn’t accepted. Try again.' : error.message)).finally(() => setBusy(false));
  }}><label htmlFor="access-code">Demo access code</label><input id="access-code" type="password" autoComplete="current-password" autoCapitalize="none" autoCorrect="off" value={code} onChange={event => setCode(event.target.value)} placeholder="Enter your access code" />{problem && <p role="alert" className="error-message">{problem}</p>}<button className="button button-purple" disabled={!code || busy}>{busy ? 'Opening…' : 'Open call desk'}</button></form><button className="button button-outline" onClick={onExplore}>Explore a scripted demo</button><p className="privacy-note"><Icon name="shield" size={15} /><span>The scripted demo places no calls. Live calls use Ishara’s calling number and approved recipients only.</span></p></main>;
}
