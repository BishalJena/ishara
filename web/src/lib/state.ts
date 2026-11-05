import type {CallView, Event, Proposal} from './types';

export const freshCall = (): CallView => ({state: 'dialing', online: false, captions: [], proposal: null, held: false, problem: '', followUps: []});

export function reduceEvent(state: CallView, event: Event, now = Date.now()): CallView {
  switch (event.type) {
    case 'connected': return {...state, online: true, problem: ''};
    case 'disconnected': return {...state, online: false, proposal: null, held: false, problem: 'Connection lost. Delivery isn’t confirmed. Reconnecting…'};
    case 'status': return {...state, state: event.state as CallView['state'], ...(event.state === 'ended' || event.state === 'error' ? {proposal: null, held: false} : {})};
    case 'history': {
      const entries = Array.isArray(event.entries) ? event.entries as {speaker: 'agent' | 'receptionist'; text: string; at: number}[] : [];
      return {...state, captions: entries.map(entry => ({...entry, id: `${entry.speaker}-${entry.at}-${entry.text}`}))};
    }
    case 'caption': {
      const item = {id: `${event.speaker}-${event.at}-${event.text}`, speaker: event.speaker as 'agent' | 'receptionist', text: String(event.text), at: Number(event.at)};
      return state.captions.some(x => x.id === item.id) ? state : {...state, captions: [...state.captions, item]};
    }
    case 'proposal':
      if (!state.online || state.state === 'ended' || state.state === 'error') return state;
      return {...state, held: false, proposal: {...event, deadline: now + Number(event.window_s) * 1000} as unknown as Proposal};
    case 'proposal_resolved':
      if (!state.proposal || state.proposal.turn_id !== event.turn_id) return state;
      return {...state, proposal: null, held: event.outcome === 'held', captions: state.proposal.origin === 'user' && event.outcome === 'spoken' ? [...state.captions, {id: `user-${state.proposal.turn_id}`, speaker: 'you', text: state.proposal.text, at: now / 1000}] : state.captions};
    case 'follow_up': return {...state, followUps: [...state.followUps, String(event.text)]};
    case 'error': return {...state, problem: String(event.message)};
    case 'not_delivered': return {...state, proposal: null, problem: 'Your reply was not confirmed. Check the connection before trying again.'};
    default: return state;
  }
}

export function indianNumber(raw: string): string | null {
  let digits = raw.replace(/\D/g, '');
  if (digits.length === 12 && digits.startsWith('91')) digits = digits.slice(2);
  if (digits.length === 11 && digits.startsWith('0')) digits = digits.slice(1);
  return /^[2-9]\d{9}$/.test(digits) ? `+91${digits}` : null;
}

export const spokenWord = (word: string) => ({thankyou: 'thank you', callonphone: 'call'}[word] ?? word);
