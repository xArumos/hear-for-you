import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

import { explainMicrophoneError, recordMicrophoneClip } from './recorder.ts';

describe('Microphone permission diagnostics', () => {
  test('maps browser permission errors to clear messages', () => {
    const denied = new DOMException('Permission denied', 'NotAllowedError');
    assert.match(explainMicrophoneError(denied), /permission/i);

    const missing = new DOMException('Device not found', 'NotFoundError');
    assert.match(explainMicrophoneError(missing), /microphone/i);

    const unsupported = new Error('AudioCapture not supported');
    assert.match(explainMicrophoneError(unsupported), /support|available/i);
  });

  test('calls getUserMedia and returns a valid WAV blob when mic input is present', async () => {
    const calls: string[] = [];
    const track = { readyState: 'live', stop() {}, addEventListener() {}, removeEventListener() {} };
    const stream = {
      getTracks: () => [track],
      getAudioTracks: () => [track],
    };

    class FakeAudioWorkletNode {
      port = { onmessage: null as ((event: MessageEvent<Float32Array>) => void) | null };
      connect() {}
      disconnect() {}
    }

    class FakeAudioContext {
      addEventListener() {}
      removeEventListener() {}
      static instances = 0;
      state = 'running';
      sampleRate = 48000;
      destination = {};
      audioWorklet = {
        addModule: async () => {},
      };
      createMediaStreamSource() {
        return {
          connect: (node: FakeAudioWorkletNode) => {
            setTimeout(() => {
              const samples = new Float32Array(4800);
              for (let index = 0; index < samples.length; index += 1) {
                samples[index] = Math.sin((index / 100) * 2 * Math.PI) * 0.2;
              }
              node.port.onmessage?.({ data: samples } as MessageEvent<Float32Array>);
            }, 0);
          },
          disconnect: () => {},
        };
      }
      resume() { return Promise.resolve(); }
      close() { return Promise.resolve(); }
    }

    const originalMediaDevices = globalThis.navigator?.mediaDevices;
    const originalWindow = globalThis.window;
    const originalAudioContext = globalThis.AudioContext;
    const originalAudioWorkletNode = globalThis.AudioWorkletNode;
    const originalIsSecureContext = globalThis.window?.isSecureContext;

    Object.defineProperty(globalThis, 'navigator', {
      value: {
        mediaDevices: {
          async getUserMedia() {
            calls.push('getUserMedia');
            return stream;
          },
        },
      },
      configurable: true,
    });

    Object.defineProperty(globalThis, 'window', {
      value: {
        isSecureContext: true,
        location: { hostname: 'localhost' },
        addEventListener() {},
        removeEventListener() {},
        setTimeout,
        clearTimeout,
      },
      configurable: true,
    });

    // @ts-expect-error test stub
    globalThis.AudioContext = FakeAudioContext;
    // @ts-expect-error test stub
    globalThis.AudioWorkletNode = FakeAudioWorkletNode;

    try {
      const wav = await recordMicrophoneClip(10);
      assert.equal(calls[0], 'getUserMedia');
      assert.equal(wav.type, 'audio/wav');
      const header = new Uint8Array(await wav.arrayBuffer()).subarray(0, 12);
      assert.equal(String.fromCharCode(...header.slice(0, 4)), 'RIFF');
      assert.equal(String.fromCharCode(...header.slice(8, 12)), 'WAVE');
    } finally {
      if (originalMediaDevices) {
        Object.defineProperty(globalThis, 'navigator', { value: { mediaDevices: originalMediaDevices }, configurable: true });
      } else {
        delete (globalThis as { navigator?: Navigator }).navigator;
      }

      if (originalWindow) {
        Object.defineProperty(globalThis, 'window', { value: originalWindow, configurable: true });
      } else {
        delete (globalThis as { window?: Window }).window;
      }

      if (originalAudioContext) {
        // @ts-expect-error test stub
        globalThis.AudioContext = originalAudioContext;
      } else {
        delete (globalThis as { AudioContext?: typeof AudioContext }).AudioContext;
      }

      if (originalAudioWorkletNode) {
        // @ts-expect-error test stub
        globalThis.AudioWorkletNode = originalAudioWorkletNode;
      } else {
        delete (globalThis as { AudioWorkletNode?: typeof AudioWorkletNode }).AudioWorkletNode;
      }

      if (originalIsSecureContext !== undefined) {
        Object.defineProperty(globalThis.window, 'isSecureContext', { value: originalIsSecureContext, configurable: true });
      }
    }
  });
});

 test('non-permission failures retain their cause', () => {
  for (const name of ['NotFoundError', 'NotReadableError', 'AbortError', 'OverconstrainedError', 'SecurityError']) {
    assert.doesNotMatch(explainMicrophoneError(new DOMException('test', name)), /permission was denied/);
  }
  assert.equal(explainMicrophoneError(new Error('Invalid WAV duration')), 'Invalid WAV duration');
});
