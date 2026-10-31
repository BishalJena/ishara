import {useState} from 'react';
import type {Record as CallRecord} from '../lib/types';
import {Icon} from './Icons';

const outcomes: {[key: string]: string} = {booked: 'Appointment booked', declined: 'Offer declined', callback: 'A follow-up is needed', unclear: 'Review the conversation', no_answer: 'The call wasn’t answered'};
export function NotesPanel({record, onDone, onRefresh, awaitingSummary = false}: {record: CallRecord; onDone: () => void; onRefresh?: (record: CallRecord) => Promise<void>; awaitingSummary?: boolean}) {
  const notes = record.notes;
  const automatic = notes.bolna_summary?.trim();
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
  const availability = notes.outcome === 'no_answer' ? 'No one answered, so there is no conversation to summarize.' : awaitingSummary ? 'The automatic summary is being prepared. You can already read the transcript below.' : 'An automatic summary is not available for this call.';
  return <section className="notes-screen">
    <header className="notes-navigation"><button aria-label="Back to home" onClick={onDone}><Icon name="back" size={20} /></button><strong>Call with {record.contact}</strong>{!record.demo && onRefresh ? <button aria-label="Refresh call notes" disabled={refreshing} onClick={() => void refresh()}><Icon name="refresh" size={20} /></button> : <span />}</header>
    <div className="notes-scroll">
      <section className="notes-card notes-primary" aria-labelledby="call-summary-heading">
        <h2 id="call-summary-heading"><Icon name="file" size={18} />Call summary</h2>
        {automatic ? <><p className="notes-summary-text">{automatic}</p><p className="summary-source">Automatic summary · read the transcript for exact words.</p></> : <>
          {!record.demo && <p className="secondary" role="status">{availability}</p>}
          {notes.summary.filter(line => line.trim()).map((line, i) => <p key={i}>{line}</p>)}
          {!!notes.summary.length && <p className="summary-source">{record.demo ? 'Scripted demo summary.' : 'From the recorded call details.'}</p>}
        </>}
        <div className={`notes-outcome ${notes.outcome === 'booked' ? 'booked' : ''}`}><Icon name={notes.outcome === 'booked' ? 'check' : 'file'} size={22} /><h1>{notes.ready ? outcomes[notes.outcome ?? 'unclear'] ?? 'Call complete' : 'Wrapping up the call…'}</h1></div>
        <p className="notes-handled">{notes.stepped_in ? `You stepped in ${notes.stepped_in === 1 ? 'once' : `${notes.stepped_in} times`}; Ishara handled the rest.` : 'Ishara handled the call from what you wrote.'}</p>
      </section>
      {problem && <p className="error-message" role="alert">{problem}</p>}
      {followUps.length > 0 && <div className="follow-up-box"><h2>What needs your attention</h2>{followUps.map((line, i) => <p key={i}>{line}</p>)}</div>}
      <details className="notes-card notes-transcript"><summary><h2>Transcript</h2><span>{notes.transcript.length} {notes.transcript.length === 1 ? 'line' : 'lines'}</span></summary>{notes.transcript.length === 0 && <p className="secondary">No transcript was captured for this call.</p>}{notes.transcript.map((line, i) => <div key={i}><span className="caption-label">{line.speaker === 'receptionist' ? record.contact : 'Ishara for you'}</span><p>{line.text}</p></div>)}</details>
      <details className="notes-card notes-details"><summary><h2>Call details</h2><Icon name="arrow" size={15} /></summary><h3>Your request</h3><p>{record.request}</p>{automatic && notes.summary.length > 0 && <><h3>Recorded details</h3>{notes.summary.map((line, i) => <p key={i}>{line}</p>)}</>}</details>
      <p className="privacy-note">Saved in this browser, with a private 24-hour backend recovery copy. {new Date(record.at).toLocaleString([], {dateStyle: 'medium', timeStyle: 'short'})}</p>
    </div>
    <footer className="notes-footer"><button className="button button-purple" aria-label="Make another call" onClick={onDone}>Done</button></footer>
  </section>;
}
