import { useEffect, useRef, useState } from 'react';
import { getHealth, getHistory, getSounds, teachSound, updateSound } from './api/client';
import type { HealthResponse, HistoryEvent, SoundRecord } from './api/types';
import { recordMicrophoneClip } from './audio/recorder';
import { countCompletedRecordings, isReadyToSave, type RecordingStep } from './teach-state';

type Screen = 'listen' | 'teach' | 'record' | 'history' | 'recognized' | 'unknown' | 'attention';
type IconName = 'door' | 'bell' | 'alarm' | 'baby' | 'dog' | 'kettle' | 'microwave' | 'phone' | 'voice' | 'glass' | 'siren' | 'water' | 'generic';

const iconPaths: Record<IconName | 'history' | 'moon' | 'pause' | 'check' | 'warning', React.ReactNode> = {
  door: <><path d="M5 21V4a1 1 0 0 1 1-1h11a1 1 0 0 1 1 1v17" /><path d="M3 21h18M14 12h.01" /></>,
  bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" /></>,
  alarm: <><circle cx="12" cy="13" r="8" /><path d="M12 9v4l2 2M5 3 2 6M19 3l3 3" /></>,
  baby: <><circle cx="12" cy="8" r="4" /><path d="M8 7c-2-2-2-4 1-5M6 14c1 5 11 5 12 0M9 13h.01M15 13h.01" /></>,
  dog: <><path d="M5 11 3 6l5 2a7 7 0 0 1 8 0l5-2-2 5v5a4 4 0 0 1-4 4H9a4 4 0 0 1-4-4zM9 13h.01M15 13h.01M10 17h4" /></>,
  kettle: <><path d="M6 8h10v11H6zM8 5h6M16 10c4 0 5 2 5 4s-2 4-5 4M4 10h2" /></>,
  microwave: <><rect x="2" y="5" width="20" height="14" rx="2" /><path d="M14 8h5v8h-5zM5 9h6v6H5z" /></>,
  phone: <><rect x="6" y="2" width="12" height="20" rx="2" /><path d="M10 18h4" /></>,
  voice: <><path d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3M5 11a7 7 0 0 0 14 0M12 18v4" /></>,
  glass: <><path d="m5 3 2 8h4l-2 10M19 3l-2 8h-4l2 10M5 3h14" /></>,
  siren: <><path d="M6 17h12l-1-8a5 5 0 0 0-10 0zM4 21h16M12 2V0M3 6 1 5M21 6l2-1" /></>,
  water: <><path d="M12 2S5 10 5 15a7 7 0 0 0 14 0c0-5-7-13-7-13zM9 16a3 3 0 0 0 3 3" /></>,
  generic: <><path d="M4 12h2l2-6 4 12 3-9 2 3h3" /></>,
  history: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  moon: <path d="M20 15a8 8 0 1 1-11-11 7 7 0 0 0 11 11z" />,
  pause: <><path d="M8 5v14M16 5v14" /></>,
  check: <path d="m5 12 4 4L19 6" />,
  warning: <><path d="M12 3 2 21h20zM12 9v5M12 18h.01" /></>,
};

function Icon({ name, size = 22 }: { name: keyof typeof iconPaths; size?: number }) {
  return (
    <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      {iconPaths[name]}
    </svg>
  );
}

function PlaybackControl({ label, blob = null, duration, available = true, compact = false }: { label: string; blob?: Blob | null; duration: number; available?: boolean; compact?: boolean }) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const urlRef = useRef<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const [resolvedDuration, setResolvedDuration] = useState(duration);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio || !blob) return;

    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current);
    }

    const nextUrl = URL.createObjectURL(blob);
    urlRef.current = nextUrl;
    audio.src = nextUrl;

    const handleLoadedMetadata = () => {
      setResolvedDuration(Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration : duration);
    };
    const handleTimeUpdate = () => setProgress(audio.currentTime || 0);
    const handleEnded = () => {
      setPlaying(false);
      setProgress(audio.duration || 0);
    };

    audio.addEventListener('loadedmetadata', handleLoadedMetadata);
    audio.addEventListener('timeupdate', handleTimeUpdate);
    audio.addEventListener('ended', handleEnded);

    return () => {
      audio.removeEventListener('loadedmetadata', handleLoadedMetadata);
      audio.removeEventListener('timeupdate', handleTimeUpdate);
      audio.removeEventListener('ended', handleEnded);
      if (urlRef.current) {
        URL.revokeObjectURL(urlRef.current);
        urlRef.current = null;
      }
    };
  }, [blob, duration]);

  useEffect(() => {
    if (!playing) return;
    const audio = audioRef.current;
    if (!audio) return;

    const handlePause = () => setPlaying(false);
    audio.addEventListener('pause', handlePause);
    return () => audio.removeEventListener('pause', handlePause);
  }, [playing]);

  if (!available || !blob) return <span className="playback-unavailable">No retained clip</span>;

  const toggle = async () => {
    const audio = audioRef.current;
    if (!audio) return;

    if (audio.paused) {
      try {
        await audio.play();
        setPlaying(true);
      } catch (error) {
        console.error('Audio playback failed:', error);
      }
      return;
    }

    audio.pause();
    setPlaying(false);
    setProgress(audio.currentTime || 0);
  };

  return (
    <div className={`playback ${compact ? 'compact' : ''}`}>
      <button className="play-button" onClick={toggle} aria-label={`${playing ? 'Pause' : 'Play'} ${label} recording`}>
        {playing ? 'Ⅱ' : '▶'}
      </button>
      <audio ref={audioRef} preload="auto" />
      <div className="playback-details">
        <div>
          <span>{playing ? 'Playing clip' : 'Playback ready'}</span>
          <time>
            {Math.floor(progress / 60)}:{String(Math.floor(progress % 60)).padStart(2, '0')} / 0:{String(Math.ceil(resolvedDuration)).padStart(2, '0')}
          </time>
        </div>
        <div className="playback-track" role="progressbar" aria-label={`${label} playback progress`} aria-valuemin={0} aria-valuemax={Math.ceil(resolvedDuration)} aria-valuenow={Math.round(progress)}>
          <span style={{ width: `${Math.min(100, (progress / Math.max(resolvedDuration, 1)) * 100)}%` }} />
        </div>
      </div>
    </div>
  );
}

const categories: { name: string; icon: IconName }[] = [
  ['Door', 'door'],
  ['Bell', 'bell'],
  ['Alarm', 'alarm'],
  ['Baby', 'baby'],
  ['Dog', 'dog'],
  ['Kettle', 'kettle'],
  ['Microwave', 'microwave'],
  ['Phone', 'phone'],
  ['Voice', 'voice'],
  ['Glass', 'glass'],
  ['Siren', 'siren'],
  ['Water', 'water'],
  ['Other', 'generic'],
].map(([name, icon]) => ({ name, icon: icon as IconName }));

function Brand() {
  return (
    <div className="brand">
      <span className="brand-mark">
        <i />
        <i />
        <i />
        <i />
      </span>
      <strong>HearAlert</strong>
    </div>
  );
}

function Sidebar({ screen, setScreen }: { screen: Screen; setScreen: (s: Screen) => void }) {
  return (
    <aside className="sidebar">
      <Brand />
      <nav aria-label="Main navigation">
        <button className={screen === 'listen' ? 'active' : ''} onClick={() => setScreen('listen')}>
          <Icon name="voice" />
          Listen
        </button>
        <button className={screen === 'teach' || screen === 'record' ? 'active' : ''} onClick={() => setScreen('teach')}>
          <Icon name="generic" />
          Teach
        </button>
        <button className={screen === 'history' ? 'active' : ''} onClick={() => setScreen('history')}>
          <Icon name="history" />
          History
        </button>
      </nav>
      <div className="sidebar-note">
        <Icon name="moon" />
        <span>
          Screen stays awake
          <br />
          <small>While listening</small>
        </span>
      </div>
    </aside>
  );
}

function Shell({ children, screen, setScreen, dark, setDark }: React.PropsWithChildren<{ screen: Screen; setScreen: (s: Screen) => void; dark: boolean; setDark: (v: boolean) => void }>) {
  return (
    <div className="app-shell">
      <Sidebar screen={screen} setScreen={setScreen} />
      <main className="main">
        <header className="topbar">
          <div className="mobile-brand">
            <Brand />
          </div>
          <button className="theme-toggle" aria-label="Toggle color theme" onClick={() => setDark(!dark)}>
            <Icon name="moon" />
            <span>{dark ? 'Light' : 'Dark'} theme</span>
          </button>
        </header>
        {children}
      </main>
    </div>
  );
}

const SOUND_PREFS_KEY = 'hearalert:sound-preferences:v1';

function readStoredSoundPreferences(): Record<string, boolean> {
  try {
    const raw = window.localStorage.getItem(SOUND_PREFS_KEY);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw) as Record<string, boolean>;
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function isSoundVisible(sound: SoundRecord, preferences: Record<string, boolean>): boolean {
  if (sound.kind === 'builtin') {
    return preferences[sound.sound_id] ?? sound.enabled;
  }
  return sound.enabled;
}

function Listen({ setScreen, health, sounds, toggleSound, preferences }: { setScreen: (s: Screen) => void; health: HealthResponse | null; sounds: SoundRecord[]; toggleSound: (soundId: string, enabled: boolean) => Promise<void>; preferences: Record<string, boolean> }) {
  const [status, setStatus] = useState<'active' | 'paused' | 'reconnecting' | 'denied'>('active');
  const statusText = {
    active: 'Listening now',
    paused: 'Listening paused',
    reconnecting: 'Reconnecting…',
    denied: 'Microphone access needed',
  }[status];

  const displaySounds = sounds.filter((sound) => isSoundVisible(sound, preferences));

  return (
    <div className="page listen-page">
      <div className="title-row">
        <div>
          <p className="eyebrow">LIVE AWARENESS</p>
          <h1>Listen</h1>
          <p>Stay aware of the sounds you’ve chosen.</p>
        </div>
        <span className={`status-pill ${status}`}>
          <span />
          {statusText}
        </span>
      </div>

      {status === 'denied' ? (
        <section className="permission card">
          <Icon name="warning" size={30} />
          <div>
            <h2>Allow microphone access</h2>
            <p>HearAlert needs permission to analyze nearby sound on this device. Audio is not stored.</p>
          </div>
          <button onClick={() => setStatus('active')} className="primary">
            Try again
          </button>
        </section>
      ) : (
        <section className={`listener card ${status}`}>
          <div className="sound-orbit">
            <div className="level-ring" />
            <div className="mic-core">
              <Icon name="voice" size={52} />
            </div>
          </div>
          <h2>{statusText}</h2>
          <p className="room-level">
            <span className="level-bars">
              <i />
              <i />
              <i />
              <i />
              <i />
            </span>
            Room level: <strong>{status === 'paused' ? '—' : 'Quiet'}</strong>
          </p>
          <div className="listener-actions">
            <button className="primary" onClick={() => setStatus(status === 'paused' ? 'active' : 'paused')}>
              <Icon name={status === 'paused' ? 'voice' : 'pause'} />
              {status === 'paused' ? 'Resume listening' : 'Pause listening'}
            </button>
            <button className="secondary" onClick={() => setStatus('reconnecting')}>
              Simulate reconnect
            </button>
          </div>
        </section>
      )}

      <div className="dashboard-grid">
        <section className="card sounds-card">
          <div className="section-head">
            <div>
              <h2>Your sounds</h2>
              <p>{health ? `Connected • ${health.models.embed}` : 'Waiting for model data…'}</p>
            </div>
          </div>

          {displaySounds.length > 0 ? (
            <div className="sound-list">
              {displaySounds.slice(0, 6).map((sound) => (
                <div className="sound-row" key={sound.sound_id}>
                  <span className="sound-icon">
                    <Icon name={sound.icon} size={20} />
                  </span>
                  <span>
                    <strong>{sound.name}</strong>
                    <small>{sound.kind === 'builtin' ? 'Built-in' : 'Custom'}</small>
                  </span>
                  <button
                    className={`switch ${isSoundVisible(sound, preferences) ? 'on' : ''}`}
                    aria-label={`Toggle ${sound.name}`}
                    onClick={() => void toggleSound(sound.sound_id, !isSoundVisible(sound, preferences))}
                  >
                    <span />
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <div className="sounds-empty">
              <span className="empty-plus">+</span>
              <h2>Add your first sound</h2>
              <p>You haven’t saved any sounds yet. Record a few examples to get started.</p>
              <button className="primary" onClick={() => setScreen('teach')}>
                <span aria-hidden="true">+</span> Teach a sound
              </button>
            </div>
          )}
        </section>

        <aside className="info-card card">
          <span className="info-icon">i</span>
          <h2>Private by design</h2>
          <p>Only sounds louder than your room are analyzed. Audio is never stored.</p>
          <hr />
          <p>
            <strong>Keep this tab visible.</strong>
            <br />
            Browsers may limit microphone access when your screen is locked or the tab is hidden.
          </p>
          <div className="alert-demo">
            <button onClick={() => setScreen('recognized')}>Preview recognized alert</button>
            <button onClick={() => setScreen('unknown')}>Preview unknown alert</button>
          </div>
        </aside>
      </div>
    </div>
  );
}

function Teach({
  setScreen,
  recordings,
  name,
  setName,
  selectedIcon,
  setSelectedIcon,
  readyToSave,
  saveState,
  saveError,
  startRecording,
  saveSound,
  deleteRecording,
}: {
  setScreen: (s: Screen) => void;
  recordings: RecordingStep[];
  name: string;
  setName: (value: string) => void;
  selectedIcon: IconName;
  setSelectedIcon: (value: IconName) => void;
  readyToSave: boolean;
  saveState: 'idle' | 'saving' | 'saved' | 'error';
  saveError: string | null;
  startRecording: (index: number) => void;
  saveSound: () => void;
  deleteRecording: (index: number) => void;
}) {
  const completed = countCompletedRecordings(recordings);

  return (
    <div className="page">
      <div className="title-row">
        <div>
          <p className="eyebrow">PERSONAL SOUND LIBRARY</p>
          <h1>Teach a sound</h1>
          <p>Record a few examples so HearAlert can recognize a sound you know.</p>
        </div>
        <span className="step-label">{completed} of 4 recordings</span>
      </div>

      <div className="teach-grid">
        <div className="teach-left">
          <section className="card form-section">
            <span className="step">1</span>
            <div className="step-content">
              <h2>Sound name</h2>
              <label htmlFor="soundName">Use a clear, descriptive name</label>
              <input id="soundName" value={name} onChange={(event) => setName(event.target.value)} />
            </div>
          </section>

          <section className="card form-section">
            <span className="step">2</span>
            <div className="step-content">
              <h2>Choose an icon</h2>
              <div className="icon-grid">
                {categories.map((category) => (
                  <button key={category.icon} className={selectedIcon === category.icon ? 'selected' : ''} onClick={() => setSelectedIcon(category.icon)}>
                    <Icon name={category.icon} />
                    <small>{category.name}</small>
                  </button>
                ))}
              </div>
            </div>
          </section>

          <section className="card form-section">
            <span className="step">3</span>
            <div className="step-content">
              <h2>Record examples</h2>
              <p>Start with Example 1. We’ll guide you through every recording automatically. Completed clips remain in memory until this session ends.</p>
              <div className="record-list">
                {['Example 1', 'Example 2', 'Example 3', 'Room noise'].map((label, index) => (
                  <div className="record-item" key={label}>
                    <div className="record-summary">
                      <span className={`record-state ${recordings[index]?.blob ? 'done' : ''}`}>{recordings[index]?.blob ? <Icon name="check" size={16} /> : index + 1}</span>
                      <span>
                        <strong>{label}</strong>
                        <small>
                          {index === 3 ? '10 seconds' : '3 seconds'} · {recordings[index]?.blob ? 'Completed' : index === 0 ? 'Ready' : 'Upcoming'}
                        </small>
                      </span>
                    </div>

                    {recordings[index]?.blob ? (
                      <>
                        <PlaybackControl label={label.toLowerCase()} blob={recordings[index].blob} duration={index === 3 ? 10 : 3} />
                        <div className="record-actions">
                          <button onClick={() => startRecording(index)}>Re-record</button>
                          <button onClick={() => deleteRecording(index)}>Delete audio</button>
                        </div>
                      </>
                    ) : (
                      <button className="record-next" onClick={() => startRecording(index)}>
                        Record <span>›</span>
                      </button>
                    )}
                  </div>
                ))}
              </div>
              {completed === 0 && (
                <button className="primary begin-recording" onClick={() => startRecording(0)}>
                  <Icon name="voice" />
                  Begin recording
                </button>
              )}
            </div>
          </section>
        </div>

        <aside className="teach-side card">
          <div className="preview-icon">
            <Icon name={selectedIcon} size={48} />
          </div>
          <p>Sound preview</p>
          <h2>{name.trim() || 'Untitled sound'}</h2>
          <div className="progress-wrap">
            <div>
              <span>Recording progress</span>
              <strong>{completed}/4</strong>
            </div>
            <div className="progress">
              <span style={{ width: `${(completed / 4) * 100}%` }} />
            </div>
          </div>
          <button className="primary" disabled={!readyToSave || saveState === 'saving'} onClick={saveSound}>
            {saveState === 'saving' ? 'Saving…' : saveState === 'saved' ? <><Icon name="check" />Sound saved</> : 'Save and check sound'}
          </button>
          {saveError ? <p role="alert" className="recording-error">{saveError}</p> : null}
          <p className="side-help">{saveState === 'saved' ? 'Your sound is saved and ready to use.' : saveState === 'error' ? 'The save request failed. Check the recordings and try again.' : 'Complete the guided recording to continue.'}</p>
        </aside>
      </div>
    </div>
  );
}

function Recording({ setScreen, index, completeRecording }: { setScreen: (s: Screen) => void; index: number; completeRecording: (index: number, blob: Blob) => void }) {
  const duration = index === 3 ? 10 : 3;
  const [time, setTime] = useState(duration);
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!recording || time === 0) return;
    const id = window.setTimeout(() => setTime((current) => current - 1), 1000);
    return () => window.clearTimeout(id);
  }, [recording, time]);

  const elapsed = duration - time;

  const startOrStopRecording = async () => {
    if (recording) {
      setRecording(false);
      setTime(0);
      return;
    }

    setError(null);
    setRecording(true);
    try {
      const blob = await recordMicrophoneClip(duration * 1000);
      setTime(0);
      setRecording(false);
      completeRecording(index, blob);
      setScreen('teach');
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : 'Unable to record microphone audio.';
      setError(message);
      setRecording(false);
      setTime(duration);
    }
  };

  return (
    <div className="page recording-page">
      <button className="back" onClick={() => setScreen('teach')}>
        ← Back to sound
      </button>
      <p className="eyebrow">{index === 3 ? 'ROOM NOISE' : `EXAMPLE ${index + 1}`} OF 4</p>
      <h1>{index === 3 ? 'Record room noise' : 'Record an example'}</h1>
      <p>
        {index === 3
          ? 'Final step: capture the normal background sound in this room.'
          : 'Make your sound during the 3-second recording. The recording will return to the Teach screen when complete.'}
      </p>

      <section className={`record-panel card ${recording ? 'is-recording' : ''}`}>
        <div className="record-orbit">
          <div className="mic-core">
            <Icon name="voice" size={58} />
          </div>
        </div>

        <h2>
          {recording ? (time ? `0:${String(elapsed).padStart(2, '0')} / 0:${String(duration).padStart(2, '0')}` : 'Recording complete') : 'Ready when you are'}
        </h2>

        <div className="wave" aria-label="Recording level">
          {[16, 30, 44, 60, 72, 52, 64, 38, 55, 66, 42, 30, 20].map((height, itemIndex) => (
            <i key={itemIndex} style={{ height: `${height}px` }} />
          ))}
        </div>

        {error ? <p role="alert" className="recording-error">{error}</p> : null}

        <button className="primary record-button" onClick={startOrStopRecording}>
          {recording ? '■ Stop recording' : <><Icon name="voice" />Start recording</>}
        </button>
      </section>
    </div>
  );
}

function History({ events }: { events: HistoryEvent[] }) {
  const formatTime = (value: string) => {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return value;
    }

    return new Intl.DateTimeFormat(undefined, {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    }).format(date);
  };

  return (
    <div className="page">
      <div className="title-row">
        <div>
          <p className="eyebrow">ACTIVITY</p>
          <h1>History</h1>
          <p>Recent detections from this device.</p>
        </div>
        <button className="secondary">Filter: All events</button>
      </div>

      <section className="card history-card">
        <div className="history-head">
          <span>Time</span>
          <span>Sound</span>
          <span>Type</span>
          <span>Clip</span>
        </div>

        {events.length === 0 ? (
          <div className="sounds-empty">
            <span className="empty-plus">+</span>
            <h2>No activity yet</h2>
            <p>When the app detects a sound, it will show up here.</p>
          </div>
        ) : (
          events.map((event, index) => (
            <div className="history-row" key={event.event_id ?? `${event.at}-${index}`}>
              <time>{formatTime(event.at)}</time>
              <span className="event-name">
                <span className={`event-icon ${event.kind.toLowerCase()}`}>
                  <Icon name={event.label?.includes('door') ? 'door' : event.label?.includes('dog') ? 'dog' : event.kind === 'unknown' ? 'generic' : 'warning'} />
                </span>
                <span>
                  <strong>{event.label ?? 'Unknown sound'}</strong>
                  <small>{event.confidence == null ? 'Confidence unavailable' : `${Math.round(event.confidence * 100)}% confidence`}</small>
                </span>
              </span>
              <span>
                <b className={`type ${event.kind.toLowerCase()}`}>{event.kind === 'none' ? 'None' : event.kind === 'unknown' ? 'Unknown' : event.kind === 'taught' ? 'Recognized' : 'Attention'}</b>
              </span>
              <span className="history-playback">
                <PlaybackControl label={(event.label ?? 'detected sound').toLowerCase()} duration={3} available={false} compact />
              </span>
            </div>
          ))
        )}
      </section>

      <p className="history-foot">This view reflects the current API history. Nothing is stored locally unless the backend keeps it.</p>
    </div>
  );
}

function Alert({ type, dismiss, teach }: { type: 'recognized' | 'unknown' | 'attention'; dismiss: () => void; teach: () => void }) {
  const data =
    type === 'recognized'
      ? { icon: 'door' as const, kicker: 'RECOGNIZED SOUND', title: 'Door knock', sub: '94% confidence', note: 'Detected just now' }
      : type === 'unknown'
        ? { icon: 'generic' as const, kicker: 'UNKNOWN SOUND', title: 'What was that?', sub: 'Possibly a metallic object falling', note: 'This is a tentative description' }
        : { icon: 'warning' as const, kicker: 'ATTENTION SOUND', title: 'Alarm-like sound', sub: 'This sound may need your attention', note: 'HearAlert has not confirmed an emergency' };

  return (
    <main className={`alert-screen ${type}`}>
      <div className="alert-top">
        <Brand />
        <span>Alert remains visible until dismissed</span>
      </div>
      <div className="alert-content">
        <div className="alert-icon">
          <Icon name={data.icon} size={76} />
        </div>
        <p className="alert-kicker">{data.kicker}</p>
        <h1>{data.title}</h1>
        <p className="alert-sub">{data.sub}</p>
        <p className="alert-note">{data.note}</p>

        {type === 'unknown' && (
          <div className="alert-playback">
            <PlaybackControl label="detected sound" duration={4} />
            <small>Simulated detected clip · retained in memory for this demo session</small>
          </div>
        )}

        <div className="alert-actions">
          {type === 'unknown' && (
            <button className="alert-secondary" onClick={teach}>
              Teach this sound
            </button>
          )}
          <button className="alert-dismiss" onClick={dismiss}>
            Dismiss alert
          </button>
        </div>
      </div>
    </main>
  );
}

export default function App() {
  const [screen, setScreen] = useState<Screen>('listen');
  const [dark, setDark] = useState(false);
  const [recordings, setRecordings] = useState<RecordingStep[]>([
    { blob: null, valid: false },
    { blob: null, valid: false },
    { blob: null, valid: false },
    { blob: null, valid: false },
  ]);
  const [recordingIndex, setRecordingIndex] = useState(0);
  const [soundName, setSoundName] = useState('');
  const [selectedIcon, setSelectedIcon] = useState<IconName>('door');
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [saveError, setSaveError] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [sounds, setSounds] = useState<SoundRecord[]>([]);
  const [history, setHistory] = useState<HistoryEvent[]>([]);
  const [preferences, setPreferences] = useState<Record<string, boolean>>(() => readStoredSoundPreferences());

  useEffect(() => {
    try {
      window.localStorage.setItem(SOUND_PREFS_KEY, JSON.stringify(preferences));
    } catch {
      // Ignore private-mode/localStorage write failures and keep the app usable.
    }
  }, [preferences]);

  useEffect(() => {
    const loadData = async () => {
      try {
        const [nextHealth, nextSounds, nextHistory] = await Promise.all([getHealth(), getSounds(), getHistory()]);
        setHealth(nextHealth);
        setSounds(nextSounds.sounds.map((sound) => ({
          ...sound,
          enabled: sound.kind === 'builtin' ? (preferences[sound.sound_id] ?? sound.enabled) : sound.enabled,
        })));
        setHistory(nextHistory.events.filter((event) => {
          if (!event.sound_id) {
            return true;
          }
          const matching = nextSounds.sounds.find((sound) => sound.sound_id === event.sound_id);
          if (!matching) {
            return true;
          }
          return isSoundVisible(matching, preferences);
        }));
      } catch (error) {
        console.error('Failed to load app data:', error);
        setHealth(null);
        setSounds([]);
        setHistory([]);
      }
    };

    void loadData();
  }, [preferences]);

  const readyToSave = isReadyToSave(soundName, recordings);

  const startRecording = (index: number) => {
    setRecordingIndex(index);
    setScreen('record');
  };

  const completeRecording = (index: number, blob: Blob) => {
    setRecordings((current) => current.map((recording, recordingIndex) => (recordingIndex === index ? { blob, valid: true } : recording)));
    setSaveState('idle');
    setSaveError(null);
    if (index < 3) {
      setRecordingIndex(index + 1);
    }
  };

  const deleteRecording = (index: number) => {
    setRecordings((current) => current.map((recording, itemIndex) => (itemIndex === index ? { blob: null, valid: false } : recording)));
    setSaveState('idle');
    setSaveError(null);
  };

  const saveSound = async () => {
    if (!readyToSave || saveState === 'saving') {
      return;
    }

    setSaveState('saving');
    setSaveError(null);

    try {
      const payload = new FormData();
      payload.append('name', soundName.trim());
      payload.append('icon', selectedIcon);

      recordings.forEach((recording, index) => {
        if (!recording.blob) {
          throw new Error(`Missing required recording ${index + 1}.`);
        }

        const fieldName = index === 3 ? 'room' : `example_${index + 1}`;
        payload.append(fieldName, recording.blob, `${fieldName}.wav`);
      });

      const response = await teachSound(payload);
      const nextSounds = await getSounds();
      setSounds(nextSounds.sounds.map((sound) => ({
        ...sound,
        enabled: sound.kind === 'builtin' ? (preferences[sound.sound_id] ?? sound.enabled) : sound.enabled,
      })));
      setSaveState('saved');
      setSaveError(null);
      setSoundName(response.name);
      setSelectedIcon(response.icon);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'The sound could not be saved. Please try again.';
      setSaveState('error');
      setSaveError(message);
    }
  };

  const toggleSound = async (soundId: string, enabled: boolean) => {
    try {
      const updated = await updateSound(soundId, { enabled });
      setSounds((current) => current.map((sound) => (sound.sound_id === soundId ? { ...sound, enabled: updated.enabled } : sound)));
      setPreferences((current) => ({ ...current, [soundId]: updated.enabled }));
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to update this sound.';
      setSaveError(message);
    }
  };

  if (['recognized', 'unknown', 'attention'].includes(screen)) {
    return <Alert type={screen as 'recognized' | 'unknown' | 'attention'} dismiss={() => setScreen('listen')} teach={() => setScreen('teach')} />;
  }

  return (
    <div className={dark ? 'theme-dark' : ''}>
      <Shell screen={screen} setScreen={setScreen} dark={dark} setDark={setDark}>
        {screen === 'listen' ? (
          <Listen setScreen={setScreen} health={health} sounds={sounds} toggleSound={toggleSound} preferences={preferences} />
        ) : screen === 'teach' ? (
          <Teach
            setScreen={setScreen}
            recordings={recordings}
            name={soundName}
            setName={setSoundName}
            selectedIcon={selectedIcon}
            setSelectedIcon={setSelectedIcon}
            readyToSave={readyToSave}
            saveState={saveState}
            saveError={saveError}
            startRecording={startRecording}
            saveSound={saveSound}
            deleteRecording={deleteRecording}
          />
        ) : screen === 'record' ? (
          <Recording key={recordingIndex} setScreen={setScreen} index={recordingIndex} completeRecording={completeRecording} />
        ) : (
          <History events={history} />
        )}
      </Shell>
    </div>
  );
}
