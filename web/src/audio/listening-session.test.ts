import assert from 'node:assert/strict';
import { test } from 'node:test';
import { ListeningSession, PENDING_CLIP_MAX_AGE_MS } from './listening-session.ts';
import type { CaptureSession } from './recorder.ts';
import type { DetectResponse } from '../api/types.ts';
import { ApiRequestError } from '../api/errors.ts';
const flush = () => new Promise<void>(resolve => setImmediate(resolve));
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
const result: DetectResponse = { event_id: 'evt_live', kind: 'builtin', label: 'Dog bark', sound_id: 'builtin_dog_bark', confidence: .9, description: null, latency_ms: 1 };
function setup() {
  let opens = 0, closes = 0, time = 0, calls = 0;
  const levels: number[] = [];
  const timers: { at: number; callback: () => void; cancelled: boolean }[] = [];
  let callbacks!: Parameters<ConstructorParameters<typeof ListeningSession>[0]['open']>[0];
  const results: DetectResponse[] = [];
  let open: () => Promise<CaptureSession> = async () => ({ sampleRate: 16000, stop: async () => { closes++; } });
  let detect: (clip: Blob, levelDb: number) => Promise<DetectResponse> = async () => result;
  const session = new ListeningSession({
    open: async options => { callbacks = options; opens++; return open(); },
    detect: async (clip, levelDb) => { calls++; levels.push(levelDb); return detect(clip, levelDb); },
    onDetection: event => results.push(event), now: () => time,
    schedule: (callback, delayMs) => {
      const timer = { at: time + delayMs, callback, cancelled: false };
      timers.push(timer);
      return () => { timer.cancelled = true; };
    },
  });
  const setTime = (value: number) => {
    time = value;
    let due: typeof timers;
    do {
      due = timers.filter(timer => !timer.cancelled && timer.at <= time);
      due.forEach(timer => { timer.cancelled = true; timer.callback(); });
    } while (due.length > 0);
  };
  return { session, results, levels, counts: () => ({ opens, closes, calls }), clip: (levelDb = -10) => callbacks.onClip(new Blob(), levelDb), error: () => callbacks.onError(new Error('Audio capture was suspended.')), time: setTime, open: (fn: typeof open) => { open = fn; }, detect: (fn: typeof detect) => { detect = fn; } };
}

test('OFF initially; repeated starts and page subscribers share one stream; stop fully releases', async () => {
  const h = setup();
  assert.equal(h.session.getSnapshot().status, 'paused');
  assert.equal(h.counts().opens, 0);
  h.session.start(); h.session.start(); await flush();
  const unsubscribe = h.session.subscribe(() => {}); unsubscribe();
  const pageTwo = h.session.subscribe(() => {});
  assert.equal(h.session.getSnapshot().status, 'active');
  h.clip(); await flush();
  assert.equal(h.results.length, 1);
  assert.equal(h.counts().opens, 1);
  pageTwo(); await h.session.stop();
  assert.equal(h.counts().closes, 1);
  assert.equal(new ListeningSession({ open: async () => { throw Error(); }, detect: async () => result, onDetection: () => {}, now: () => 0 }).getSnapshot().status, 'paused');
});

test('one request stays in flight, the newest fresh clip waits, and Stop discards it', async () => {
  const h = setup(), pending = deferred<DetectResponse>();
  h.detect(() => pending.promise);
  h.session.start(); await flush(); h.clip(-10); h.clip(-20);
  h.time(2000); h.clip(-30);
  assert.equal(h.counts().calls, 1);
  await h.session.stop(); pending.resolve(result); await flush();
  assert.equal(h.results.length, 0);
  assert.equal(h.counts().calls, 1);
  h.detect(async () => result); h.session.start(); await flush(); h.clip(); await flush();
  assert.equal(h.counts().calls, 2);
  assert.equal(h.results.length, 1);
  await h.session.stop();
});

test('only the newest pending clip follows an active request without exceeding the cap', async () => {
  const h = setup(), first = deferred<DetectResponse>();
  let request = 0;
  h.detect(async () => request++ === 0 ? first.promise : result);
  h.session.start(); await flush();
  h.clip(-10); h.clip(-20); h.clip(-30);
  assert.equal(h.counts().calls, 1);
  h.time(1000); first.resolve(result); await flush();
  assert.equal(h.counts().calls, 2);
  assert.deepEqual(h.levels, [-10, -30]);
  assert.equal(h.results.length, 2);
  await h.session.stop();
});

test('a pending clip expires instead of being submitted after a slow request', async () => {
  const h = setup(), first = deferred<DetectResponse>();
  h.detect(() => first.promise);
  h.session.start(); await flush(); h.clip(); h.clip(-20);
  h.time(PENDING_CLIP_MAX_AGE_MS); first.resolve(result); await flush();
  assert.equal(h.counts().calls, 1);
  assert.equal(h.results.length, 1);
  await h.session.stop();
});

test('stop/restart waits for late microphone permission and teardown without overlapping capture', async () => {
  const h = setup(), permission = deferred<CaptureSession>(), closed = deferred<void>();
  h.open(() => permission.promise);
  h.session.start(); await flush();
  void h.session.stop(); h.session.start(); await flush();
  assert.equal(h.counts().opens, 1);
  permission.resolve({ sampleRate: 16000, stop: () => closed.promise }); await flush();
  assert.equal(h.counts().opens, 1);
  h.open(async () => ({ sampleRate: 16000, stop: async () => {} }));
  closed.resolve(); await flush();
  assert.equal(h.counts().opens, 2);
  assert.equal(h.session.getSnapshot().status, 'active'); await h.session.stop();
});

test('Teach pauses enabled listening; leaving waits for recording release then resumes once', async () => {
  const h = setup(), recording = deferred<string>();
  h.session.start(); await flush();
  let entered = false;
  const task = h.session.record(async () => { entered = true; assert.equal(h.counts().closes, 1); return recording.promise; });
  await flush(); assert.equal(entered, true);
  assert.equal(h.session.getSnapshot().status, 'teaching');
  void h.session.setTeaching(false); await flush();
  assert.equal(h.counts().opens, 1);
  recording.resolve('valid wav'); assert.equal(await task, 'valid wav'); await flush();
  assert.equal(h.counts().opens, 2); assert.equal(h.session.getSnapshot().status, 'active');
  await h.session.stop();
});

test('Teach discards pending detection and does not enable listening when originally OFF or stopped', async () => {
  const h = setup(), pending = deferred<DetectResponse>();
  await h.session.record(async () => 'clip'); await h.session.setTeaching(false);
  assert.equal(h.counts().opens, 0);
  h.session.start(); await flush(); h.detect(() => pending.promise); h.clip(); h.clip(-20);
  await h.session.setTeaching(true); pending.resolve(result); await flush();
  assert.equal(h.results.length, 0);
  assert.equal(h.counts().calls, 1);
  await h.session.stop(); await h.session.setTeaching(false); await flush();
  assert.equal(h.counts().opens, 1); assert.equal(h.session.getSnapshot().status, 'paused');
});

test('microphone/browser interruption stops the global state, retains error, and needs explicit restart', async () => {
  const h = setup(); h.session.start(); await flush(); h.error(); await flush();
  assert.equal(h.session.getSnapshot().status, 'paused');
  assert.match(h.session.getSnapshot().error!, /suspended/);
  await h.session.setTeaching(false); assert.equal(h.counts().opens, 1);
  h.session.start(); await flush(); assert.equal(h.counts().opens, 2); await h.session.stop();
});

test('permanent API failures stop; transient failures respect retry delay and recover', async () => {
  const h = setup(); h.session.start(); await flush();
  h.detect(async () => { throw new ApiRequestError('Temporarily unavailable', 5000, 503); });
  h.clip(); await flush(); assert.match(h.session.getSnapshot().error!, /Waiting/);
  h.time(4999); h.clip(); assert.equal(h.counts().calls, 1);
  h.detect(async () => result); h.time(5000); await flush(); assert.equal(h.results.length, 1);
  assert.equal(h.session.getSnapshot().error, null);
  h.time(6000); h.detect(async () => { throw new ApiRequestError('Gemini request failed.', 0, 502); });
  h.clip(); await flush(); assert.equal(h.session.getSnapshot().status, 'paused');
  assert.equal(h.counts().closes, 1);
});


test('preview playback pauses detection independently of recording and never enables an OFF session', async () => {
  const h = setup();
  h.session.setPreviewing(true); h.session.setPreviewing(false); await flush();
  assert.equal(h.counts().opens, 0);
  h.session.start(); await flush();
  h.session.setPreviewing(true); await flush();
  assert.equal(h.counts().closes, 1);
  await h.session.setTeaching(true); h.session.setPreviewing(false); await flush();
  assert.equal(h.counts().opens, 1);
  await h.session.setTeaching(false); await flush();
  assert.equal(h.counts().opens, 2);
  h.session.setPreviewing(true); await h.session.stop(); h.session.setPreviewing(false); await flush();
  assert.equal(h.counts().opens, 2);
});

test('preview and microphone interruption clear a queued clip', async () => {
  for (const suspend of ['preview', 'interruption'] as const) {
    const h = setup(), pending = deferred<DetectResponse>();
    h.detect(() => pending.promise); h.session.start(); await flush();
    h.clip(); h.clip(-20);
    if (suspend === 'preview') h.session.setPreviewing(true);
    else h.error();
    await flush(); pending.resolve(result); await flush();
    assert.equal(h.counts().calls, 1, suspend);
    assert.equal(h.results.length, 0, suspend);
    await h.session.stop();
  }
});
