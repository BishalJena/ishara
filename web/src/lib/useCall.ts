import {useCallback, useEffect, useRef, useState} from 'react';
import {api} from './api';
import {DemoCall} from './demo';
import {freshCall, indianNumber, reduceEvent} from './state';
import type {CallView, Event, Notes, Setup} from './types';

type Transport = {send(event: Event): void; close(): void; notes(): Promise<Notes>};

export function useCall() {
  const [view, setView] = useState<CallView>(freshCall);
  const [setup, setSetup] = useState<Setup | null>(null);
  const [notes, setNotes] = useState<Notes | null>(null);
  const [notesProblem, setNotesProblem] = useState('');
  const [notesPending, setNotesPending] = useState(false);
  const [starting, setStarting] = useState(false);
  const [demo, setDemo] = useState(true);
  const [callId, setCallId] = useState<string | null>(null);
  const transport = useRef<Transport | null>(null);
  const generation = useRef(0);
  const composing = useRef(false);
  const active = useRef(false);
  const emit = useCallback((event: Event) => setView(old => reduceEvent(old, event)), []);

  const start = useCallback(async (chosen: Setup, isDemo: boolean) => {
    if (active.current || starting) return;
    active.current = true; setStarting(true); setDemo(isDemo);
    setNotes(null); setNotesProblem(''); setView(freshCall()); setSetup(chosen);
    const run = ++generation.current;
    try {
      if (isDemo) {
        const call = new DemoCall(chosen, emit);
        transport.current = call; setCallId(crypto.randomUUID()); call.connect();
      } else {
        const phone = indianNumber(chosen.number);
        if (!phone) throw new Error('Enter a valid 10-digit Indian number.');
        const brief = await api<{brief_id: string}>('/briefs', {purpose: 'general', chips: [], profile: chosen.profile, request: chosen.request});
        // Never automatically retry this POST: a lost response can still mean a call was placed.
        let call: {call_id: string};
        try {
          call = await api<{call_id: string}>('/calls', {phone_number: phone, purpose: 'general', mode: 'steer', brief_id: brief.brief_id, attended: false});
        } catch (error) {
          // Recover the accepted call by its unique brief. Never retry the dial POST.
          try { call = await api<{call_id: string}>(`/briefs/${brief.brief_id}/call`); }
          catch { throw error; }
        }
        setCallId(call.call_id);
        let socket: WebSocket | null = null;
        let retry: ReturnType<typeof setTimeout> | null = null;
        let attempts = 0;
        let closed = false;
        const connection: Transport = {
          send: event => {
            if (socket?.readyState !== WebSocket.OPEN) throw new Error('The connection is unavailable. Your reply was not queued.');
            socket.send(JSON.stringify(event));
          },
          close: () => { closed = true; if (retry) clearTimeout(retry); socket?.close(); },
          notes: () => api<Notes>(`/calls/${call.call_id}/notes`),
        };
        const connect = () => {
          if (closed || generation.current !== run) return;
          const url = new URL(`/calls/${call.call_id}/ws`, window.location.href);
          url.searchParams.set('history', '1');
          url.protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
          socket = new WebSocket(url);
          socket.onopen = () => {
            if (generation.current !== run) { socket?.close(); return; }
            emit({type: 'connected'});
            connection.send({type: 'presence', present: !document.hidden});
          };
          socket.onmessage = message => {
            if (generation.current !== run) return;
            try { emit(JSON.parse(message.data) as Event); } catch { /* Ignore unknown frames. */ }
          };
          socket.onclose = event => {
            if (closed || generation.current !== run) return;
            composing.current = false; emit({type: 'disconnected'});
            const refused: {[code: number]: string} = {4401: 'Unlock the call desk again to continue.', 4404: 'The server no longer knows this call. Ask the recipient to hang up, then start again.', 4409: 'This call was opened in another window.'};
            if (refused[event.code] || attempts >= 3) {
              emit({type: 'error', message: refused[event.code] ?? 'The connection could not be restored. Ask the recipient to hang up.'});
              return;
            }
            retry = setTimeout(connect, [1000, 2000, 4000][attempts++]);
          };
        };
        transport.current = connection; connect();
      }
    } catch (error) {
      active.current = false; setSetup(null);
      emit({type: 'status', state: 'error'});
      emit({type: 'error', message: error instanceof Error ? error.message : 'The call could not be started.'});
    } finally { setStarting(false); }
  }, [emit, starting]);

  const send = useCallback((event: Event) => {
    try {
      if (!transport.current) return false;
      transport.current.send(event); return true;
    } catch (error) { emit({type: 'error', message: error instanceof Error ? error.message : 'Your reply was not sent.'}); return false; }
  }, [emit]);
  const hold = useCallback((value: boolean) => {
    if (composing.current === value || !view.online || view.state === 'ended') return;
    composing.current = value;
    send({type: 'hold', turn_id: view.proposal?.turn_id ?? crypto.randomUUID(), composing: value});
  }, [send, view.online, view.state, view.proposal?.turn_id]);
  const say = useCallback((text: string) => {
    if (!text.trim() || !view.online || !['in_call', 'speaking'].includes(view.state)) return false;
    composing.current = false;
    return send({type: 'say', text: text.trim()});
  }, [send, view.online, view.state]);

  useEffect(() => {
    if (!callId || view.state !== 'ended') return;
    active.current = false;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let attempts = 0;
    setNotesPending(!demo);
    const poll = async () => {
      try {
        const latest = await transport.current?.notes();
        if (cancelled || !latest) return;
        setNotes(latest); setNotesProblem('');
        if (!demo && attempts++ < 30 && (!latest.ready || (!latest.bolna_summary?.trim() && latest.outcome !== 'no_answer'))) timer = setTimeout(poll, 2000);
        else setNotesPending(false);
      } catch { if (!cancelled) { setNotesProblem('The call ended, but its notes could not be loaded. Your captions are still shown below.'); if (attempts++ < 5) timer = setTimeout(poll, 2000); else setNotesPending(false); } }
    };
    void poll();
    return () => { cancelled = true; clearTimeout(timer); setNotesPending(false); };
  }, [callId, view.state, demo]);

  useEffect(() => {
    const visibility = () => { if (active.current && !demo) send({type: 'presence', present: !document.hidden}); };
    const leaving = (event: BeforeUnloadEvent) => { if (active.current) event.preventDefault(); };
    document.addEventListener('visibilitychange', visibility);
    window.addEventListener('beforeunload', leaving);
    return () => { document.removeEventListener('visibilitychange', visibility); window.removeEventListener('beforeunload', leaving); };
  }, [send, demo]);
  useEffect(() => () => { generation.current++; transport.current?.close(); }, []);

  const retryNotes = useCallback(async () => {
    const run = generation.current;
    try {
      const latest = await transport.current?.notes();
      if (latest && run === generation.current) { setNotes(latest); setNotesProblem(''); }
    } catch { if (run === generation.current) setNotesProblem('Notes are still unavailable. Check the backend service, then try again.'); }
  }, []);

  const reset = useCallback(() => {
    generation.current++; transport.current?.close(); transport.current = null;
    active.current = false; composing.current = false;
    setSetup(null); setCallId(null); setNotes(null); setNotesProblem(''); setNotesPending(false); setView(freshCall());
  }, []);
  return {view, setup, notes, notesProblem, notesPending, retryNotes, starting, demo, callId, start, send, say, hold, reset};
}
