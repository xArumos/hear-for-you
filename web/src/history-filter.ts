export interface HistoryFilterEvent {
  at: string;
  label: string | null;
}

export interface HistoryFilters {
  startDate: string;
  endDate: string;
  sound: string;
}

const DATE_INPUT = /^(\d{4})-(\d{2})-(\d{2})$/;

export function isValidDateInput(value: string): boolean {
  if (!value) return true;
  const match = DATE_INPUT.exec(value);
  if (!match) return false;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(year, month - 1, day);
  return date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day;
}

export function localDateKey(timestamp: string): string | null {
  const date = new Date(timestamp);
  if (!Number.isFinite(date.getTime())) return null;
  const year = String(date.getFullYear()).padStart(4, '0');
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function historyRangeError(startDate: string, endDate: string): string | null {
  if (!isValidDateInput(startDate) || !isValidDateInput(endDate)) return 'Enter valid start and end dates.';
  if (startDate && endDate && endDate < startDate) return 'End date must be on or after start date.';
  return null;
}

export function filterHistoryEvents<T extends HistoryFilterEvent>(
  events: readonly T[], filters: HistoryFilters,
): T[] {
  if (historyRangeError(filters.startDate, filters.endDate)) return [];
  return events.filter(event => {
    if (filters.sound !== 'All' && event.label !== filters.sound) return false;
    if (!filters.startDate && !filters.endDate) return true;
    const date = localDateKey(event.at);
    if (!date) return false;
    return (!filters.startDate || date >= filters.startDate) && (!filters.endDate || date <= filters.endDate);
  });
}
