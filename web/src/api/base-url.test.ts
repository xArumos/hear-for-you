import assert from 'node:assert/strict';
import { test } from 'node:test';
import { apiUrl } from './base-url.ts';
test('website keeps same-origin API by default; native requires an explicit reachable backend', () => {
  assert.equal(apiUrl('/detect', undefined, false), '/api/detect');
  assert.throws(() => apiUrl('/detect', undefined, true), /reachable HTTPS/);
});
test('HTTPS native endpoint preserves API paths and queries', () => {
  assert.equal(apiUrl('/history?limit=10', 'https://backend.example/', true), 'https://backend.example/api/history?limit=10');
});
test('unsafe or ambiguous endpoint configurations are rejected', () => {
  for (const origin of ['http://backend.example', 'https://localhost', 'https://127.0.0.1', 'https://[::1]', 'https://key@backend.example', 'https://backend.example/api', 'https://backend.example/?key=x', 'https://backend.example/#x']) {
    assert.throws(() => apiUrl('/teach', origin, true), undefined, origin);
  }
  assert.throws(() => apiUrl('//other.example', 'https://backend.example', true));
});
