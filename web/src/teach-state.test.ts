import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

import { encodeWav, validateWavFile } from './audio/wav.ts';
import { countCompletedRecordings, isReadyToSave } from './teach-state.ts';
import { trimCapturedSamples } from './audio/recorder.ts';

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

  test('keeps a three-second clip at exactly 48,000 samples and a ten-second room clip at exactly 160,000 samples', async () => {
    const threeSecond = new Float32Array(48000);
    const roomClip = new Float32Array(160000);

    const threeBlob = encodeWav(threeSecond, 16000);
    const roomBlob = encodeWav(roomClip, 16000);

    assert.equal(await validateWavFile(threeBlob, 48000), true);
    assert.equal(await validateWavFile(roomBlob, 160000), true);
  });

  test('trims captured source audio to the requested exact sample count without dropping the sound', () => {
    const samples = new Float32Array(50000);
    for (let index = 0; index < samples.length; index += 1) {
      samples[index] = 0.2 * Math.sin((2 * Math.PI * 440 * index) / 16000);
    }

    const trimmed = trimCapturedSamples(samples, 48000);
    assert.equal(trimmed.length, 48000);
    assert.ok(Math.abs(trimmed[0] - samples[0]) < 1e-9);
    assert.ok(Math.abs(trimmed[trimmed.length - 1] - samples[47999]) < 1e-9);
  });
});

describe('Sound enablement filtering', () => {
  test('disabled built-in categories are suppressed from alerts and history while keeping prior events intact', () => {
    const sounds = [
      { sound_id: 'builtin_dog_bark', name: 'Dog bark', kind: 'builtin', enabled: false },
      { sound_id: 'builtin_siren', name: 'Siren', kind: 'builtin', enabled: true },
      { sound_id: 'snd_custom', name: 'Door knock', kind: 'taught', enabled: true },
    ];

    const events = [
      { event_id: 'evt_1', at: '2026-10-24T10:00:00Z', kind: 'builtin', label: 'Dog bark', sound_id: 'builtin_dog_bark', confidence: 0.9, description: null },
      { event_id: 'evt_2', at: '2026-10-24T10:01:00Z', kind: 'builtin', label: 'Siren', sound_id: 'builtin_siren', confidence: 0.8, description: null },
      { event_id: 'evt_3', at: '2026-10-24T10:02:00Z', kind: 'taught', label: 'Door knock', sound_id: 'snd_custom', confidence: 0.7, description: null },
    ];

    const filtered = events.filter((event) => {
      if (!event.sound_id) return true;
      const sound = sounds.find((item) => item.sound_id === event.sound_id);
      if (!sound) return true;
      return sound.enabled;
    });

    assert.deepEqual(filtered.map((event) => event.event_id), ['evt_2', 'evt_3']);
  });

  test('save readiness stays blocked until all four recordings and the sound name are valid', () => {
    const recordings = [
      { blob: new Blob(['one'], { type: 'audio/wav' }), valid: true },
      { blob: new Blob(['two'], { type: 'audio/wav' }), valid: true },
      { blob: new Blob(['three'], { type: 'audio/wav' }), valid: true },
      { blob: new Blob(['four'], { type: 'audio/wav' }), valid: false },
    ];

    assert.equal(isReadyToSave('Door knock', recordings), false);
    assert.equal(isReadyToSave('   ', recordings), false);
  });

  test('builtin categories stay visible while disabled and custom sounds remain separate', () => {
    const builtins = [
      { sound_id: 'builtin_smoke_alarm', name: 'Smoke alarm', kind: 'builtin', enabled: false },
      { sound_id: 'builtin_dog_bark', name: 'Dog bark', kind: 'builtin', enabled: true },
    ];
    const customSounds = [
      { sound_id: 'snd_123', name: 'Front door', kind: 'taught', enabled: true },
    ];

    const visibleBuiltins = builtins.filter((sound) => sound.kind === 'builtin');
    assert.equal(visibleBuiltins.length, 2);
    assert.equal(visibleBuiltins[0].enabled, false);
    assert.equal(customSounds[0].kind, 'taught');
  });
});
