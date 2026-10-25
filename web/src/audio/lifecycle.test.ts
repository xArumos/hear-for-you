import assert from 'node:assert/strict';
import { test } from 'node:test';
import { openMicrophone, recordMicrophoneClip } from './recorder.ts';
import { validateWavFile } from './wav.ts';

test('independent sessions release tracks on completion, initialization errors, cancellation and device loss', async () => {
  const events = new EventTarget();
  const descriptors = Object.getOwnPropertyDescriptors(globalThis);
  let acquired = 0, stopped = 0, closed = 0;
  let failure: Error | undefined;
  let initializationFailure = false, ended = false, silent = false, delayGrant = false;
  let grant: (() => void) | undefined;
  let trackEnded: (() => void) | undefined;
  class Worklet {
    port: { onmessage: ((event: { data: Float32Array }) => void) | null } = { onmessage: null };
    connect() {} disconnect() {}
  }
  class Context {
    addEventListener() {}
    removeEventListener() {}
    state = 'suspended'; sampleRate = 44100; destination = {};
    audioWorklet = { addModule: async () => { if (initializationFailure) throw new Error('Worklet initialization failed'); } };
    async resume() { this.state = 'running'; }
    async close() { closed++; this.state = 'closed'; }
    createMediaStreamSource() { return { disconnect() {}, connect(node: Worklet) { setTimeout(() => {
      node.port.onmessage?.({ data: new Float32Array(44100 * 10).fill(silent ? 0 : 0.2) });
    }, 0); } }; }
  }
  Object.defineProperties(globalThis, {
    window: { value: { isSecureContext: true, addEventListener: events.addEventListener.bind(events), removeEventListener: events.removeEventListener.bind(events) }, configurable: true },
    navigator: { value: { mediaDevices: { async getUserMedia() {
      acquired++;
      if (failure) throw failure;
      if (delayGrant) await new Promise<void>(resolve => { grant = resolve; });
      const track = { readyState: ended ? 'ended' : 'live', stop() { stopped++; },
        addEventListener(_type: string, callback: () => void) { trackEnded = callback; }, removeEventListener() {} };
      return { getTracks: () => [track], getAudioTracks: () => [track] };
    } } }, configurable: true },
    AudioContext: { value: Context, configurable: true },
    AudioWorkletNode: { value: Worklet, configurable: true },
  });
  try {
    for (const duration of [3000, 3000, 3000, 10000]) {
      assert.equal(await validateWavFile(await recordMicrophoneClip(duration), duration * 16), true);
    }
    assert.equal(acquired, 4); assert.equal(stopped, 4); assert.equal(closed, 4);
    silent = true;
    await assert.rejects(recordMicrophoneClip(), /No usable sound/);
    assert.equal(await validateWavFile(await recordMicrophoneClip(10000, { allowSilence: true }), 160000), true);
    silent = false; initializationFailure = true;
    await assert.rejects(recordMicrophoneClip(), /Worklet initialization failed/);
    initializationFailure = false; ended = true;
    await assert.rejects(recordMicrophoneClip(), /stream has ended/);
    ended = false;
    for (const name of ['NotAllowedError', 'NotFoundError', 'NotReadableError', 'OverconstrainedError', 'SecurityError']) {
      failure = new DOMException('test', name);
      await assert.rejects(recordMicrophoneClip(), error => error === failure);
    }
    failure = undefined; delayGrant = true;
    const controller = new AbortController();
    const recording = recordMicrophoneClip(3000, { signal: controller.signal });
    controller.abort(); grant?.();
    await assert.rejects(recording, { name: 'AbortError' });
    assert.equal(stopped, 9); assert.equal(closed, 7);
    delayGrant = false;
    let deviceError: Error | undefined;
    const session = await openMicrophone(() => {}, { onError: error => { deviceError = error; } });
    trackEnded?.();
    assert.match(deviceError?.message ?? '', /disconnected/);
    await session.stop(); await session.stop();
    assert.equal(stopped, 10); assert.equal(closed, 8);
    const active = await openMicrophone(() => {}, { onError: error => { deviceError = error; } });
    events.dispatchEvent(new Event('hear-for-you-native-inactive'));
    assert.match(deviceError?.message ?? '', /backgrounded/);
    await active.stop();
    assert.equal(stopped, 11); assert.equal(closed, 9);
    delayGrant = true;
    const pending = openMicrophone(() => {}, { onError: () => {} });
    events.dispatchEvent(new Event('hear-for-you-native-inactive'));
    grant?.();
    await assert.rejects(pending, { name: 'AbortError' });
    assert.equal(stopped, 12); // late native permission grant must not leak its track

  } finally {
    for (const key of ['window', 'navigator', 'AudioContext', 'AudioWorkletNode']) {
      if (descriptors[key]) Object.defineProperty(globalThis, key, descriptors[key]);
      else Reflect.deleteProperty(globalThis, key);
    }
  }
});
