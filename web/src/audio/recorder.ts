import { encodeWav, resampleToSampleRate, validateWavFile } from './wav.ts';

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function peakAmplitude(samples: Float32Array): number {
  let peak = 0;
  for (let index = 0; index < samples.length; index += 1) {
    peak = Math.max(peak, Math.abs(samples[index]));
  }
  return peak;
}

export function explainMicrophoneError(error: unknown): string {
  const browserError = error instanceof DOMException ? error : null;

  if (browserError?.name === 'NotAllowedError') {
    return 'Microphone permission was denied. Please allow access and try again.';
  }

  if (browserError?.name === 'NotFoundError') {
    return 'No microphone was found on this device. Connect a microphone and try again.';
  }

  if (browserError?.name === 'NotReadableError') {
    return 'The microphone is in use by another app or is not readable right now.';
  }

  if (browserError?.name === 'AbortError') {
    return 'The recording was interrupted. Please try again.';
  }

  if (error instanceof Error && /secure|https|localhost/i.test(error.message)) {
    return 'Microphone access requires a secure context. Use HTTPS or localhost.';
  }

  if (typeof navigator !== 'undefined' && !navigator.mediaDevices?.getUserMedia) {
    return 'This browser does not support microphone capture.';
  }

  return 'Microphone recording could not start. Please check your browser permissions and try again.';
}

export function trimCapturedSamples(samples: Float32Array, targetSampleCount: number): Float32Array {
  if (samples.length <= targetSampleCount) {
    return new Float32Array(samples);
  }

  return new Float32Array(samples.subarray(0, targetSampleCount));
}

export async function recordMicrophoneClip(durationMs = 3000, options: { signal?: AbortSignal } = {}): Promise<Blob> {
  const secureContext = typeof window !== 'undefined' && (window.isSecureContext || window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');
  if (!secureContext) {
    throw new Error('Microphone access requires a secure context. Use HTTPS or localhost.');
  }

  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error('Microphone access is not available in this browser.');
  }

  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: false,
    },
  });

  const audioContext = new AudioContext();
  if (audioContext.state === 'suspended') {
    await audioContext.resume();
  }

  const inputSampleRate = audioContext.sampleRate;
  const targetSampleRate = 16000;
  const source = audioContext.createMediaStreamSource(stream);
  const fragments: Float32Array[] = [];
  const minimumSourceSamples = Math.max(1, Math.ceil((durationMs / 1000) * inputSampleRate));
  const targetOutputSamples = Math.max(1, Math.round((durationMs / 1000) * targetSampleRate));

  await audioContext.audioWorklet.addModule(new URL('./recorder-worklet.js', import.meta.url));

  const workletNode = new AudioWorkletNode(audioContext, 'hearalert-recorder-processor');

  const stopStream = async () => {
    workletNode.disconnect();
    source.disconnect();
    stream.getTracks().forEach((track) => track.stop());
    await audioContext.close();
  };

  try {
    const capture = new Promise<Float32Array>((resolve, reject) => {
      let settled = false;
      const finalize = (error?: Error) => {
        if (settled) {
          return;
        }
        settled = true;
        window.clearTimeout(timeoutId);
        workletNode.port.onmessage = null;
        resolve(buildMergedSamples(fragments, minimumSourceSamples));
        if (error) {
          reject(error);
        }
      };

      const timeoutId = window.setTimeout(() => {
        if (fragments.length === 0) {
          finalize(new Error('No usable audio samples were captured.'));
          return;
        }
        finalize();
      }, durationMs + 1200);

      const onAbort = () => {
        finalize(new DOMException('The microphone recording was aborted.', 'AbortError'));
      };

      if (options.signal) {
        if (options.signal.aborted) {
          onAbort();
          return;
        }
        options.signal.addEventListener('abort', onAbort, { once: true });
      }

      workletNode.port.onmessage = (event: MessageEvent<Float32Array>) => {
        const chunk = new Float32Array(event.data);
        if (chunk.length === 0) {
          return;
        }

        fragments.push(chunk);
        const totalSamples = fragments.reduce((sum, fragment) => sum + fragment.length, 0);
        if (totalSamples >= minimumSourceSamples) {
          finalize();
        }
      };
    });

    source.connect(workletNode);
    const captured = await capture;
    const trimmed = trimCapturedSamples(captured, minimumSourceSamples);
    const resampled = resampleToSampleRate(trimmed, inputSampleRate, targetSampleRate);
    const exactLength = trimCapturedSamples(resampled, targetOutputSamples);

    if (peakAmplitude(exactLength) < 0.01) {
      throw new Error('No usable sound was detected. Try recording again with the sound active.');
    }

    const wav = encodeWav(exactLength, targetSampleRate);
    const isValid = await validateWavFile(wav, targetOutputSamples);
    if (!isValid) {
      throw new Error('The recorded audio does not match the required 16 kHz mono WAV format.');
    }

    return wav;
  } finally {
    await stopStream();
  }
}

function buildMergedSamples(fragments: Float32Array[], minimumSourceSamples: number): Float32Array {
  const totalSamples = fragments.reduce((sum, fragment) => sum + fragment.length, 0);
  const samples = new Float32Array(Math.max(1, Math.min(totalSamples, minimumSourceSamples)));

  let offset = 0;
  for (const fragment of fragments) {
    const remaining = samples.length - offset;
    if (remaining <= 0) {
      break;
    }

    const lengthToCopy = Math.min(fragment.length, remaining);
    samples.set(fragment.subarray(0, lengthToCopy), offset);
    offset += lengthToCopy;
  }

  return samples;
}
