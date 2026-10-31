import type {Caption, Event, Notes, Setup} from './types';

/** Clearly labelled rehearsal. It never calls the telephone or text-generation APIs. */
export class DemoCall {
  private timers = new Set<ReturnType<typeof setTimeout>>();
  private pending: {id: string; text: string; origin: string} | null = null;
  private proposalTimer?: ReturnType<typeof setTimeout>;
  private finished = false;
  private captions: Caption[] = [];
  private steppedIn = 0;
  private booked = false;
  private composing = false;
  constructor(private setup: Setup, private emit: (event: Event) => void) {}
  private after(ms: number, action: () => void) {
    const timer = setTimeout(() => { this.timers.delete(timer); if (!this.finished) action(); }, ms);
    this.timers.add(timer); return timer;
  }
  private caption(speaker: 'agent' | 'receptionist', text: string) {
    const at = Date.now() / 1000;
    this.captions.push({id: crypto.randomUUID(), speaker, text, at});
    this.emit({type: 'caption', speaker, text, at});
  }
  connect() {
    this.emit({type: 'connected'});
    this.emit({type: 'status', state: 'dialing'});
    this.after(900, () => this.emit({type: 'status', state: 'ringing'}));
    this.after(2200, () => {
      this.emit({type: 'status', state: 'in_call'});
      this.caption('agent', `Hello, I’m calling for ${this.setup.profile.name}, who is using Ishara. This is an automated voice speaking on their behalf.`);
    });
    this.after(3800, () => this.caption('receptionist', 'Hello, City Clinic. How can I help?'));
    this.after(5200, () => this.caption('agent', this.setup.request));
    this.after(7800, () => this.caption('receptionist', 'We have 10:30 tomorrow morning. Would that work?'));
    this.after(9000, () => {
      const fits = /tomorrow/i.test(this.setup.request) && !/afternoon|evening|next week/i.test(this.setup.request);
      this.booked = fits;
      this.propose(fits ? 'Yes, tomorrow morning works. Please book that.' : 'I’ll need to check that and call back. Thank you.', 'agent');
    });
  }
  private propose(text: string, origin: 'agent' | 'user') {
    if (this.proposalTimer) clearTimeout(this.proposalTimer);
    const id = crypto.randomUUID();
    this.pending = {id, text, origin};
    if (this.composing && origin === 'agent') {
      this.emit({type: 'proposal_resolved', turn_id: id, outcome: 'held'});
      return;
    }
    this.emit({type: 'proposal', turn_id: id, text, origin, window_s: origin === 'user' ? 1.5 : 2});
    this.proposalTimer = this.after(origin === 'user' ? 1500 : 2000, () => this.speak());
  }
  private speak() {
    if (!this.pending) return;
    const {id, text} = this.pending;
    this.pending = null;
    this.emit({type: 'proposal_resolved', turn_id: id, outcome: 'spoken'});
    this.caption('agent', text);
    this.after(2600, () => this.caption('receptionist', this.booked ? 'All right, that’s booked. Thank you!' : 'Of course. Thank you for calling.'));
    this.after(4300, () => { this.caption('agent', 'Thank you. Goodbye.'); this.end(); });
  }
  send(event: Event) {
    if (this.finished) return;
    if (event.type === 'end') { this.end(); return; }
    if (event.type === 'hold' && event.composing) {
      this.composing = true;
      if (this.proposalTimer) clearTimeout(this.proposalTimer);
      this.emit({type: 'proposal_resolved', turn_id: this.pending?.id, outcome: 'held'});
      this.caption('agent', 'One moment, please.');
    }
    if (event.type === 'hold' && !event.composing) {
      this.composing = false;
      if (this.pending) this.propose(this.pending.text, this.pending.origin as 'agent' | 'user');
    }
    if (event.type === 'say') {
      this.composing = false;
      this.steppedIn++;
      const text = String(event.text).trim();
      this.propose(text.charAt(0).toUpperCase() + text.slice(1), 'user');
    }
    if (event.type === 'approve' && event.turn_id === this.pending?.id) {
      if (this.proposalTimer) clearTimeout(this.proposalTimer);
      this.speak();
    }
  }
  private end() {
    this.finished = true; this.close(); this.emit({type: 'status', state: 'ended'});
  }
  async notes(): Promise<Notes> {
    return {call_id: 'demo', ready: this.finished, outcome: this.booked ? 'booked' : 'callback',
      presentation: {version: 1, status: 'ready', title: 'Book a clinic check-up', overview: this.booked ? 'The scripted clinic booked the appointment.' : 'The scripted call ended with a follow-up needed.', key_points: this.booked ? ['Tomorrow morning at 10:30.'] : [], next_step: this.booked ? null : 'Call the clinic back.'},
      brief: this.setup.request, summary: [this.booked ? 'The scripted clinic offered 10:30 tomorrow morning.' : 'The scripted call ended with a request to call back.'],
      follow_ups: [], open_questions: [], stepped_in: this.steppedIn,
      transcript: this.captions.map(({speaker, text, at}) => ({speaker: speaker as 'agent' | 'receptionist', text, at}))};
  }
  close() { this.timers.forEach(clearTimeout); this.timers.clear(); }
}
