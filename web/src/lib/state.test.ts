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
