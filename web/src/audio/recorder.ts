import { encodeWav, resampleToSampleRate } from './wav';

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

export async function recordMicrophoneClip(durationMs = 3000): Promise<Blob> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error('Microphone access is not available in this browser.');
  }

  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
    },
  });

  const audioContext = new AudioContext();
  const inputSampleRate = audioContext.sampleRate;
  const source = audioContext.createMediaStreamSource(stream);
  const fragments: Float32Array[] = [];

  await audioContext.audioWorklet.addModule(new URL('./recorder-worklet.js', import.meta.url));

  const workletNode = new AudioWorkletNode(audioContext, 'hearalert-recorder-processor');
  workletNode.port.onmessage = (event: MessageEvent<Float32Array>) => {
    fragments.push(new Float32Array(event.data));
  };

  source.connect(workletNode);

  try {
    await sleep(durationMs);
  } finally {
    workletNode.disconnect();
    source.disconnect();
    stream.getTracks().forEach((track) => track.stop());
    await audioContext.close();
  }

  const samples = new Float32Array(fragments.reduce((size, chunk) => size + chunk.length, 0));
  let offset = 0;
  for (const fragment of fragments) {
    samples.set(fragment, offset);
    offset += fragment.length;
  }

  if (samples.length === 0) {
    throw new Error('No audio samples were captured.');
  }

  const resampled = resampleToSampleRate(samples, inputSampleRate, 16000);
  return encodeWav(resampled, 16000);
}
