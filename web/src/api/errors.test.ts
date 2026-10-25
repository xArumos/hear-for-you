import assert from 'node:assert/strict';
import { test } from 'node:test';
import { ApiRequestError, DetectionRetryBudget } from './errors.ts';

test('preserves HTTP status, contract code and server retry delay', () => {
  const error = new ApiRequestError('Busy', 7000, 429, 'rate_limited');
  assert.equal(error.status, 429); assert.equal(error.code, 'rate_limited');
  assert.deepEqual(new DetectionRetryBudget().failure(error), { stop: false, delayMs: 7000 });
});

test('authentication, invalid models, quota and opaque nonretryable Gemini failures stop immediately', () => {
  for (const [status, message] of [[401,'Unauthorized'],[403,'Forbidden'],[404,'Model not found'],[429,'Quota exhausted'],[502,'Gemini request failed.'],[502,'API key invalid']] as const) {
    assert.deepEqual(new DetectionRetryBudget().failure(new ApiRequestError(message, 0, status)), { stop: true, delayMs: 0 });
  }
});

test('transient failures back off, stop after three failures, and reset after success', () => {
  const budget = new DetectionRetryBudget();
  const error = new ApiRequestError('Gemini failed after one retry.', 0, 502, 'upstream_error');
  assert.deepEqual(budget.failure(error), { stop:false, delayMs:2000 });
  assert.deepEqual(budget.failure(error), { stop:false, delayMs:4000 });
  assert.deepEqual(budget.failure(error), { stop:true, delayMs:0 });
  budget.success(); assert.deepEqual(budget.failure(new TypeError('Network unavailable')), { stop:false, delayMs:2000 });
});
