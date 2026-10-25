export interface RecordingStep {
  blob: Blob | null;
  valid: boolean;
}

export type GuestSoundKind = 'builtin' | 'taught';

export interface GuestSound {
  sound_id: string;
  name: string;
  icon: string;
  kind: GuestSoundKind;
  enabled: boolean;
}

export const DEFAULT_BUILTIN_SOUNDS: GuestSound[] = [
  { sound_id: 'builtin_smoke_alarm', name: 'Smoke alarm', icon: 'alarm', kind: 'builtin', enabled: true },
  { sound_id: 'builtin_crying_baby', name: 'Crying baby', icon: 'baby', kind: 'builtin', enabled: true },
  { sound_id: 'builtin_dog_bark', name: 'Dog bark', icon: 'dog', kind: 'builtin', enabled: true },
  { sound_id: 'builtin_door_knock', name: 'Door knock', icon: 'door', kind: 'builtin', enabled: true },
  { sound_id: 'builtin_glass_breaking', name: 'Glass breaking', icon: 'glass', kind: 'builtin', enabled: true },
  { sound_id: 'builtin_siren', name: 'Siren', icon: 'siren', kind: 'builtin', enabled: true },
];

export function countCompletedRecordings(recordings: readonly RecordingStep[]): number {
  return recordings.filter((recording) => recording.blob instanceof Blob && recording.valid).length;
}

export function isReadyToSave(name: string, recordings: readonly RecordingStep[]): boolean {
  const trimmedName = name.trim();
  if (!trimmedName || trimmedName.length > 40) {
    return false;
  }

  if (recordings.length !== 4) {
    return false;
  }

  return recordings.every((recording) => recording.blob instanceof Blob && recording.valid);
}

export function filterEnabledSounds<T extends { sound_id?: string; kind?: string; enabled?: boolean }>(items: readonly T[]): T[] {
  return items.filter((item) => {
    if (!item.sound_id) return true;
    if (item.kind === 'builtin' || item.kind === 'taught') {
      return item.enabled !== false;
    }
    return true;
  });
}

export function mergeBuiltinsWithSaved(currentBuiltins: readonly GuestSound[] | null | undefined): GuestSound[] {
  const nextById = new Map<string, GuestSound>();

  for (const sound of DEFAULT_BUILTIN_SOUNDS) {
    nextById.set(sound.sound_id, { ...sound, enabled: sound.enabled });
  }

  for (const sound of currentBuiltins ?? []) {
    if (sound.kind !== 'builtin') continue;
    nextById.set(sound.sound_id, { ...sound, kind: 'builtin', enabled: sound.enabled !== false });
  }

  return [...nextById.values()];
}
