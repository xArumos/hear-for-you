import type { DetectResponse } from './api/types.ts';
import type { GuestSound } from './teach-state.ts';

// Notification grouping only, not a classifier threshold. A gap rearms the category.
export const ONGOING_EVENT_GAP_MS = 10_000;
const sustained = new Set(['builtin_dog_bark', 'builtin_siren', 'builtin_crying_baby']);

// Match complete, background-only descriptions. Never reject by finding a word
// such as "speech" inside a mixed-event description (e.g. alarm with speech).
const backgroundOnly = /^(?:(?:the sound of )?(?:someone (?:is )?(?:speaking|talking|typing)|(?:people|a person) (?:are |is )?(?:speaking|talking)|(?:normal |ordinary )?(?:speech|conversation)|(?:a |the )?(?:keyboard typing|typing on a (?:laptop |computer )?keyboard|mouse clicking|footsteps|fan noise|household background noise)|(?:a |the )?laptop (?:being )?tapped)|(?:a )?loud (?:noise|sound)(?: (?:was )?detected)?)$/i;

export function hasRelevantDescription(description: string | null): boolean {
  const text = description?.trim().replace(/[.!]+$/, '').trim();
  return !!text && !backgroundOnly.test(text);
}

/** One admission decision feeds both the existing alert and local History. */
export class AlertPolicy {
  private seen = new Set<string>();
  private lastObserved = new Map<string, number>();

  accept(result: DetectResponse, sounds: readonly GuestSound[], now: number): boolean {
    if (result.kind === 'none' || this.seen.has(result.event_id)) return false;
    if (result.kind === 'unknown') {
      // Unknown descriptions have no calibrated confidence. Do not manufacture it.
      if (!hasRelevantDescription(result.description)) return false;
    } else {
      const sound = sounds.find(sound => sound.sound_id === result.sound_id && sound.kind === result.kind);
      if (!sound?.enabled) return false;
      const confidence = result.confidence;
      if (confidence === null || !Number.isFinite(confidence) || confidence < 0 || confidence > 1) return false;
      // Mirror existing backend acceptance rules; never raise a global threshold.
      // Taught confidence is a threshold-relative mapping, not a calibrated probability.
      if (result.kind === 'taught' && confidence < 0.5) return false;
      // The backend checks p > 0.6 before rounding to two decimals: an admitted
      // probability just above 0.6 can arrive as 0.60. Preserve that decision.
      if (result.kind === 'builtin' && result.sound_id !== 'builtin_smoke_alarm' && confidence < 0.6) return false;
      if (result.sound_id && sustained.has(result.sound_id)) {
        const previous = this.lastObserved.get(result.sound_id);
        this.lastObserved.set(result.sound_id, now);
        if (previous !== undefined && now - previous < ONGOING_EVENT_GAP_MS) return false;
      }
    }
    this.seen.add(result.event_id);
    return true;
  }
}
