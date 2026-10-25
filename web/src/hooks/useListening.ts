import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { detectClip } from '../api/client';
import type { DetectResponse } from '../api/types';
import { ListeningSession } from '../audio/listening-session';
import { startMicrophoneListener } from '../audio/listener';

export function useListening(onDetection: (result: DetectResponse) => void) {
  const callback = useRef(onDetection);
  callback.current = onDetection;
  const [session] = useState(() => new ListeningSession({
    open: startMicrophoneListener,
    detect: detectClip,
    onDetection: result => callback.current(result),
    now: () => performance.now(),
  }));
  const state = useSyncExternalStore(session.subscribe, session.getSnapshot);
  useEffect(() => {
    const stop = () => { void session.stop(); };
    window.addEventListener('pagehide', stop);
    return () => { window.removeEventListener('pagehide', stop); stop(); };
  }, [session]);
  return { ...state, start: session.start, stop: session.stop, reconnect: session.reconnect, setTeaching: session.setTeaching, record: session.record };
}
export type GlobalListening = ReturnType<typeof useListening>;
