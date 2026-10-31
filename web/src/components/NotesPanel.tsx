import {useState} from 'react';
import type {Record as CallRecord} from '../lib/types';
import {Icon} from './Icons';
import {callTitle, overview} from '../lib/summary';

const outcomes: {[key: string]: string} = {done: 'Request handled', booked: 'Appointment booked', declined: 'Offer declined', callback: 'A follow-up is needed', unclear: 'Outcome not confirmed', no_answer: 'The call wasn’t answered'};
export function NotesPanel({record, onDone, onRefresh, awaitingSummary = false}: {record: CallRecord; onDone: () => void; onRefresh?: (record: CallRecord) => Promise<void>; awaitingSummary?: boolean}) {
  const notes = record.notes;
  const followUps = [...new Set([...(notes.follow_ups ?? []), ...(notes.open_questions ?? [])])];
  const [refreshing, setRefreshing] = useState(false);
  const [problem, setProblem] = useState('');
  const refresh = async () => {
    if (!onRefresh || refreshing) return;
    setRefreshing(true); setProblem('');
    try { await onRefresh(record); }
    catch { setProblem('Couldn’t refresh this call. Your saved notes and transcript are still available.'); }
    finally { setRefreshing(false); }
  };

  return <section className="notes-screen">
    <header className="notes-navigation"><button aria-label="Back to home" onClick={onDone}><Icon name="back" size={20} /></button><strong>Call summary</strong>{!record.demo && onRefresh ? <button aria-label="Refresh call notes" disabled={refreshing} onClick={() => void refresh()}><Icon name="refresh" size={20} /></button> : <span />}</header>
    <div className="notes-scroll">
      <section className="notes-card notes-primary" aria-labelledby="call-summary-heading">
        <h2 id="call-summary-heading"><Icon name="file" size={18} />Call summary</h2>
        <h1 className="notes-task-title">{callTitle(record)}</h1>
        <p className="notes-summary-text">{overview(notes)}</p>
        {!!notes.presentation?.key_points.length && <ul className="notes-key-points">{notes.presentation.key_points.slice(0, 3).map((point, i) => <li key={i}>{point}</li>)}</ul>}
        {notes.presentation?.next_step && <div className="notes-next-step"><h3>Next step</h3><p>{notes.presentation.next_step}</p></div>}
        {awaitingSummary && <p className="secondary" role="status">Preparing the call summary…</p>}
        <div className={`notes-outcome ${notes.outcome === 'booked' ? 'booked' : ''}`}><Icon name={notes.outcome === 'booked' ? 'check' : 'file'} size={22} /><h2>{notes.ready ? outcomes[notes.outcome ?? 'unclear'] ?? 'Call complete' : 'Wrapping up the call…'}</h2></div>

      </section>
      {problem && <p className="error-message" role="alert">{problem}</p>}
      {notes.presentation?.status !== 'ready' && followUps.length > 0 && <div className="follow-up-box"><h2>What needs your attention</h2>{followUps.map((line, i) => <p key={i}>{line}</p>)}</div>}
      <details className="notes-card notes-transcript"><summary><h2>Transcript</h2><span>{notes.transcript.length} {notes.transcript.length === 1 ? 'line' : 'lines'}</span></summary>{notes.transcript.length === 0 && <p className="secondary">No transcript was captured for this call.</p>}{notes.transcript.map((line, i) => <div key={i}><span className="caption-label">{line.speaker === 'receptionist' ? record.contact : 'Ishara for you'}</span><p>{line.text}</p></div>)}</details>
      <details className="notes-card notes-details"><summary><h2>Call details</h2><Icon name="arrow" size={15} /></summary><h3>Your request</h3><p>{record.request}</p>{notes.summary.length > 0 && <><h3>Recorded details</h3>{notes.summary.map((line, i) => <p key={i}>{line}</p>)}</>}</details>
      <p className="privacy-note">Saved in this browser, with a private 24-hour backend recovery copy. {new Date(record.at).toLocaleString([], {dateStyle: 'medium', timeStyle: 'short'})}</p>
    </div>
    <footer className="notes-footer"><button className="button button-purple" aria-label="Make another call" onClick={onDone}>Done</button></footer>
  </section>;
}
