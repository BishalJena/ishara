import type {Notes, Record as CallRecord} from './types';

export function requestTitle(request?: string): string {
  let intent = request?.trim();
  if (intent?.startsWith('Call on behalf of ')) {
    intent = intent.includes('Request:') ? intent.slice(intent.indexOf('Request:') + 'Request:'.length).trim() : intent.replace(/^Call on behalf of .*?, to /, '');
  }
  intent = intent?.split(/\s+(?:Preferred:|Reason, if asked:|May share:|Will not agree)/)[0];
  const text = intent?.replace(/^(I would like to |I'd like to |I want to |Please |Can you )/i, '').split(/\s+/).slice(0, 7).join(' ').replace(/[.!?]+$/, '');
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : 'Call summary';
}
export const callTitle = (record: CallRecord) => record.notes.presentation?.title?.trim() || requestTitle(record.request || record.notes.brief);
export const summaryComplete = (notes: Notes) => notes.ready && (notes.presentation?.status === 'ready' || notes.outcome === 'no_answer');
export function overview(notes: Notes): string {
  return notes.presentation?.overview?.trim() || ({booked: 'The appointment was booked.', done: 'The request was handled.', no_answer: 'Nobody answered the call.', callback: 'A follow-up is needed to finish the request.', declined: 'No suitable offer was accepted.'}[notes.outcome ?? ''] ?? 'The call ended without a confirmed outcome.');
}
