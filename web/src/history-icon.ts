import type { IconKey } from './api/types.ts';
import type { GuestSound } from './teach-state.ts';

export interface HistoryIconEvent {
  sound_id: string | null;
}

/** Resolve the icon from the same sound metadata used by Your Sounds. */
export function historyIcon(event: HistoryIconEvent, sounds: readonly GuestSound[]): IconKey {
  if (!event.sound_id) return 'generic';
  return sounds.find(sound => sound.sound_id === event.sound_id)?.icon ?? 'generic';
}
