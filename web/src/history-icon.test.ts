import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { IconKey } from './api/types.ts';
import { filterHistoryEvents } from './history-filter.ts';
import { historyIcon } from './history-icon.ts';
import { DEFAULT_BUILTIN_SOUNDS, type GuestSound } from './teach-state.ts';

test('every built-in History event uses the icon assigned in Your Sounds', () => {
  for (const sound of DEFAULT_BUILTIN_SOUNDS) {
    assert.equal(historyIcon({ sound_id: sound.sound_id }, DEFAULT_BUILTIN_SOUNDS), sound.icon);
  }
});

test('custom and older History events resolve persisted icons by stable sound ID', () => {
  const storedSounds = JSON.stringify([
    { sound_id: 'snd_front_door', name: 'Front door', icon: 'bell', kind: 'taught', enabled: true },
    { sound_id: 'snd_old_kettle', name: 'Old kettle', icon: 'kettle', kind: 'taught', enabled: false },
  ] satisfies GuestSound[]);
  const restoredSounds = JSON.parse(storedSounds) as GuestSound[];

  assert.equal(historyIcon({ sound_id: 'snd_front_door' }, restoredSounds), 'bell');
  assert.equal(historyIcon({ sound_id: 'snd_old_kettle' }, restoredSounds), 'kettle');
});

test('unknown events and missing sound metadata use the generic fallback', () => {
  assert.equal(historyIcon({ sound_id: null }, DEFAULT_BUILTIN_SOUNDS), 'generic');
  assert.equal(historyIcon({ sound_id: 'snd_unavailable' }, DEFAULT_BUILTIN_SOUNDS), 'generic');
});

test('icon lookup does not change combined date and sound filtering', () => {
  const events = [
    { id: 'dog', at: new Date(2026, 9, 24, 12).toISOString(), label: 'Dog bark', sound_id: 'builtin_dog_bark' },
    { id: 'siren', at: new Date(2026, 9, 25, 12).toISOString(), label: 'Siren', sound_id: 'builtin_siren' },
  ];
  const filtered = filterHistoryEvents(events, { startDate: '2026-10-24', endDate: '2026-10-24', sound: 'Dog bark' });

  assert.deepEqual(filtered.map(event => event.id), ['dog']);
  assert.equal(historyIcon(filtered[0], DEFAULT_BUILTIN_SOUNDS), 'dog' satisfies IconKey);
});
