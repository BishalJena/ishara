import type {BackendHealth} from '../lib/useBackendStatus';
import {Icon} from './Icons';

export function BackendStatus({status, check}: {status: BackendHealth; check: () => Promise<void>}) {
  const label = status.state === 'checking' ? 'Checking backend…' : status.state === 'online' ? (status.configured === false ? 'Backend online · setup incomplete' : 'Backend online') : 'Backend unavailable';
  return <details className="backend-details">
    <summary className={`service-status ${status.state === 'online' ? 'is-online' : ''}`} onClick={() => void check()} aria-label="Backend status">
      <span className={`dot ${status.state === 'online' ? 'green' : ''}`} /><span>{label}</span><Icon name="arrow" size={13} />
    </summary>
    <div role="region" aria-label="Backend status">
      <p className="service-status-heading">{label}</p>
      <p className="secondary">{status.checked_at ? 'Last checked ' + new Date(status.checked_at).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit', second: '2-digit'}) + '.' : 'Checking the live service.'} The service is checked every 30 seconds.</p>
      <button className="button button-purple" disabled={status.checking} onClick={() => void check()}>{status.checking ? 'Checking…' : 'Check again'}</button>
      <h3>If the backend is unavailable</h3>
      <p className="secondary">Check your connection and ask the demo operator to verify the backend service. A failed service check can also mean a network problem.</p>
      <p className="privacy-note">Do not restart the backend during a call. The scripted demo remains available when the backend is down.</p>
    </div>
  </details>;
}
