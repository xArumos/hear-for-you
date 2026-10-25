import type { DetectResponse } from '../api/types.ts';
import { DetectionRetryBudget } from '../api/errors.ts';
import { explainMicrophoneError, type CaptureSession } from './recorder.ts';

export interface ListeningState {
  status: 'active' | 'paused' | 'reconnecting' | 'teaching';
  error: string | null;
}
interface Dependencies {
  open(options: { signal: AbortSignal; onClip(clip: Blob, levelDb: number): void; onError(error: Error): void }): Promise<CaptureSession>;
  detect(clip: Blob, levelDb: number, signal: AbortSignal): Promise<DetectResponse>;
  onDetection(result: DetectResponse): void;
  now(): number;
  schedule?(callback: () => void, delayMs: number): () => void;
}

export const PENDING_CLIP_MAX_AGE_MS = 5_000;
const MIN_REQUEST_GAP_MS = 1_000;

/** Owned by App, never by a page. Serialize capture teardown before acquiring again. */
export class ListeningSession {
  private state: ListeningState = { status: 'paused', error: null };
  private subscribers = new Set<() => void>();
  private enabled = false;
  private teaching = false;
  private previewing = false;
  private controller: AbortController | null = null;
  private capture: CaptureSession | null = null;
  private recording: Promise<void> | null = null;
  private opening: Promise<void> = Promise.resolve();
  private cleanup: Promise<void> = Promise.resolve();

  private readonly deps: Dependencies;
  constructor(deps: Dependencies) { this.deps = deps; }
  getSnapshot = (): ListeningState => this.state;
  subscribe = (callback: () => void): (() => void) => {
    this.subscribers.add(callback);
    return () => { this.subscribers.delete(callback); };
  };
  private update(status: ListeningState['status'], error: string | null = null): void {
    this.state = { status, error };
    this.subscribers.forEach(callback => callback());
  }
  start = (): void => {
    this.enabled = true;
    if (this.teaching || this.previewing) { this.update('teaching'); return; }
    this.launch();
  };
  stop = (): Promise<void> => {
    this.enabled = false;
    this.update('paused');
    return this.release();
  };
  reconnect = (): void => { void this.stop(); this.start(); };
  setTeaching = (teaching: boolean): Promise<void> => {
    this.teaching = teaching;
    return this.syncSuspension();
  };
  setPreviewing = (previewing: boolean): void => {
    this.previewing = previewing;
    void this.syncSuspension();
  };
  private syncSuspension(): Promise<void> {
    if (this.teaching || this.previewing) {
      this.update(this.enabled ? 'teaching' : 'paused', this.state.error);
      return this.release();
    }
    if (this.enabled) this.launch();
    return this.cleanup;
  }
  record = async <T>(task: () => Promise<T>): Promise<T> => {
    if (this.recording) throw new Error('A teaching recording is already active.');
    const released = this.setTeaching(true);
    let finish: () => void = () => {};
    this.recording = new Promise<void>(resolve => { finish = resolve; });
    try {
      await released;
      return await task();
    } finally {
      finish();
      this.recording = null;
    }
  };
  private release(): Promise<void> {
    this.controller?.abort();
    this.controller = null;
    const capture = this.capture;
    this.capture = null;
    this.cleanup = Promise.all([this.cleanup, this.opening, capture?.stop()]).then(() => {});
    return this.cleanup;
  }
  private fail(error: string): void {
    this.enabled = false;
    this.update('paused', error);
    void this.release();
  }
  private schedule(callback: () => void, delayMs: number): () => void {
    if (this.deps.schedule) return this.deps.schedule(callback, delayMs);
    const timer = setTimeout(callback, delayMs);
    return () => clearTimeout(timer);
  }
  private launch(): void {
    if (this.controller || !this.enabled || this.teaching || this.previewing) return;
    const controller = new AbortController();
    this.controller = controller;
    this.update('reconnecting');
    const cleanup = this.cleanup;
    const recording = this.recording;
    let busy = false, nextRequestAt = 0;
    let pending: { clip: Blob; levelDb: number; capturedAt: number } | null = null;
    let cancelScheduled: (() => void) | null = null;
    const retries = new DetectionRetryBudget();
    const clearPending = () => {
      pending = null;
      cancelScheduled?.();
      cancelScheduled = null;
    };
    controller.signal.addEventListener('abort', clearPending, { once: true });

    const submit = (clip: Blob, levelDb: number): void => {
      if (controller.signal.aborted) return;
      busy = true;
      nextRequestAt = this.deps.now() + MIN_REQUEST_GAP_MS;
      void this.deps.detect(clip, levelDb, controller.signal).then(result => {
        if (controller.signal.aborted) return;
        retries.success(); this.update('active');
        this.deps.onDetection(result);
      }).catch(error => {
        if (controller.signal.aborted) return;
        const retry = retries.failure(error);
        const message = error instanceof Error ? error.message : 'Detection request failed.';
        if (retry.stop) this.fail(`${message} Listening stopped. Resolve the backend issue, then start again.`);
        else {
          nextRequestAt = this.deps.now() + retry.delayMs;
          this.update('active', `${message} Waiting before the next detection attempt.`);
        }
      }).finally(() => {
        busy = false;
        submitPending();
      });
    };

    const submitPending = (): void => {
      cancelScheduled?.();
      cancelScheduled = null;
      if (!pending || busy || controller.signal.aborted) return;
      const age = this.deps.now() - pending.capturedAt;
      if (age >= PENDING_CLIP_MAX_AGE_MS) { pending = null; return; }
      const requestDelay = Math.max(0, nextRequestAt - this.deps.now());
      if (requestDelay > 0) {
        const staleDelay = PENDING_CLIP_MAX_AGE_MS - age;
        cancelScheduled = this.schedule(submitPending, Math.min(requestDelay, staleDelay));
        return;
      }
      const next = pending;
      pending = null;
      submit(next.clip, next.levelDb);
    };

    this.opening = (async () => {
      await cleanup;
      await recording;
      if (controller.signal.aborted) return;
      try {
        const capture = await this.deps.open({
          signal: controller.signal,
          onError: error => { if (!controller.signal.aborted) this.fail(explainMicrophoneError(error)); },
          onClip: (clip, levelDb) => {
            if (controller.signal.aborted) return;
            if (busy || this.deps.now() < nextRequestAt) {
              pending = { clip, levelDb, capturedAt: this.deps.now() };
              submitPending();
              return;
            }
            submit(clip, levelDb);
          },
        });
        if (controller.signal.aborted) { await capture.stop(); return; }
        this.capture = capture;
        this.update('active');
      } catch (error) {
        if (!controller.signal.aborted) this.fail(explainMicrophoneError(error));
      }
    })();
  }
}
