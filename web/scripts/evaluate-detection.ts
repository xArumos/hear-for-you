import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { AlertPolicy } from '../src/alert-policy.ts';
import type { DetectResponse, SoundsResponse } from '../src/api/types.ts';
import type { GuestSound } from '../src/teach-state.ts';

interface EvaluationCase {
  id: string;
  path: string;
  expected_sound_id: string | null;
  condition: string;
  source: string;
}

interface EvaluationResult {
  id: string;
  expected_sound_id: string | null;
  condition: string;
  source: string;
  peak_dbfs: number;
  status: number;
  response: DetectResponse;
  frontend_alert: boolean;
  frontend_eligible_independently: boolean;
  correct_builtin: boolean;
  false_alert: boolean;
}

const sleep = (milliseconds: number): Promise<void> => new Promise(resolveDelay => setTimeout(resolveDelay, milliseconds));

function peakDbfs(wav: Buffer): number {
  if (wav.length !== 96_044 || wav.toString('ascii', 0, 4) !== 'RIFF' || wav.toString('ascii', 8, 12) !== 'WAVE') {
    throw new Error('Expected an exact 3.0 s PCM WAV file.');
  }
  const channels = wav.readUInt16LE(22);
  const sampleRate = wav.readUInt32LE(24);
  const bits = wav.readUInt16LE(34);
  const dataTag = wav.toString('ascii', 36, 40);
  const dataBytes = wav.readUInt32LE(40);
  if (channels !== 1 || sampleRate !== 16_000 || bits !== 16 || dataTag !== 'data' || dataBytes !== 96_000) {
    throw new Error('Expected 16 kHz mono 16-bit PCM WAV with 48,000 samples.');
  }
  let peak = 0;
  for (let offset = 44; offset < wav.length; offset += 2) peak = Math.max(peak, Math.abs(wav.readInt16LE(offset)));
  if (peak === 0) throw new Error('Silent clips are not valid detection inputs.');
  return 20 * Math.log10(peak / 32_768);
}

function parseArguments(): { manifestPath: string; endpoint: string; intervalMs: number } {
  const [, , manifestPath, endpoint = 'http://127.0.0.1:8000', interval = '1100'] = process.argv;
  if (!manifestPath) throw new Error('Usage: npm run evaluate:detection -- <manifest.json> [endpoint] [interval_ms]');
  const url = new URL(endpoint);
  if (url.protocol !== 'https:' && url.hostname !== '127.0.0.1' && url.hostname !== 'localhost') {
    throw new Error('Use HTTPS except for a local backend.');
  }
  const intervalMs = Number(interval);
  if (!Number.isFinite(intervalMs) || intervalMs < 1_000) throw new Error('interval_ms must be at least 1000.');
  return { manifestPath: resolve(manifestPath), endpoint: url.href.replace(/\/$/, ''), intervalMs };
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<{ status: number; body: T }> {
  const response = await fetch(url, init);
  const body = await response.json() as T;
  return { status: response.status, body };
}

async function detect(endpoint: string, wav: Buffer, levelDb: number): Promise<{ status: number; body: DetectResponse }> {
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const form = new FormData();
    form.append('clip', new Blob([wav], { type: 'audio/wav' }), 'evaluation.wav');
    form.append('level_db', String(levelDb));
    const result = await requestJson<DetectResponse | { error?: { message?: string; retry_after_ms?: number } }>(`${endpoint}/api/detect`, { method: 'POST', body: form });
    if (result.status === 429 && attempt < 2) {
      const error = 'error' in result.body ? result.body.error : undefined;
      await sleep(Math.max(1_000, error?.retry_after_ms ?? 1_000));
      continue;
    }
    if (result.status !== 200 || !('kind' in result.body)) {
      const error = 'error' in result.body ? result.body.error : undefined;
      throw new Error(`Detect failed (${result.status}): ${error?.message ?? 'invalid response'}`);
    }
    return { status: result.status, body: result.body };
  }
  throw new Error('Detect retry loop exhausted.');
}

async function main(): Promise<void> {
  const { manifestPath, endpoint, intervalMs } = parseArguments();
  const manifest = JSON.parse(await readFile(manifestPath, 'utf8')) as EvaluationCase[];
  if (!Array.isArray(manifest) || manifest.length === 0) throw new Error('Manifest must be a non-empty JSON array.');
  const soundsResult = await requestJson<SoundsResponse>(`${endpoint}/api/sounds`);
  if (soundsResult.status !== 200) throw new Error(`Could not read enabled sounds (${soundsResult.status}).`);
  const sounds: GuestSound[] = soundsResult.body.sounds;
  const policy = new AlertPolicy();
  const results: EvaluationResult[] = [];
  let previousRequestAt = 0;

  for (const item of manifest) {
    if (!item.id || !item.path || !item.condition || !item.source || !('expected_sound_id' in item)) {
      throw new Error('Each case needs id, path, expected_sound_id, condition and source.');
    }
    const wait = previousRequestAt + intervalMs - Date.now();
    if (wait > 0) await sleep(wait);
    const wav = await readFile(resolve(item.path));
    const levelDb = peakDbfs(wav);
    previousRequestAt = Date.now();
    const { status, body } = await detect(endpoint, wav, levelDb);
    const frontendAlert = policy.accept(body, sounds, performance.now());
    const frontendEligibleIndependently = new AlertPolicy().accept(body, sounds, performance.now());
    const correctBuiltin = item.expected_sound_id !== null && body.kind === 'builtin' && body.sound_id === item.expected_sound_id;
    const falseAlert = item.expected_sound_id === null && frontendAlert;
    results.push({
      id: item.id,
      expected_sound_id: item.expected_sound_id,
      condition: item.condition,
      source: item.source,
      peak_dbfs: Number(levelDb.toFixed(3)),
      status,
      response: body,
      frontend_alert: frontendAlert,
      frontend_eligible_independently: frontendEligibleIndependently,
      correct_builtin: correctBuiltin,
      false_alert: falseAlert,
    });
  }

  process.stdout.write(`${JSON.stringify({
    generated_at: new Date().toISOString(),
    endpoint,
    interval_ms: intervalMs,
    enabled_builtin_ids: sounds.filter(sound => sound.kind === 'builtin' && sound.enabled).map(sound => sound.sound_id),
    results,
  }, null, 2)}\n`);
}

await main();
