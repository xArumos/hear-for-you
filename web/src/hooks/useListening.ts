import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { detectClip } from '../api/client';
import type { DetectResponse } from '../api/types';
import { ListeningSession } from '../audio/listening-session';
import { startMicrophoneListener } from '../audio/listener';

export function useListening(onDetection: (result: DetectResponse) => void, page: string) {
  const callback = useRef(onDetection);
  callback.current = onDetection;
  const [session] = useState(() => new ListeningSession({
    open: startMicrophoneListener,
    detect: detectClip,
    onDetection: result => callback.current(result),
    now: () => performance.now(),
  }));
  const state = useSyncExternalStore(session.subscribe, session.getSnapshot);
  const syncPreviews = () => session.setPreviewing(
    Array.from(document.querySelectorAll<HTMLAudioElement>('.playback audio'))
      .some(audio => !audio.paused && !audio.ended && !audio.error),
  );
  // Removed/changed audio elements may not bubble pause events to document.
  useEffect(syncPreviews, [page, session]);
  useEffect(() => {
    const stop = () => { void session.stop(); };
    const preview = syncPreviews;
    for (const event of ['play', 'pause', 'ended', 'error']) document.addEventListener(event, preview, true);
    window.addEventListener('pagehide', stop);
    window.addEventListener('hear-for-you-native-inactive', stop);
    return () => {
      for (const event of ['play', 'pause', 'ended', 'error']) document.removeEventListener(event, preview, true);
      window.removeEventListener('pagehide', stop);
      window.removeEventListener('hear-for-you-native-inactive', stop);
      stop();
    };
  }, [session]);
  return { ...state, start: session.start, stop: session.stop, reconnect: session.reconnect, setTeaching: session.setTeaching, record: session.record };
}
export type GlobalListening = ReturnType<typeof useListening>;
