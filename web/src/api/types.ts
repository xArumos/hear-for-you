export type ApiErrorCode = 'bad_audio' | 'not_found' | 'bad_request' | 'rate_limited' | 'upstream_error';

export interface ApiError {
  code: ApiErrorCode;
  message: string;
  retry_after_ms?: number;
}

export type DetectKind = 'builtin' | 'taught' | 'unknown' | 'none';

export interface HealthResponse {
  ok: true;
  models: {
    embed: string;
    describe: string;
  };
}

export interface DetectResponse {
  event_id: string;
  kind: DetectKind;
  label: string | null;
  sound_id: string | null;
  confidence: number | null;
  description: string | null;
  latency_ms: number;
}

export interface TeachSelfCheck {
  passed: boolean;
  score: number;
  threshold: number;
}

export type IconKey =
  | 'door'
  | 'bell'
  | 'alarm'
  | 'baby'
  | 'dog'
  | 'kettle'
  | 'microwave'
  | 'phone'
  | 'voice'
  | 'glass'
  | 'siren'
  | 'water'
  | 'generic';

export interface TeachResponse {
  sound_id: string;
  name: string;
  icon: IconKey;
  self_check: TeachSelfCheck;
  latency_ms: number;
}

export type SoundKind = 'builtin' | 'taught';

export interface SoundRecord {
  sound_id: string;
  name: string;
  icon: IconKey;
  kind: SoundKind;
  enabled: boolean;
}

export interface SoundsResponse {
  sounds: SoundRecord[];
  latency_ms: number;
}

export interface UpdateSoundRequest {
  enabled?: boolean;
  name?: string;
}

export interface UpdateSoundResponse extends SoundRecord {
  latency_ms: number;
}

export interface DeleteSoundResponse {
  deleted: true;
  latency_ms: number;
}

export interface HistoryEvent {
  event_id: string;
  at: string;
  kind: DetectKind;
  label: string | null;
  sound_id: string | null;
  confidence: number | null;
  description: string | null;
}

export interface HistoryResponse {
  events: HistoryEvent[];
  latency_ms: number;
}

export interface MetricsResponse {
  builtin_accuracy: {
    zero_shot: number;
    trained: number;
    test_fold: number;
  };
  taught_miss_rate: number;
  false_alarms_per_hour: number;
  latency_ms_median: number;
  gemini_calls_per_hour: {
    gate_off: number;
    gate_on: number;
  };
  updated_at: string;
}
