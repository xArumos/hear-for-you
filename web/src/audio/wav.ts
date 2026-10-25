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
    const originalPosition = index / ratio;
    const leftIndex = Math.floor(originalPosition);
    const rightIndex = Math.min(leftIndex + 1, samples.length - 1);
    const fraction = originalPosition - leftIndex;
    const leftSample = samples[leftIndex] ?? 0;
    const rightSample = samples[rightIndex] ?? leftSample;
    output[index] = leftSample * (1 - fraction) + rightSample * fraction;
  }

  return output;
}

export async function validateWavFile(blob: Blob, expectedSampleCount?: number): Promise<boolean> {
  if (!blob || blob.size < 44) {
    return false;
  }

  const buffer = await blob.arrayBuffer();
  if (buffer.byteLength < 44) {
    return false;
  }

  const view = new DataView(buffer);

  const readString = (offset: number, length: number) => {
    let value = '';
    for (let index = 0; index < length; index += 1) {
      value += String.fromCharCode(view.getUint8(offset + index));
    }
    return value;
  };

  if (readString(0, 4) !== 'RIFF' || readString(8, 4) !== 'WAVE' || readString(12, 4) !== 'fmt ' || readString(36, 4) !== 'data') {
    return false;
  }

  const audioFormat = view.getUint16(20, true);
  const channels = view.getUint16(22, true);
  const sampleRate = view.getUint32(24, true);
  const byteRate = view.getUint32(28, true);
  const blockAlign = view.getUint16(32, true);
  const bitsPerSample = view.getUint16(34, true);
  const dataLength = view.getUint32(40, true);

  if (audioFormat !== 1 || channels !== 1 || sampleRate !== 16000 || bitsPerSample !== 16) {
    return false;
  }

  if (byteRate !== sampleRate * blockAlign || blockAlign !== 2) {
    return false;
  }

  const sampleCount = dataLength / 2;
  if (!Number.isInteger(sampleCount) || sampleCount <= 0) {
    return false;
  }

  if (buffer.byteLength !== 44 + dataLength) {
    return false;
  }

  if (expectedSampleCount !== undefined && sampleCount !== expectedSampleCount) {
    return false;
  }

  return true;
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
