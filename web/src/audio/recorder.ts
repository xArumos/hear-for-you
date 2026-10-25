import { Capacitor } from '@capacitor/core';
import { encodeWav, resampleToSampleRate, validateWavFile } from './wav.ts';

export function explainMicrophoneError(error: unknown): string {
  const name = error instanceof Error ? error.name : '';
  if (name === 'NotAllowedError' && Capacitor.isNativePlatform()) return 'Microphone access was denied. Enable microphone access for HearAlert in iPhone Settings, then retry.';
  const messages: Record<string, string> = {
    NotAllowedError: 'Microphone permission was denied. Enable microphone access in browser site settings, then retry.',
    NotFoundError: 'No microphone was found. Connect a microphone and retry.',
    NotReadableError: 'The microphone is busy or unreadable. Close other apps using it and retry.',
    AbortError: 'Recording was interrupted. Please record this clip again.',
    OverconstrainedError: 'This microphone cannot provide the requested audio settings.',
    SecurityError: 'Microphone access is blocked by browser security settings. Use HTTPS or localhost.',
  };
  return messages[name] ?? (error instanceof Error ? error.message : 'Audio capture failed. Please retry.');
}

export function trimCapturedSamples(samples: Float32Array, count: number): Float32Array {
  return new Float32Array(samples.subarray(0, count));
}

export interface CaptureSession { stop(): Promise<void>; sampleRate: number }

/** Each caller owns its stream; cancellation also releases a late permission grant. */
export async function openMicrophone(
  onSamples: (samples: Float32Array) => void,
  options: { signal?: AbortSignal; onError?: (error: Error) => void } = {},
): Promise<CaptureSession> {
  if (!window.isSecureContext && !Capacitor.isNativePlatform()) throw new Error('Microphone access requires HTTPS or localhost.');
  if (!navigator.mediaDevices?.getUserMedia || typeof AudioContext === 'undefined' || typeof AudioWorkletNode === 'undefined') {
    throw new Error('This browser does not support microphone AudioWorklet capture.');
  }
  let interrupted = false;
  const aborted = () => { if (interrupted || options.signal?.aborted) throw new DOMException('Capture cancelled', 'AbortError'); };
  aborted();
  let stream: MediaStream | undefined;
  let context: AudioContext | undefined;
  let source: MediaStreamAudioSourceNode | undefined;
  let node: AudioWorkletNode | undefined;
  let stopped = false;
  const fail = () => options.onError?.(new Error('The microphone disconnected. Reconnect it and retry.'));
  const stateChanged = () => { if (!stopped && context?.state !== 'running') options.onError?.(new Error('Audio capture was suspended or closed. Please restart capture.')); };
  const stop = async () => {
    if (stopped) return;
    stopped = true;
    options.signal?.removeEventListener('abort', onAbort);
    window.removeEventListener('hear-for-you-native-inactive', inactive);
    if (node) { node.port.onmessage = null; node.disconnect(); }
    source?.disconnect();
    stream?.getTracks().forEach(track => { track.removeEventListener('ended', fail); track.stop(); });
    context?.removeEventListener('statechange', stateChanged);
    if (context && context.state !== 'closed') await context.close();
  };
  const onAbort = () => { void stop(); };
  const inactive = () => { interrupted = true; options.onError?.(new Error('The app was interrupted or backgrounded. Start capture again when ready.')); if (stream) void stop(); };
  try {
    window.addEventListener('hear-for-you-native-inactive', inactive);
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    aborted();
    const tracks = stream.getAudioTracks();
    if (!tracks.length || tracks.some(track => track.readyState !== 'live')) throw new Error('The microphone stream has ended. Please retry.');
    context = new AudioContext();
    if (context.state === 'suspended') await context.resume();
    aborted();
    if (context.state !== 'running') throw new Error('Audio capture is suspended. Please retry.');
    source = context.createMediaStreamSource(stream);
    await context.audioWorklet.addModule(new URL('./recorder-worklet.js', import.meta.url));
    aborted();
    node = new AudioWorkletNode(context, 'hearalert-recorder-processor');
    node.port.onmessage = (event: MessageEvent<Float32Array>) => { if (!stopped) onSamples(new Float32Array(event.data)); };
    // Keep the processing graph pulled by the destination; the processor emits silence.
    source.connect(node);
    node.connect(context.destination);
    tracks.forEach(track => track.addEventListener('ended', fail));
    context.addEventListener('statechange', stateChanged);
    options.signal?.addEventListener('abort', onAbort, { once: true });
    return { stop, sampleRate: context.sampleRate };
  } catch (error) {
    await stop();
    throw error;
  }
}

export async function recordMicrophoneClip(durationMs = 3000, options: { signal?: AbortSignal; allowSilence?: boolean; onProgress?: (fraction: number) => void } = {}): Promise<Blob> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  options.signal?.addEventListener('abort', abort, { once: true });
  if (options.signal?.aborted) controller.abort();
  let session: CaptureSession | undefined;
  let timeout: ReturnType<typeof setTimeout> | undefined;
  let rejectCapture: (error: Error) => void = () => {};
  const fragments: Float32Array[] = [];
  let total = 0;
  const cancelled = () => rejectCapture(new DOMException('Recording interrupted', 'AbortError'));
  try {
    let finish: (samples: Float32Array) => void = () => {};
    const complete = new Promise<Float32Array>((resolve, reject) => { finish = resolve; rejectCapture = reject; });
    void complete.catch(() => {});
    controller.signal.addEventListener('abort', cancelled, { once: true });
    session = await openMicrophone(samples => {
      if (!session) return;
      fragments.push(samples);
      total += samples.length;
      const required = Math.ceil(durationMs / 1000 * session.sampleRate);
      options.onProgress?.(Math.min(1, total / required));
      if (total >= required) {
        const merged = new Float32Array(total);
        let offset = 0;
        for (const fragment of fragments) { merged.set(fragment, offset); offset += fragment.length; }
        finish(trimCapturedSamples(merged, required));
      }
    }, { signal: controller.signal, onError: error => rejectCapture(error) });
    timeout = setTimeout(() => rejectCapture(new Error('Recording stopped before enough audio was captured. Please re-record.')), durationMs + 5000);
    const samples = await complete;
    const outputCount = Math.round(durationMs / 1000 * 16000);
    const output = trimCapturedSamples(resampleToSampleRate(samples, session.sampleRate, 16000), outputCount);
    if (!options.allowSilence && !output.some(sample => Math.abs(sample) >= 0.001)) throw new Error('No usable sound was detected. Make the sound and record again.');
    const wav = encodeWav(output);
    if (!await validateWavFile(wav, outputCount)) throw new Error('Recording has an invalid WAV format or duration. Please re-record.');
    return wav;
  } finally {
    clearTimeout(timeout);
    controller.signal.removeEventListener('abort', cancelled);
    options.signal?.removeEventListener('abort', abort);
    await session?.stop();
  }
}
