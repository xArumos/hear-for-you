import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

import { encodeWav } from './audio/wav.ts';
import { countCompletedRecordings, isReadyToSave } from './teach-state.ts';

describe('Teach state logic', () => {
  test('requires a valid name and all four recordings before enabling save', () => {
    const recordings = [
      { blob: new Blob(['ok'], { type: 'audio/wav' }), valid: true },
      { blob: new Blob(['ok'], { type: 'audio/wav' }), valid: true },
      { blob: new Blob(['ok'], { type: 'audio/wav' }), valid: true },
      { blob: new Blob(['ok'], { type: 'audio/wav' }), valid: true },
    ];

    assert.equal(isReadyToSave('Door knock', recordings), true);
    assert.equal(isReadyToSave('   ', recordings), false);
    assert.equal(isReadyToSave('Door knock', recordings.slice(0, 3)), false);
    assert.equal(countCompletedRecordings(recordings), 4);
  });
});

describe('WAV encoder', () => {
  test('creates a valid 16 kHz mono PCM WAV blob for a non-silent signal', async () => {
    const samples = new Float32Array(48000);
    for (let index = 0; index < samples.length; index += 1) {
      samples[index] = 0.2 * Math.sin((2 * Math.PI * 440 * index) / 16000);
    }

    const blob = encodeWav(samples, 16000);
    assert.equal(blob.type, 'audio/wav');

    const bytes = new Uint8Array(await blob.arrayBuffer());
    assert.equal(String.fromCharCode(...bytes.slice(0, 4)), 'RIFF');
    assert.equal(String.fromCharCode(...bytes.slice(8, 12)), 'WAVE');
    assert.equal(String.fromCharCode(...bytes.slice(12, 16)), 'fmt ');
    assert.equal(String.fromCharCode(...bytes.slice(36, 40)), 'data');

    const sampleCount = new DataView(bytes.buffer).getUint32(40, true);
    assert.equal(sampleCount, 48000 * 2);

    let peak = 0;
    for (let index = 44; index < bytes.length; index += 2) {
      const sample = new DataView(bytes.buffer).getInt16(index, true);
      peak = Math.max(peak, Math.abs(sample));
    }

    assert.ok(peak > 1000, 'encoded signal should contain non-zero sample data');
  });
});
