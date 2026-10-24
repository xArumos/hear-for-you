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

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: {
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    const errorPayload = (await response.json().catch(() => null)) as { error?: { code: string; message: string } } | null;
    const message = errorPayload?.error?.message ?? 'Request failed.';
    throw new Error(message);
  }

  return (await response.json()) as T;
}

export async function getHealth(): Promise<HealthResponse> {
  return fetchJson<HealthResponse>('/health');
}

export async function detectClip(clip: Blob, levelDb: number): Promise<DetectResponse> {
  const form = new FormData();
  form.append('clip', clip, 'clip.wav');
  form.append('level_db', String(levelDb));

  return fetchJson<DetectResponse>('/detect', {
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
