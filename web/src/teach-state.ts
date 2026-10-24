export interface RecordingStep {
  blob: Blob | null;
  valid: boolean;
}

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
