import assert from 'node:assert/strict';
import { test } from 'node:test';
import { SoundGate } from './listener.ts';
import { validateWavFile } from './wav.ts';

test('gate waits for a real onset and returns exact pre/post audio with peak dBFS', async () => {
  const gate = new SoundGate();
  for (let i = 0; i < 110; i++) assert.equal(gate.push(new Float32Array(1600).fill(0.001)), null);
  let result = gate.push(new Float32Array(1600).fill(0.5));
  for (let i = 0; i < 24 && !result; i++) result = gate.push(new Float32Array(1600).fill(0.5));
  assert.ok(result);
  assert.equal(await validateWavFile(result.clip, 48000), true);
  assert.ok(Math.abs(result.levelDb - -6.0206) < 0.001);
  const view = new DataView(await result.clip.arrayBuffer());
  assert.ok(view.getInt16(44, true) < 100);
  assert.ok(view.getInt16(44 + 8000 * 2, true) > 10000);
});

test('steady quiet or loud input does not fabricate detections', () => {
  for (const amplitude of [0, 0.1, 0.8]) {
    const gate = new SoundGate();
    for (let i = 0; i < 200; i++) assert.equal(gate.push(new Float32Array(1600).fill(amplitude)), null);
  }
});
