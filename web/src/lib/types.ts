export type CallState = 'dialing' | 'ringing' | 'in_call' | 'speaking' | 'ended' | 'error';
export type Proposal = {turn_id: string; text: string; window_s: number; origin: 'agent' | 'user'; deadline: number};
export type Caption = {id: string; speaker: 'receptionist' | 'agent' | 'you'; text: string; at: number};
export type Contact = {id: string; name: string; number: string};
export type Profile = {name: string; callback?: string; details: {label: string; value: string}[]; documents: {name: string; text: string}[]};
export type Setup = {number: string; contactName: string; request: string; profile: Profile};
export type CallPresentation = {version: 1; status: 'pending' | 'ready'; title: string; overview: string; key_points: string[]; next_step: string | null};
export type Notes = {call_id: string; ready: boolean; outcome: string | null; brief?: string; summary: string[]; follow_ups: string[]; open_questions: string[]; transcript: {speaker: 'receptionist' | 'agent'; text: string; at: number}[]; bolna_summary?: string | null; presentation?: CallPresentation | null; stepped_in: number};
export type Record = {id: string; contact: string; request: string; at: number; demo: boolean; notes: Notes};
export type Event = {type: string; [key: string]: unknown};
export type Recognition = {kind: 'chip' | 'candidate' | 'unsure'; gloss?: string; reason?: string; p?: number; suggestions?: string[]};
export type CallView = {
  state: CallState; online: boolean; captions: Caption[]; proposal: Proposal | null;
  held: boolean; problem: string; followUps: string[];
};
