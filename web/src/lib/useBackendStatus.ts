import {useCallback, useEffect, useRef, useState} from 'react';

export type BackendHealth = {state: 'checking' | 'online' | 'unavailable' | 'unconfigured'; checking: boolean; checked_at?: string; configured?: boolean};
export function useBackendStatus() {
  const [status, setStatus] = useState<BackendHealth>({state: 'checking', checking: false});
  const pending = useRef(false);
  const check = useCallback(async () => {
    if (pending.current) return;
    pending.current = true; setStatus(old => ({...old, checking: true}));
    try {
      const response = await fetch('/service-status', {cache: 'no-store', signal: AbortSignal.timeout(6000)});
      if (!response.ok) throw new Error('unavailable');
      const value = await response.json();
      setStatus({state: ['online','unavailable','unconfigured'].includes(value.state) ? value.state : 'unavailable', checked_at: value.checked_at, configured: value.configured, checking: false});
    } catch { setStatus({state: 'unavailable', checking: false, checked_at: new Date().toISOString()}); }
    finally { pending.current = false; }
  }, []);
  useEffect(() => { void check(); const timer = setInterval(() => void check(), 30000); return () => clearInterval(timer); }, [check]);
  return {status, check};
}
