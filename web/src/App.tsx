import { useEffect, useRef, useState } from 'react'

import { explainMicrophoneError, recordMicrophoneClip } from './audio/recorder'
import { DEFAULT_BUILTIN_SOUNDS, mergeBuiltinsWithSaved, type GuestSound } from './teach-state'

type Screen = 'home' | 'listen' | 'teach' | 'record' | 'history' | 'sounds' | 'account' | 'auth' | 'recognized' | 'unknown' | 'attention'
type AuthMode = 'signin' | 'create' | 'verify' | 'forgot' | 'reset' | 'expired'
type IconName = 'door' | 'bell' | 'alarm' | 'baby' | 'dog' | 'kettle' | 'microwave' | 'phone' | 'voice' | 'glass' | 'siren' | 'water' | 'generic'

type GuestHistoryEvent = {
  event_id: string;
  at: string;
  kind: 'builtin' | 'taught' | 'unknown' | 'none';
  label: string | null;
  sound_id: string | null;
  confidence: number | null;
  description: string | null;
}

const STORAGE_KEYS = {
  builtins: 'hear-for-you-builtins',
  custom: 'hear-for-you-custom-sounds',
  history: 'hear-for-you-history',
} as const

const iconPaths: Record<IconName | 'home' | 'account' | 'history' | 'moon' | 'pause' | 'check' | 'warning', React.ReactNode> = {
  door: <><path d="M5 21V4a1 1 0 0 1 1-1h11a1 1 0 0 1 1 1v17"/><path d="M3 21h18M14 12h.01"/></>,
  bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/></>,
  alarm: <><circle cx="12" cy="13" r="8"/><path d="M12 9v4l2 2M5 3 2 6M19 3l3 3"/></>,
  baby: <><circle cx="12" cy="8" r="4"/><path d="M8 7c-2-2-2-4 1-5M6 14c1 5 11 5 12 0M9 13h.01M15 13h.01"/></>,
  dog: <><path d="M5 11 3 6l5 2a7 7 0 0 1 8 0l5-2-2 5v5a4 4 0 0 1-4 4H9a4 4 0 0 1-4-4zM9 13h.01M15 13h.01M10 17h4"/></>,
  kettle: <><path d="M6 8h10v11H6zM8 5h6M16 10c4 0 5 2 5 4s-2 4-5 4M4 10h2"/></>,
  microwave: <><rect x="2" y="5" width="20" height="14" rx="2"/><path d="M14 8h5v8h-5zM5 9h6v6H5z"/></>,
  phone: <><rect x="6" y="2" width="12" height="20" rx="2"/><path d="M10 18h4"/></>,
  voice: <><path d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3M5 11a7 7 0 0 0 14 0M12 18v4"/></>,
  glass: <><path d="m5 3 2 8h4l-2 10M19 3l-2 8h-4l2 10M5 3h14"/></>,
  siren: <><path d="M6 17h12l-1-8a5 5 0 0 0-10 0zM4 21h16M12 2V0M3 6 1 5M21 6l2-1"/></>,
  water: <><path d="M12 2S5 10 5 15a7 7 0 0 0 14 0c0-5-7-13-7-13zM9 16a3 3 0 0 0 3 3"/></>,
  generic: <><path d="M4 12h2l2-6 4 12 3-9 2 3h3"/></>,
  home: <><path d="m3 11 9-8 9 8"/><path d="M5 10v10h14V10M9 20v-6h6v6"/></>,
  account: <><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></>,
  history: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
  moon: <path d="M20 15a8 8 0 1 1-11-11 7 7 0 0 0 11 11z"/>,
  pause: <><path d="M8 5v14M16 5v14"/></>,
  check: <path d="m5 12 4 4L19 6"/>,
  warning: <><path d="M12 3 2 21h20zM12 9v5M12 18h.01"/></>,
}

function Icon({ name, size = 22 }: { name: keyof typeof iconPaths; size?: number }) {
  return <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{iconPaths[name]}</svg>
}

function readStoredValue<T>(key: string, fallback: T): T {
  if (typeof window === 'undefined') return fallback
  try {
    const raw = window.localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}

function writeStoredValue<T>(key: string, value: T) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // Ignore local storage write failures in private browsing or restricted browser modes.
  }
}

function PlaybackControl({ label, duration, available = true, compact = false }: { label:string; duration:number; available?:boolean; compact?:boolean }) {
  const [playing, setPlaying] = useState(false)
  const [progress, setProgress] = useState(0)
  useEffect(() => {
    if (!playing) return
    const timer = window.setInterval(() => setProgress(current => {
      const next = Math.min(duration, current + .25)
      if (next >= duration) setPlaying(false)
      return next
    }), 250)
    return () => window.clearInterval(timer)
  }, [playing, duration])
  if (!available) return <span className="playback-unavailable">No retained clip</span>
  const toggle = () => {
    if (progress >= duration) setProgress(0)
    setPlaying(!playing)
  }
  return <div className={`playback ${compact ? 'compact' : ''}`}>
    <button className="play-button" onClick={toggle} aria-label={`${playing ? 'Pause' : 'Play'} ${label} demo recording`}>{playing ? 'Ⅱ' : '▶'}</button>
    <div className="playback-details"><div><span>{playing ? 'Playing demo' : 'Demo preview'}</span><time>{Math.floor(progress / 60)}:{String(Math.floor(progress % 60)).padStart(2,'0')} / 0:{String(duration).padStart(2,'0')}</time></div><div className="playback-track" role="progressbar" aria-label={`${label} playback progress`} aria-valuemin={0} aria-valuemax={duration} aria-valuenow={Math.round(progress)}><span style={{width:`${progress / duration * 100}%`}}/></div></div>
  </div>
}

const categories: { name: string; icon: IconName }[] = [
  ['Door', 'door'], ['Bell', 'bell'], ['Alarm', 'alarm'], ['Baby', 'baby'], ['Dog', 'dog'], ['Kettle', 'kettle'], ['Microwave', 'microwave'],
  ['Phone', 'phone'], ['Voice', 'voice'], ['Glass', 'glass'], ['Siren', 'siren'], ['Water', 'water'], ['Other', 'generic'],
].map(([name, icon]) => ({ name, icon: icon as IconName }))

function Brand() {
  return <div className="brand"><span className="brand-mark"><i/><i/><i/><i/></span><strong>hear for you.</strong></div>
}

function Sidebar({ screen, navigate }: { screen: Screen; navigate: (s: Screen) => void }) {
  return <aside className="sidebar">
    <Brand />
    <nav aria-label="Main navigation">
      <button className={screen === 'home' ? 'active' : ''} onClick={() => navigate('home')}><Icon name="home"/>Home</button>
      <button className={screen === 'listen' ? 'active' : ''} onClick={() => navigate('listen')}><Icon name="voice"/>Listen</button>
      <button className={screen === 'teach' || screen === 'record' ? 'active' : ''} onClick={() => navigate('teach')}><Icon name="generic"/>Teach</button>
      <button className={screen === 'sounds' ? 'active' : ''} onClick={() => navigate('sounds')}><Icon name="bell"/>My Sounds</button>
      <button className={screen === 'history' ? 'active' : ''} onClick={() => navigate('history')}><Icon name="history"/>History</button>
      <button className={screen === 'auth' ? 'active' : ''} onClick={() => navigate('auth')}><Icon name="account"/>Login</button>
    </nav>
    <div className="sidebar-note"><Icon name="moon"/><span>Screen stays awake<br/><small>While listening</small></span></div>
  </aside>
}

function Shell({ children, screen, navigate, dark, setDark }: React.PropsWithChildren<{screen: Screen; navigate: (s: Screen) => void; dark: boolean; setDark: (v:boolean)=>void}>) {
  return <div className="app-shell"><Sidebar screen={screen} navigate={navigate}/><main className="main"><header className="topbar"><div className="mobile-brand"><Brand/></div><span className="topbar-motto">Here when it matters. Hearing what matters.</span><button className="theme-toggle" aria-label="Toggle color theme" onClick={() => setDark(!dark)}><Icon name="moon"/><span>{dark ? 'Light' : 'Dark'} theme</span></button></header>{children}</main></div>
}

function Home({ goToTeach, goToListen }: { goToTeach: () => void; goToListen: () => void }) {
  return <div className="page home-page"><section className="home-hero"><div><p className="eyebrow">PERSONALIZED SOUND AWARENESS</p><h1>Here when it matters.<br/>Hearing what matters.</h1><h2>Stay connected to the sounds that matter.</h2><p>Hear For You helps you recognize important sounds around you through personalized detection and clear visual alerts — so you can stay aware, informed, and in control.</p><div className="hero-actions"><button className="primary" onClick={goToTeach}>Get Started</button><button className="secondary" onClick={goToListen}>Open Listen</button></div></div><aside className="hero-status card"><div className="hero-mark"><span className="brand-mark"><i/><i/><i/><i/></span></div><p>Here when it matters. Hearing what matters.</p><h2>Clear alerts. Personal sounds. More confidence in your surroundings.</h2><div className="hero-feature"><Icon name="voice"/><span><strong>Stay aware</strong><small>Visual alerts for sounds around you</small></span></div><div className="hero-feature"><Icon name="generic"/><span><strong>Make it personal</strong><small>Teach the sounds that matter to you</small></span></div><div className="hero-feature"><Icon name="warning"/><span><strong>Stay in control</strong><small>Clear labels without unnecessary alarm</small></span></div></aside></section></div>
}

function Listen({ setScreen, builtins, customSounds }: { setScreen: (s:Screen)=>void; builtins: GuestSound[]; customSounds: GuestSound[] }) {
  const [status, setStatus] = useState<'active'|'paused'|'reconnecting'|'denied'>('active')
  const statusText = { active: 'Listening now', paused: 'Listening paused', reconnecting: 'Reconnecting…', denied: 'Microphone access needed' }[status]
  const visibleSounds = [...builtins.filter((sound) => sound.enabled), ...customSounds.filter((sound) => sound.enabled)]

  return <div className="page listen-page">
    <div className="title-row"><div><p className="eyebrow">LIVE AWARENESS</p><h1>Listen</h1><p>Stay aware of the sounds around you.</p></div><span className={`status-pill ${status}`}><span/>{statusText}</span></div>
    {status === 'denied' ? <section className="permission card"><Icon name="warning" size={30}/><div><h2>Allow microphone access</h2><p>Hear For You needs permission to analyze nearby sound on this device. Live microphone audio is not continuously saved.</p></div><button onClick={()=>setStatus('active')} className="primary">Try again</button></section> :
    <section className={`listener card ${status}`}>
      <div className="sound-orbit"><div className="level-ring"/><div className="mic-core"><Icon name="voice" size={52}/></div></div>
      <h2>{statusText}</h2><p className="room-level"><span className="level-bars"><i/><i/><i/><i/><i/></span>Room level: <strong>{status === 'paused' ? '—' : 'Quiet'}</strong></p>
      <div className="listener-actions"><button className="primary" onClick={()=>setStatus(status==='paused'?'active':'paused')}><Icon name={status==='paused'?'voice':'pause'}/>{status==='paused'?'Resume listening':'Pause listening'}</button><button className="secondary" onClick={()=>setStatus('reconnecting')}>Reconnect</button></div>
    </section>}
    <div className="dashboard-grid">
      <section className="card sounds-card"><div className="section-head"><div><h2>Your sounds</h2><p>Enabled sound categories and saved sounds appear here.</p></div></div>
        {visibleSounds.length === 0 ? <div className="sounds-empty"><span className="empty-plus">+</span><h2>No active sounds yet</h2><p>Turn on a built-in sound or save a custom one to start listening.</p><button className="primary" onClick={()=>setScreen('teach')}><span aria-hidden="true">+</span> Teach a sound</button></div> : <div className="sound-list">{visibleSounds.slice(0, 6).map((sound) => <div className="sound-row" key={sound.sound_id}><span className="sound-icon"><Icon name={sound.icon as IconName}/></span><span><strong>{sound.name}</strong><small>{sound.kind === 'builtin' ? 'Built-in category' : 'Saved sound'}</small></span><button className="text-button" onClick={()=>setScreen('sounds')}>View</button></div>)}</div>}
      </section>
      <aside className="info-card card"><span className="info-icon">i</span><h2>Private by design</h2><p>Only loud sounds are analyzed. Audio is never stored permanently in your browser session.</p><hr/><p><strong>Keep this tab visible.</strong><br/>Browsers may limit microphone access when your screen is locked or the tab is hidden.</p></aside>
    </div>
  </div>
}

function Teach({ setScreen, done, saved, startRecording, saveSound, deleteRecording }: { setScreen:(s:Screen)=>void; done:boolean[]; saved:boolean; startRecording:(index:number)=>void; saveSound:(payload:{name:string; icon:IconName})=>void; deleteRecording:(index:number)=>void }) {
  const [selected, setSelected] = useState<IconName>('door')
  const [name, setName] = useState('Door knock')
  const handleSave = () => saveSound({ name, icon: selected })

  return <div className="page"><div className="title-row"><div><p className="eyebrow">PERSONAL SOUND LIBRARY</p><h1>Teach a sound</h1><p>Teach Hear For You the sounds that matter to you.</p></div><span className="step-label">{done.filter(Boolean).length} of 4 recordings</span></div>
    <div className="teach-grid"><div className="teach-left">
      <section className="card form-section"><span className="step">1</span><div className="step-content"><h2>Sound name</h2><label htmlFor="soundName">Use a clear, descriptive name</label><input id="soundName" value={name} onChange={e=>setName(e.target.value)} /></div></section>
      <section className="card form-section"><span className="step">2</span><div className="step-content"><h2>Choose an icon</h2><div className="icon-grid">{categories.map(c=><button key={c.icon} className={selected===c.icon?'selected':''} onClick={()=>setSelected(c.icon)}><Icon name={c.icon}/><small>{c.name}</small></button>)}</div></div></section>
      <section className="card form-section"><span className="step">3</span><div className="step-content"><h2>Record examples</h2><p>Start with Example 1. We’ll guide you through every recording automatically. Completed clips remain in memory until this session ends.</p><div className="record-list">{['Example 1','Example 2','Example 3','Room noise'].map((x,i)=><div className={`record-item ${done[i]?'complete':''}`} key={x}><div className="record-summary"><span className={`record-state ${done[i]?'done':''}`}>{done[i]?<Icon name="check" size={16}/>:i+1}</span><span><strong>{x}</strong><small>{i === 3 ? '10 seconds' : '3 seconds'} · {done[i] ? 'Completed' : i===0 ? 'Ready' : 'Upcoming'}</small></span></div>{done[i]?<><PlaybackControl label={x.toLowerCase()} duration={i===3?10:3}/><div className="record-actions"><button onClick={()=>startRecording(i)}>Re-record</button><button onClick={()=>deleteRecording(i)}>Delete audio</button></div></>:<button className="record-next" onClick={()=>startRecording(i)}>Record <span>›</span></button>}</div>)}</div>{!done.some(Boolean)&&<button className="primary begin-recording" onClick={()=>startRecording(0)}><Icon name="voice"/>Begin recording</button>}</div></section>
    </div><aside className="teach-side card"><div className="preview-icon"><Icon name={selected} size={48}/></div><p>Sound preview</p><h2>{name || 'Untitled sound'}</h2><div className="progress-wrap"><div><span>Recording progress</span><strong>{done.filter(Boolean).length}/4</strong></div><div className="progress"><span style={{width:`${done.filter(Boolean).length*25}%`}}/></div></div><button className="primary" disabled={!done.every(Boolean) || !name.trim() || saved} onClick={handleSave}>{saved?<><Icon name="check"/>Sound saved</>:'Save and check sound'}</button><p className="side-help">{saved?'Your sound is saved and ready to use.':'Complete the guided recording to continue.'}</p></aside></div>
  </div>
}

function Recording({ setScreen, index, saveRecording }: { setScreen:(s:Screen)=>void; index:number; saveRecording:()=>void }) {
  const duration = index === 3 ? 10 : 3
  const [time, setTime] = useState(duration)
  const [recording, setRecording] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    if (!recording) return

    const timer = window.setInterval(() => {
      setTime((current) => {
        if (current <= 1) {
          window.clearInterval(timer)
          return 0
        }
        return current - 1
      })
    }, 1000)

    return () => window.clearInterval(timer)
  }, [recording])

  useEffect(() => {
    return () => {
      abortRef.current?.abort()
    }
  }, [])

  const handleRecording = async () => {
    if (recording) {
      abortRef.current?.abort()
      setRecording(false)
      setTime(duration)
      return
    }

    setError(null)
    setRecording(true)
    setTime(duration)

    const controller = new AbortController()
    abortRef.current = controller

    try {
      await recordMicrophoneClip(duration * 1000, { signal: controller.signal })
      setRecording(false)
      setTime(duration)
      saveRecording()
    } catch (caughtError) {
      setRecording(false)
      setTime(duration)
      setError(explainMicrophoneError(caughtError))
    }
  }

  const elapsed = duration - time
  return <div className="page recording-page"><button className="back" onClick={()=>setScreen('teach')}>← Back to sound</button><p className="eyebrow">{index === 3 ? 'ROOM NOISE' : `EXAMPLE ${index + 1}`} OF 4</p><h1>{index === 3 ? 'Record room noise' : 'Record an example'}</h1><p>{index === 3 ? 'Final step: capture the normal background sound in this room.' : 'Make your sound during the 3-second recording. The next step will open automatically.'}</p>{error && <section className="card permission"><Icon name="warning" size={30}/><div><h2>Microphone unavailable</h2><p>{error}</p></div><button className="primary" onClick={() => setError(null)}>Try again</button></section>} {!error && <section className={`record-panel card ${recording?'is-recording':''}`}><div className="record-orbit"><div className="mic-core"><Icon name="voice" size={58}/></div></div><h2>{recording ? (time ? `0:${String(elapsed).padStart(2,'0')} / 0:${String(duration).padStart(2,'0')}` : 'Recording complete') : 'Ready when you are'}</h2><div className="wave" aria-label="Recording level">{[16,30,44,60,72,52,64,38,55,66,42,30,20].map((h,i)=><i key={i} style={{height:`${h}px`}}/>)}</div>{recording&&time===0?<><button className="primary" onClick={saveRecording}><Icon name="check"/>{index === 3 ? 'Finish and save sound' : 'Use and continue'}</button><button className="secondary" onClick={()=>{setTime(duration);setRecording(false)}}>Re-record</button></>:<button className="primary record-button" onClick={handleRecording}>{recording?'■ Stop recording':<><Icon name="voice"/>Start recording</>}</button>}</section>}</div>
}

function AuthScreen() {
  return <div className="page auth-page"><section className="card auth-card"><p className="eyebrow">GUEST MODE</p><h1>Login is not available</h1><p>Accounts are not available in this version. You can use Hear For You without signing in.</p><button className="primary" onClick={() => window.history.back()}>Continue</button></section></div>
}

function MySounds({ builtinSounds, customSounds, toggleBuiltin, deleteCustom, saveCustom }: { builtinSounds: GuestSound[]; customSounds: GuestSound[]; toggleBuiltin:(soundId:string)=>void; deleteCustom:(soundId:string)=>void; saveCustom:()=>void }) {
  return <div className="page"><div className="title-row"><div><p className="eyebrow">YOUR SOUND LIBRARY</p><h1>Your Sounds</h1><p>Built-in categories and your personal sounds stay available without an account.</p></div><button className="primary" onClick={saveCustom}>+ Add sound</button></div>
    <div className="library-grid">
      <section className="card account-card">
        <h2>Built-In Sounds</h2>
        {builtinSounds.map((sound) => <div className="sound-row" key={sound.sound_id}><span className="sound-icon"><Icon name={sound.icon as IconName}/></span><span><strong>{sound.name}</strong><small>{sound.enabled ? 'Enabled' : 'Disabled'}</small></span><button className={`switch ${sound.enabled ? 'on' : ''}`} aria-label={`${sound.enabled ? 'Disable' : 'Enable'} ${sound.name}`} onClick={() => toggleBuiltin(sound.sound_id)}><span/></button></div>)}
      </section>
      <section className="card account-card">
        <h2>My Taught Sounds</h2>
        {customSounds.length === 0 ? <div className="sounds-empty"><span className="empty-plus">+</span><h2>No custom sounds yet</h2><p>Teach a sound to add it to your library.</p><button className="primary" onClick={saveCustom}>Teach a sound</button></div> : customSounds.map((sound) => <div className="sound-row" key={sound.sound_id}><span className="sound-icon"><Icon name={sound.icon as IconName}/></span><span><strong>{sound.name}</strong><small>{sound.enabled ? 'Active' : 'Disabled'}</small></span><button className="danger-button" onClick={() => deleteCustom(sound.sound_id)}>Delete</button></div>)}
      </section>
    </div>
  </div>
}

function History({ events }: { events: GuestHistoryEvent[] }) {
  const [soundFilter,setSoundFilter]=useState('All')
  const [dateFilter,setDateFilter]=useState('All')
  const [limit,setLimit]=useState(5)

  const filtered = events.filter((event) => {
    const matchesSound = soundFilter === 'All' || event.label === soundFilter
    const matchesDate = dateFilter === 'All' || new Date(event.at).toDateString() === new Date(dateFilter).toDateString()
    return matchesSound && matchesDate
  })

  if (events.length === 0) {
    return <div className="page"><div className="title-row"><div><p className="eyebrow">DETECTION HISTORY</p><h1>History</h1><p>Your genuine detections appear here after a matching event is confirmed.</p></div></div><section className="card history-empty"><h2>No detections yet</h2><p>New detections will appear here after a sound is recognized and enabled.</p></section></div>
  }

  return <div className="page"><div className="title-row"><div><p className="eyebrow">DETECTION HISTORY</p><h1>History</h1><p>Only confirmed detections are stored locally.</p></div></div><section className="card history-filters"><label>Date<select value={dateFilter} onChange={e=>setDateFilter(e.target.value)}><option value="All">All</option>{Array.from(new Set(events.map((event) => event.at.slice(0, 10)))).map((date) => <option key={date} value={date}>{date}</option>)}</select></label><label>Sound<select value={soundFilter} onChange={e=>setSoundFilter(e.target.value)}><option value="All">All</option>{Array.from(new Set(events.map((event) => event.label).filter(Boolean))).map((label) => <option key={label as string} value={label as string}>{label as string}</option>)}</select></label><button className="secondary" onClick={()=>{setDateFilter('All');setSoundFilter('All')}}>Clear filters</button></section><section className="card history-card"><div className="history-head event-only"><span>Date and time</span><span>Original detected label</span><span>Status</span></div>{filtered.slice(0, limit).map((event) => <div className="history-row event-only" key={event.event_id}><time>{new Date(event.at).toLocaleString()}</time><span className="event-name"><span className={`event-icon ${event.kind}`}><Icon name={event.kind === 'unknown' ? 'warning' : event.kind === 'builtin' ? (event.label?.includes('dog') ? 'dog' : 'generic') : 'voice'}/></span><span><strong>{event.label ?? 'Sound detected'}</strong><small>Stored locally</small></span></span><span><b className={`type ${event.kind}`}>{event.kind}</b></span></div>)}{filtered.length === 0 && <div className="history-empty"><h2>No matching results</h2><p>Try clearing one or more filters.</p></div>}</section>{limit < filtered.length && <button className="secondary load-more" onClick={()=>setLimit(limit + 5)}>Load more history</button>}</div>
}

export default function App() {
  const [screen, setScreen] = useState<Screen>('home')
  const [dark, setDark] = useState(false)
  const [recordings, setRecordings] = useState([false, false, false, false])
  const [recordingIndex, setRecordingIndex] = useState(0)
  const [soundSaved, setSoundSaved] = useState(false)
  const [builtinSounds, setBuiltinSounds] = useState<GuestSound[]>(() => mergeBuiltinsWithSaved(readStoredValue<GuestSound[]>(STORAGE_KEYS.builtins, DEFAULT_BUILTIN_SOUNDS)))
  const [customSounds, setCustomSounds] = useState<GuestSound[]>(() => readStoredValue<GuestSound[]>(STORAGE_KEYS.custom, []))
  const [history, setHistory] = useState<GuestHistoryEvent[]>(() => readStoredValue<GuestHistoryEvent[]>(STORAGE_KEYS.history, []))

  useEffect(() => { writeStoredValue(STORAGE_KEYS.builtins, builtinSounds) }, [builtinSounds])
  useEffect(() => { writeStoredValue(STORAGE_KEYS.custom, customSounds) }, [customSounds])
  useEffect(() => { writeStoredValue(STORAGE_KEYS.history, history) }, [history])

  const saveCustomSound = ({ name, icon }: { name: string; icon: IconName }) => {
    const trimmed = name.trim()
    if (!trimmed) return

    const nextSound: GuestSound = {
      sound_id: `snd_${Date.now()}`,
      name: trimmed,
      icon,
      kind: 'taught',
      enabled: true,
    }

    setCustomSounds((current) => [nextSound, ...current])
    setSoundSaved(true)
    setScreen('sounds')
  }

  const startRecording = (index: number) => {
    setRecordingIndex(index)
    setScreen('record')
  }

  const saveRecording = () => {
    setRecordings((current) => current.map((saved, index) => index === recordingIndex ? true : saved))
    if (recordingIndex < 3) {
      setRecordingIndex(recordingIndex + 1)
    } else {
      setSoundSaved(false)
      setScreen('teach')
    }
  }

  const toggleBuiltin = (soundId: string) => {
    setBuiltinSounds((current) => current.map((sound) => sound.sound_id === soundId ? { ...sound, enabled: !sound.enabled } : sound))
  }

  const deleteCustom = (soundId: string) => {
    setCustomSounds((current) => current.filter((sound) => sound.sound_id !== soundId))
  }

  const navigate = (next: Screen) => {
    setScreen(next)
  }

  if (screen === 'auth') {
    return <div className={dark ? 'theme-dark' : ''}><Shell screen={screen} navigate={navigate} dark={dark} setDark={setDark}><AuthScreen /></Shell></div>
  }

  return <div className={dark ? 'theme-dark' : ''}><Shell screen={screen} navigate={navigate} dark={dark} setDark={setDark}>{screen === 'home' ? <Home goToTeach={() => setScreen('teach')} goToListen={() => setScreen('listen')} /> : screen === 'listen' ? <Listen setScreen={setScreen} builtins={builtinSounds} customSounds={customSounds} /> : screen === 'teach' ? <Teach setScreen={setScreen} done={recordings} saved={soundSaved} startRecording={startRecording} saveSound={saveCustomSound} deleteRecording={(index) => { setRecordings((current) => current.map((value, currentIndex) => currentIndex === index ? false : value)); setSoundSaved(false) }} /> : screen === 'record' ? <Recording key={recordingIndex} setScreen={setScreen} index={recordingIndex} saveRecording={saveRecording} /> : screen === 'sounds' ? <MySounds builtinSounds={builtinSounds} customSounds={customSounds} toggleBuiltin={toggleBuiltin} deleteCustom={deleteCustom} saveCustom={() => setScreen('teach')} /> : screen === 'history' ? <History events={history} /> : <Home goToTeach={() => setScreen('teach')} goToListen={() => setScreen('listen')} />}</Shell></div>
}
