/** Retain the contract error and HTTP status without guessing an upstream cause. */
export class ApiRequestError extends Error {
  retryAfterMs: number;
  status: number;
  code?: string;
  constructor(message: string, retryAfterMs = 0, status = 0, code?: string) {
    super(message); this.name = 'ApiRequestError';
    this.retryAfterMs = retryAfterMs; this.status = status; this.code = code;
  }
}

/** A validly shaped request whose samples are below the backend audio floor. */
export function isSilentClipError(error: unknown): boolean {
  return error instanceof ApiRequestError
    && error.status === 400
    && error.code === 'bad_audio'
    && /^clip is silent\.?$/i.test(error.message.trim());
}

export class DetectionRetryBudget {
  private failures = 0;
  success(): void { this.failures = 0; }
  failure(error: unknown): { stop: boolean; delayMs: number } {
    this.failures++;
    if (error instanceof ApiRequestError) {
      // The current backend hides non-retryable Gemini causes behind this exact message.
      // Stop rather than treating an unknown authentication/model failure as transient.
      const permanent = [400, 401, 403, 404, 422].includes(error.status)
        || /authentication|api key|invalid model|model.*not found|quota|billing/i.test(error.message)
        || error.message === 'Gemini request failed.';
      if (permanent) return { stop: true, delayMs: 0 };
    }
    if (this.failures >= 3) return { stop: true, delayMs: 0 };
    const requested = error instanceof ApiRequestError ? error.retryAfterMs : 0;
    return { stop: false, delayMs: Math.max(requested, Math.min(30000, 2000 * 2 ** (this.failures - 1))) };
  }
}
