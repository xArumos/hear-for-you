import type {
  DeleteSoundResponse,
  DetectResponse,
  HealthResponse,
  HistoryResponse,
  MetricsResponse,
  SoundsResponse,
  TeachResponse,
  UpdateSoundRequest,
  UpdateSoundResponse,
} from './types';
import healthFixture from '../fixtures/health.json';
import soundsFixture from '../fixtures/sounds.json';
import detectBuiltinFixture from '../fixtures/detect_builtin.json';
import detectTaughtFixture from '../fixtures/detect_taught.json';
import detectUnknownFixture from '../fixtures/detect_unknown.json';
import detectNoneFixture from '../fixtures/detect_none.json';
import teachFixture from '../fixtures/teach.json';
import historyFixture from '../fixtures/history.json';
import metricsFixture from '../fixtures/metrics.json';
import updateSoundFixture from '../fixtures/update_sound.json';
import deleteSoundFixture from '../fixtures/delete_sound.json';

import { ApiRequestError } from './errors';
export { ApiRequestError } from './errors';

const useFixtures = import.meta.env.VITE_USE_FIXTURES === '1';

const fixtureMap: Record<string, unknown> = {
  '/health': healthFixture,
  '/sounds': soundsFixture,
  '/detect': detectBuiltinFixture,
  '/teach': teachFixture,
  '/history': historyFixture,
  '/metrics': metricsFixture,
  '/sounds/snd_3c1d': updateSoundFixture,
  '/sounds/snd_3c1d/delete': deleteSoundFixture,
};

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  if (useFixtures) {
    const fixture = fixtureMap[path];
    if (!fixture) {
      throw new Error(`No fixture configured for ${path}`);
    }
    return fixture as T;
  }

  const response = await fetch(`/api${path}`, {
    ...init,
    headers: {
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    const errorPayload = (await response.json().catch(() => null)) as { error?: { code: string; message: string; retry_after_ms?: number } } | null;
    const message = errorPayload?.error?.message ?? 'Request failed.';
    throw new ApiRequestError(message, errorPayload?.error?.retry_after_ms ?? 0, response.status, errorPayload?.error?.code);
  }

  return (await response.json()) as T;
}

export async function getHealth(): Promise<HealthResponse> {
  return fetchJson<HealthResponse>('/health');
}

export async function detectClip(clip: Blob, levelDb: number, signal?: AbortSignal): Promise<DetectResponse> {
  const form = new FormData();
  form.append('clip', clip, 'clip.wav');
  form.append('level_db', String(levelDb));

  return fetchJson<DetectResponse>('/detect', {
    signal,
    method: 'POST',
    body: form,
  });
}

export async function teachSound(payload: FormData): Promise<TeachResponse> {
  return fetchJson<TeachResponse>('/teach', {
    method: 'POST',
    body: payload,
  });
}

export async function getSounds(): Promise<SoundsResponse> {
  return fetchJson<SoundsResponse>('/sounds');
}

export async function updateSound(soundId: string, body: UpdateSoundRequest): Promise<UpdateSoundResponse> {
  return fetchJson<UpdateSoundResponse>(`/sounds/${soundId}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });
}

export async function deleteSound(soundId: string): Promise<DeleteSoundResponse> {
  return fetchJson<DeleteSoundResponse>(`/sounds/${soundId}`, {
    method: 'DELETE',
  });
}

export async function getHistory(since?: string, limit = 100): Promise<HistoryResponse> {
  const query = new URLSearchParams();
  if (since) query.set('since', since);
  query.set('limit', String(limit));
  return fetchJson<HistoryResponse>(`/history?${query.toString()}`);
}

export async function getMetrics(): Promise<MetricsResponse> {
  return fetchJson<MetricsResponse>('/metrics');
}
