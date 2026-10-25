import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const appSource = readFileSync(new URL('./App.tsx', import.meta.url), 'utf8');

test('History removes only the per-row storage label and keeps persistence', () => {
  assert.doesNotMatch(appSource, /stored locally/i);
  assert.match(appSource, /readStoredValue<GuestHistoryEvent\[]>\(STORAGE_KEYS\.history/);
  assert.match(appSource, /writeStoredValue\(STORAGE_KEYS\.history, history\)/);
  assert.match(appSource, /<time>\{new Date\(event\.at\)\.toLocaleString\(\)\}<\/time>/);
  assert.match(appSource, /<strong>\{event\.label \?\? 'Sound detected'\}<\/strong>/);
});
