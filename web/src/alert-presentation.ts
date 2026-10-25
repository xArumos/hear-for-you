import type { DetectResponse, IconKey } from './api/types.ts';
import { historyIcon } from './history-icon.ts';
import type { GuestSound } from './teach-state.ts';

export interface AlertPresentation {
  className: 'recognized' | 'taught' | 'unknown';
  icon: IconKey;
}

/** Use the same saved sound metadata that powers Your Sounds and History. */
export function alertPresentation(
  detection: DetectResponse,
  sounds: readonly GuestSound[],
): AlertPresentation {
  if (detection.kind === 'unknown') return { className: 'unknown', icon: 'generic' };
  return {
    className: detection.kind === 'taught' ? 'taught' : 'recognized',
    icon: historyIcon(detection, sounds),
  };
}
