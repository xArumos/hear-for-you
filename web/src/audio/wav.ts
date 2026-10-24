export function clampSample(value: number): number {
  return Math.max(-1, Math.min(1, value));
}

export function resampleToSampleRate(samples: Float32Array, inputSampleRate: number, targetSampleRate: number): Float32Array {
  if (inputSampleRate === targetSampleRate || samples.length === 0) {
    return new Float32Array(samples);
  }

  const ratio = targetSampleRate / inputSampleRate;
  const outputLength = Math.max(1, Math.round(samples.length * ratio));
  const output = new Float32Array(outputLength);

  for (let index = 0; index < outputLength; index += 1) {
    const originalPosition = (index / ratio);
    const leftIndex = Math.floor(originalPosition);
    const rightIndex = Math.min(leftIndex + 1, samples.length - 1);
    const fraction = originalPosition - leftIndex;
    const leftSample = samples[leftIndex] ?? 0;
    const rightSample = samples[rightIndex] ?? leftSample;
    output[index] = leftSample * (1 - fraction) + rightSample * fraction;
  }

  return output;
}

export function encodeWav(samples: Float32Array, sampleRate = 16000): Blob {
  const dataLength = samples.length * 2;
  const buffer = new ArrayBuffer(44 + dataLength);
  const view = new DataView(buffer);

  const writeString = (offset: number, value: string) => {
    for (let index = 0; index < value.length; index += 1) {
      view.setUint8(offset + index, value.charCodeAt(index));
    }
  };

  writeString(0, 'RIFF');
  view.setUint32(4, 36 + dataLength, true);
  writeString(8, 'WAVE');
  writeString(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeString(36, 'data');
  view.setUint32(40, dataLength, true);

  const pcmData = new Int16Array(samples.length);
  for (let index = 0; index < samples.length; index += 1) {
    const value = clampSample(samples[index]);
    pcmData[index] = value < 0 ? value * 0x8000 : value * 0x7fff;
  }

  new Int16Array(buffer, 44).set(pcmData);
  return new Blob([buffer], { type: 'audio/wav' });
}
