import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { filterHistoryEvents, historyRangeError, localDateKey } from './history-filter.ts';

interface Event {
  id: string;
  at: string;
  label: string | null;
}

const localIso = (year: number, month: number, day: number, hour = 12, minute = 0, second = 0, millisecond = 0): string =>
  new Date(year, month - 1, day, hour, minute, second, millisecond).toISOString();
const event = (id: string, year: number, month: number, day: number, label = 'Door knock', hour = 12): Event =>
  ({ id, label, at: localIso(year, month, day, hour) });
const filter = (events: Event[], startDate = '', endDate = '', sound = 'All'): Event[] =>
  filterHistoryEvents(events, { startDate, endDate, sound });

test('single-day and inclusive multi-day ranges use local calendar dates', () => {
  const events = [event('before', 2026, 10, 19), event('20', 2026, 10, 20), event('22', 2026, 10, 22), event('24', 2026, 10, 24), event('25', 2026, 10, 25), event('after', 2026, 10, 26)];
  assert.deepEqual(filter(events, '2026-10-24', '2026-10-24').map(item => item.id), ['24']);
  assert.deepEqual(filter(events, '2026-10-20', '2026-10-25').map(item => item.id), ['20', '22', '24', '25']);
});

test('ranges cross month and year boundaries without changing event order', () => {
  const events = [event('dec30', 2025, 12, 30), event('dec31', 2025, 12, 31), event('jan1', 2026, 1, 1), event('feb1', 2026, 2, 1)];
  assert.deepEqual(filter(events, '2025-12-31', '2026-01-01').map(item => item.id), ['dec31', 'jan1']);
  assert.deepEqual(filter(events, '2026-01-01', '2026-02-01').map(item => item.id), ['jan1', 'feb1']);
});

test('start and end day boundaries are inclusive', () => {
  const events: Event[] = [
    { id: 'start', label: 'Door knock', at: localIso(2026, 10, 24, 0, 0, 0, 0) },
    { id: 'end', label: 'Door knock', at: localIso(2026, 10, 24, 23, 59, 59, 999) },
    { id: 'next', label: 'Door knock', at: localIso(2026, 10, 25, 0, 0, 0, 0) },
  ];
  assert.deepEqual(filter(events, '2026-10-24', '2026-10-24').map(item => item.id), ['start', 'end']);
});

test('local date extraction remains stable on daylight-saving transition days', () => {
  for (const [year, month, day] of [[2026, 3, 8], [2026, 11, 1]] as const) {
    const timestamp = localIso(year, month, day, 12);
    const expected = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    assert.equal(localDateKey(timestamp), expected);
    assert.equal(filter([{ id: expected, label: 'Siren', at: timestamp }], expected, expected).length, 1);
  }
});

test('open-ended, cleared, invalid and empty ranges have defined behavior', () => {
  const events = [event('20', 2026, 10, 20), event('24', 2026, 10, 24), event('25', 2026, 10, 25)];
  assert.deepEqual(filter(events, '2026-10-24').map(item => item.id), ['24', '25']);
  assert.deepEqual(filter(events, '', '2026-10-24').map(item => item.id), ['20', '24']);
  assert.deepEqual(filter(events).map(item => item.id), ['20', '24', '25']);
  assert.equal(historyRangeError('2026-10-25', '2026-10-24'), 'End date must be on or after start date.');
  assert.deepEqual(filter(events, '2026-10-25', '2026-10-24'), []);
  assert.deepEqual(filter(events, '2027-01-01', '2027-01-02'), []);
});

test('sound filtering composes with the date range and restored stored events', () => {
  const stored = JSON.stringify([event('dog', 2026, 10, 24, 'Dog bark'), event('knock', 2026, 10, 24), event('old-dog', 2026, 10, 20, 'Dog bark')]);
  const restored = JSON.parse(stored) as Event[];
  assert.deepEqual(filter(restored, '2026-10-23', '2026-10-25', 'Dog bark').map(item => item.id), ['dog']);
});

test('History source has no visible storage-status wording', () => {
  const source = readFileSync(new URL('./App.tsx', import.meta.url), 'utf8');
  assert.doesNotMatch(source, /stored locally/i);
  assert.match(source, /readStoredValue<GuestHistoryEvent\[]>\(STORAGE_KEYS\.history/);
  assert.match(source, /writeStoredValue\(STORAGE_KEYS\.history, history\)/);
});
