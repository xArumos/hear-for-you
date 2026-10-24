import { openMicrophone, type CaptureSession } from './recorder.ts';
import { encodeWav, resampleToSampleRate } from './wav.ts';

/** Sample-counted onset window: 0.5 s before + 2.5 s after, baseline median over 10 s. */
export class SoundGate {
  private samples = new Float32Array(0);
  private baseline: number[] = [];
  private capture: Float32Array | null = null;
  push(chunk: Float32Array): { clip: Blob; levelDb: number } | null {
    const merged = new Float32Array(this.samples.length + chunk.length);
    merged.set(this.samples); merged.set(chunk, this.samples.length); this.samples = merged;
    while (this.samples.length >= 1600) {
      const frame = this.samples.slice(0, 1600); this.samples = this.samples.slice(1600);
      const rms = Math.sqrt(frame.reduce((sum, value) => sum + value * value, 0) / frame.length);
      const level = 20 * Math.log10(Math.max(rms, 1e-8));
      const sorted = [...this.baseline].sort((a, b) => a - b);
      const median = sorted[Math.floor(sorted.length / 2)] ?? level;
      this.baseline.push(level); if (this.baseline.length > 100) this.baseline.shift();
      if (!this.capture && this.baseline.length >= 10 && level > median + 12) this.capture = this.pre;
      if (this.capture) {
        const next: Float32Array = new Float32Array(this.capture.length + frame.length);
        next.set(this.capture); next.set(frame, this.capture.length); this.capture = next;
        if (next.length >= 48000) {
          const clip = next.slice(0, 48000); this.capture = null;
          return { clip: encodeWav(clip), levelDb: 20 * Math.log10(Math.max(1e-8, clip.reduce((peak, value) => Math.max(peak, Math.abs(value)), 0))) };
        }
      }
      const pre = new Float32Array(this.pre.length + frame.length); pre.set(this.pre); pre.set(frame, this.pre.length); this.pre = pre.slice(-8000);
    }
    return null;
  }
  private pre = new Float32Array(0);
}

export async function startMicrophoneListener(options: {
  signal: AbortSignal;
  onClip: (clip: Blob, levelDb: number) => void;
  onError: (error: Error) => void;
}): Promise<CaptureSession> {
  const gate = new SoundGate();
  let session: CaptureSession | undefined;
  // Resample cumulative blocks, avoiding per-worklet-chunk rounding drift.
  let pending = new Float32Array(0);
  session = await openMicrophone(chunk => {
    if (!session || options.signal.aborted) return;
    const next = new Float32Array(pending.length + chunk.length); next.set(pending); next.set(chunk, pending.length); pending = next;
    const frameCount = Math.round(session.sampleRate / 10);
    while (pending.length >= frameCount) {
      const frame = pending.slice(0, frameCount); pending = pending.slice(frameCount);
      const result = gate.push(resampleToSampleRate(frame, session.sampleRate, 16000));
      if (result) options.onClip(result.clip, result.levelDb);
    }
  }, { signal: options.signal, onError: options.onError });
  return session;
}
