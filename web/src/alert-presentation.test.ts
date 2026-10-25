import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { alertPresentation } from './alert-presentation.ts';
import type { DetectResponse } from './api/types.ts';
import { DEFAULT_BUILTIN_SOUNDS, type GuestSound } from './teach-state.ts';

const event = (overrides: Partial<DetectResponse>): DetectResponse => ({
  event_id: 'evt_test',
  kind: 'builtin',
  label: 'Dog bark',
  sound_id: 'builtin_dog_bark',
  confidence: 0.9,
  description: null,
  latency_ms: 1,
  ...overrides,
});

test('a taught alert reuses its selected custom icon and pink presentation', () => {
  const sounds: GuestSound[] = [
    ...DEFAULT_BUILTIN_SOUNDS,
    { sound_id: 'snd_lilis_voice', name: "Lili's voice", icon: 'voice', kind: 'taught', enabled: true },
  ];

  assert.deepEqual(alertPresentation(event({
    kind: 'taught', label: "Lili's voice", sound_id: 'snd_lilis_voice', confidence: 0.75,
  }), sounds), { className: 'taught', icon: 'voice' });

  const styles = readFileSync(new URL('./index.css', import.meta.url), 'utf8');
  assert.match(styles, /\.alert-screen\.taught\{background:var\(--light-violet\);color:var\(--dark-blue\)\}/);
});

test('built-in and unknown alerts keep their existing presentations', () => {
  assert.deepEqual(alertPresentation(event({}), DEFAULT_BUILTIN_SOUNDS), { className: 'recognized', icon: 'dog' });
  assert.deepEqual(alertPresentation(event({
    kind: 'unknown', label: null, sound_id: null, confidence: null, description: 'A sound.',
  }), DEFAULT_BUILTIN_SOUNDS), { className: 'unknown', icon: 'generic' });
});

test('missing custom metadata uses the generic icon without inventing a mapping', () => {
  assert.deepEqual(alertPresentation(event({
    kind: 'taught', label: 'Old sound', sound_id: 'snd_missing', confidence: 0.7,
  }), DEFAULT_BUILTIN_SOUNDS), { className: 'taught', icon: 'generic' });
});
