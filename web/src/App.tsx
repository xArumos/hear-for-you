import { useEffect, useState } from 'react';
import { recordMicrophoneClip } from './audio/recorder';

function App() {
  const [isRecording, setIsRecording] = useState(false);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [status, setStatus] = useState('Ready to record a 3.0 second clip.');
  const [fileInfo, setFileInfo] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    return () => {
      if (audioUrl) {
        URL.revokeObjectURL(audioUrl);
      }
    };
  }, [audioUrl]);

  const handleRecord = async () => {
    setIsRecording(true);
    setError(null);
    setStatus('Requesting microphone access…');
    setFileInfo('');

    try {
      const blob = await recordMicrophoneClip(3000);
      const nextUrl = URL.createObjectURL(blob);
      setAudioUrl((previousUrl) => {
        if (previousUrl) {
          URL.revokeObjectURL(previousUrl);
        }
        return nextUrl;
      });
      setFileInfo(`${(blob.size / 1024).toFixed(1)} KB • 16 kHz mono • 16-bit PCM WAV`);
      setStatus('Recording complete. Clip is encoded as 16 kHz mono 16-bit PCM WAV.');
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : 'Unable to record microphone audio.';
      setError(message);
      setStatus('Recording failed.');
    } finally {
      setIsRecording(false);
    }
  };

  return (
    <main className="min-h-screen bg-slate-100 p-6 text-slate-900">
      <div className="mx-auto max-w-xl rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <h1 className="text-2xl font-semibold">HearAlert Test Recorder</h1>
        <p className="mt-3 text-sm text-slate-600">
          Records exactly 3.0 seconds from the microphone, converts it to 16 kHz mono 16-bit PCM WAV,
          and lets you play it back locally.
        </p>

        <button
          type="button"
          onClick={handleRecord}
          disabled={isRecording}
          className="mt-6 inline-flex w-full items-center justify-center rounded-md bg-blue-600 px-4 py-3 text-base font-medium text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-400"
        >
          {isRecording ? 'Recording…' : 'Record 3.0 second clip'}
        </button>

        <p className="mt-4 text-sm text-slate-700">{status}</p>

        {fileInfo ? (
          <p className="mt-2 text-xs font-medium uppercase tracking-wide text-slate-500">{fileInfo}</p>
        ) : null}

        {error ? (
          <p role="alert" className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </p>
        ) : null}

        {audioUrl ? (
          <div className="mt-6 rounded-md border border-slate-200 bg-slate-50 p-3">
            <audio controls src={audioUrl} className="w-full" />
          </div>
        ) : null}
      </div>
    </main>
  );
}

export default App;
