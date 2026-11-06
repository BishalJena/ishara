import {test} from 'node:test';
import assert from 'node:assert/strict';
import {freshCall, indianNumber, reduceEvent} from './state';

test('network loss drops a proposal rather than leaving a stale approval available', () => {
  let state = reduceEvent(freshCall(), {type: 'connected'});
  state = reduceEvent(state, {type: 'status', state: 'in_call'});
  state = reduceEvent(state, {type: 'proposal', turn_id: 'p1', text: 'An approved line', origin: 'agent', window_s: 2}, 1000);
  assert.equal(state.proposal?.deadline, 3000);
  state = reduceEvent(state, {type: 'disconnected'});
  assert.equal(state.proposal, null);
  assert.equal(state.online, false);
  assert.equal(reduceEvent(state, {type: 'proposal', turn_id: 'late', window_s: 2}), state);
});

test('a stale resolution cannot clear a newer proposal', () => {
  let state = reduceEvent(freshCall(), {type: 'connected'});
  state = reduceEvent(state, {type: 'proposal', turn_id: 'current', text: 'Current', window_s: 2});
  assert.equal(reduceEvent(state, {type: 'proposal_resolved', turn_id: 'old', outcome: 'spoken'}), state);
});

test('a call ending removes approvals and ignores later proposals', () => {
  let state = reduceEvent(freshCall(), {type: 'connected'});
  state = reduceEvent(state, {type: 'status', state: 'ended'});
  assert.equal(reduceEvent(state, {type: 'proposal', turn_id: 'late', window_s: 2}), state);
});

test('invalid and partial phone entries do not become a dial target', () => {
  assert.equal(indianNumber(''), null);
  assert.equal(indianNumber('123'), null);
  assert.equal(indianNumber('a number'), null);
});


test('reconnected history restores both sides exactly once without restoring an approval', () => {
  let state = reduceEvent(freshCall(), {type: 'connected'});
  const history = {type: 'history', entries: [{speaker: 'receptionist', text: 'A question', at: 1}, {speaker: 'agent', text: 'An answer', at: 2}]};
  state = reduceEvent(state, history);
  state = reduceEvent(state, history);
  assert.deepEqual(state.captions.map(c => c.text), ['A question', 'An answer']);
  assert.equal(state.proposal, null);
});

import {callTitle, overview, requestTitle, summaryComplete} from './summary';
import type {Notes, Record as CallRecord} from './types';
test('canonical presentation controls the title and readiness without changing the outcome', () => {
  const notes: Notes = {call_id: 'fixture', ready: true, outcome: 'unclear', summary: ['They offered a time.'], follow_ups: [], open_questions: [], stepped_in: 0, transcript: [], bolna_summary: 'The appointment was booked.', presentation: {version: 1, status: 'pending', title: 'Appointment with Dr. Rao', overview: 'Registration is still needed.', key_points: ['No booking confirmed.'], next_step: 'Provide the registration ID.'}};
  const record: CallRecord = {id: 'fixture', contact: 'Synthetic recipient', request: 'Book an appointment.', at: 1, demo: false, notes};
  assert.equal(summaryComplete(notes), false);
  assert.equal(callTitle(record), 'Appointment with Dr. Rao');
  assert.equal(overview(notes), 'Registration is still needed.');
  assert.equal(notes.outcome, 'unclear');
  assert.equal(summaryComplete({...notes, presentation: {...notes.presentation!, status: 'ready'}}), true);
  assert.equal(callTitle({...record, notes: {...notes, presentation: undefined}, request: 'Please ask a plumber about a leaking pipe.'}), 'Ask a plumber about a leaking pipe');
  assert.equal(overview({...notes, presentation: undefined}), 'The call ended without a confirmed outcome.');
});

test('legacy general brief title comes from its Request clause and preserves Dr. abbreviation', () => {
  const brief = 'Call on behalf of Asha, who uses the Ishara app, to carry out their approved request. Request: Book an appointment with Dr. Rao. Preferred: tomorrow morning. Reason, if asked: a routine check-up. May share: supplied report. Will not agree to unrelated requests.';
  assert.equal(requestTitle(brief), 'Book an appointment with Dr. Rao');
  for (const context of ['Preferred: tomorrow.', 'Reason, if asked: a check-up.', 'May share: supplied report.', 'Will not agree to unrelated requests.']) {
    assert.equal(requestTitle('Call on behalf of Asha, to carry out their approved request. Request: Book an appointment with Dr. Rao. ' + context), 'Book an appointment with Dr. Rao');
  }
});
