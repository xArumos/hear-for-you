import assert from 'node:assert/strict';
import { test } from 'node:test';
import { AlertPolicy, ONGOING_EVENT_GAP_MS } from './alert-policy.ts';
import { DEFAULT_BUILTIN_SOUNDS } from './teach-state.ts';
import type { DetectResponse } from './api/types.ts';
const sounds = [...DEFAULT_BUILTIN_SOUNDS, { sound_id: 'snd_voice', name: 'My voice cue', icon: 'voice', kind: 'taught' as const, enabled: true }];
function event(overrides: Partial<DetectResponse> = {}): DetectResponse {
  return { event_id: 'evt_test', kind: 'builtin', label: 'Dog bark', sound_id: 'builtin_dog_bark', confidence: 0.9, description: null, latency_ms: 1, ...overrides };
}
function unknown(description: string | null): DetectResponse {
  return event({ kind: 'unknown', label: null, sound_id: null, confidence: null, description });
}
test('complete speech and background-only descriptions do not alert by default', () => {
  for (const text of ['Someone is speaking.', 'People are talking.', 'Normal conversation.', 'Keyboard typing.', 'Typing on a keyboard.', 'A laptop being tapped.', 'Mouse clicking.', 'Footsteps.', 'Fan noise.', 'Household background noise.'])
    assert.equal(new AlertPolicy().accept(unknown(text), sounds, 0), false, text);
});
test('amplitude-only fallback does not automatically turn typing or tapping into alerts', () => {
  for (const text of [null, '', '   ', 'Loud noise detected.', 'A loud sound was detected.'])
    assert.equal(new AlertPolicy().accept(unknown(text), sounds, 0), false);
});
test('mixed events and meaningful unknown descriptions remain eligible without fabricated confidence', () => {
  for (const text of ['A smoke alarm beeps while someone is speaking.', 'Glass breaks near a keyboard.', 'A microwave beeps.', 'A doorbell rings.', 'A loud bang from an unidentified source.'])
    assert.equal(new AlertPolicy().accept(unknown(text), sounds, 0), true, text);
});
test('invalid and below-backend-threshold scores fail; existing matched targets and taught scores pass', () => {
  for (const confidence of [null, NaN, Infinity, -0.1, 0.59, 1.1])
    assert.equal(new AlertPolicy().accept(event({ confidence }), sounds, 0), false);
  assert.equal(new AlertPolicy().accept(event({ confidence: 0.61 }), sounds, 0), true);
  assert.equal(new AlertPolicy().accept(event({ kind: 'taught', sound_id: 'snd_voice', confidence: 0.5 }), sounds, 0), true);
  assert.equal(new AlertPolicy().accept(event({ kind: 'taught', sound_id: 'snd_voice', confidence: 0.49 }), sounds, 0), false);
});
test('backend-admitted built-ins survive confidence rounding at the cutoff', () => {
  for (const sound_id of ['builtin_door_knock', 'builtin_dog_bark', 'builtin_glass_breaking']) {
    // Mirrors detectors.detect: a valid raw probability > 0.6 rounds to 0.60.
    const confidence = Math.round(0.604 * 100) / 100;
    assert.equal(new AlertPolicy().accept(event({ sound_id, confidence }), sounds, 0), true);
    assert.equal(new AlertPolicy().accept(event({ sound_id, confidence }), sounds.map(sound => ({ ...sound, enabled: false })), 0), false);
  }
});
test('sustained events alert immediately, group continued observations, and rearm after a gap', () => {
  const policy = new AlertPolicy();
  assert.equal(policy.accept(event(), sounds, 0), true);
  assert.equal(policy.accept(event({ event_id: 'evt_2' }), sounds, 4000), false);
  assert.equal(policy.accept(event({ event_id: 'evt_3' }), sounds, 11000), false);
  assert.equal(policy.accept(event({ event_id: 'evt_new' }), sounds, 11000 + ONGOING_EVENT_GAP_MS), true);
});
test('single glass breaks, smoke alarms, knocks and custom cues need no repetition', () => {
  const policy = new AlertPolicy();
  for (const sound_id of ['builtin_glass_breaking', 'builtin_smoke_alarm', 'builtin_door_knock', 'snd_voice'])
    for (let i = 0; i < 2; i++)
      assert.equal(policy.accept(event({ event_id: `${sound_id}_${i}`, sound_id, kind: sound_id === 'snd_voice' ? 'taught' : 'builtin' }), sounds, i), true);
});
test('disabled categories remain visible, suppressed, and eligible on re-enable', () => {
  const policy = new AlertPolicy();
  const disabled = sounds.map(sound => ({ ...sound, enabled: false }));
  assert.equal(disabled.length, sounds.length);
  assert.equal(policy.accept(event(), disabled, 0), false);
  assert.equal(policy.accept(event(), sounds, 1), true);
  assert.equal(policy.accept(event({ sound_id: 'missing' }), sounds, 2), false);
});
test('one admission decision produces the same alert and local History IDs, without duplicates', () => {
  const policy = new AlertPolicy();
  const alerts: string[] = [], history: string[] = [];
  for (const result of [unknown('Someone is speaking.'), unknown(null), event(), event(), event({ event_id: 'evt_continued' }), event({ event_id: 'evt_glass', sound_id: 'builtin_glass_breaking' })])
    if (policy.accept(result, sounds, 0)) { alerts.push(result.event_id); history.push(result.event_id); }
  assert.deepEqual(alerts, ['evt_test', 'evt_glass']);
  assert.deepEqual(history, alerts);
});
