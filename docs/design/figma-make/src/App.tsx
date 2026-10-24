import { useEffect, useState } from 'react'

type Screen = 'listen' | 'teach' | 'record' | 'history' | 'recognized' | 'unknown' | 'attention'
type IconName = 'door' | 'bell' | 'alarm' | 'baby' | 'dog' | 'kettle' | 'microwave' | 'phone' | 'voice' | 'glass' | 'siren' | 'water' | 'generic'

const iconPaths: Record<IconName | 'history' | 'moon' | 'pause' | 'check' | 'warning', React.ReactNode> = {
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
  history: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
  moon: <path d="M20 15a8 8 0 1 1-11-11 7 7 0 0 0 11 11z"/>,
  pause: <><path d="M8 5v14M16 5v14"/></>,
  check: <path d="m5 12 4 4L19 6"/>,
  warning: <><path d="M12 3 2 21h20zM12 9v5M12 18h.01"/></>,
}

function Icon({ name, size = 22 }: { name: keyof typeof iconPaths; size?: number }) {
  return <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{iconPaths[name]}</svg>
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
  return <div className="brand"><span className="brand-mark"><i/><i/><i/><i/></span><strong>HearAlert</strong></div>
}

function Sidebar({ screen, setScreen }: { screen: Screen; setScreen: (s: Screen) => void }) {
  return <aside className="sidebar">
    <Brand />
    <nav aria-label="Main navigation">
      <button className={screen === 'listen' ? 'active' : ''} onClick={() => setScreen('listen')}><Icon name="voice"/>Listen</button>
      <button className={screen === 'teach' || screen === 'record' ? 'active' : ''} onClick={() => setScreen('teach')}><Icon name="generic"/>Teach</button>
      <button className={screen === 'history' ? 'active' : ''} onClick={() => setScreen('history')}><Icon name="history"/>History</button>
    </nav>
    <div className="sidebar-note"><Icon name="moon"/><span>Screen stays awake<br/><small>While listening</small></span></div>
  </aside>
}

function Shell({ children, screen, setScreen, dark, setDark }: React.PropsWithChildren<{screen: Screen; setScreen: (s: Screen) => void; dark: boolean; setDark: (v:boolean)=>void}>) {
  return <div className="app-shell"><Sidebar screen={screen} setScreen={setScreen}/><main className="main"><header className="topbar"><div className="mobile-brand"><Brand/></div><button className="theme-toggle" aria-label="Toggle color theme" onClick={() => setDark(!dark)}><Icon name="moon"/><span>{dark ? 'Light' : 'Dark'} theme</span></button></header>{children}</main></div>
}

function Listen({ setScreen }: { setScreen: (s:Screen)=>void }) {
  const [status, setStatus] = useState<'active'|'paused'|'reconnecting'|'denied'>('active')
  const statusText = { active: 'Listening now', paused: 'Listening paused', reconnecting: 'Reconnecting…', denied: 'Microphone access needed' }[status]
  return <div className="page listen-page">
    <div className="title-row"><div><p className="eyebrow">LIVE AWARENESS</p><h1>Listen</h1><p>Stay aware of the sounds you’ve chosen.</p></div><span className={`status-pill ${status}`}><span/>{statusText}</span></div>
    {status === 'denied' ? <section className="permission card"><Icon name="warning" size={30}/><div><h2>Allow microphone access</h2><p>HearAlert needs permission to analyze nearby sound on this device. Audio is not stored.</p></div><button onClick={()=>setStatus('active')} className="primary">Try again</button></section> :
    <section className={`listener card ${status}`}>
      <div className="sound-orbit"><div className="level-ring"/><div className="mic-core"><Icon name="voice" size={52}/></div></div>
      <h2>{statusText}</h2><p className="room-level"><span className="level-bars"><i/><i/><i/><i/><i/></span>Room level: <strong>{status === 'paused' ? '—' : 'Quiet'}</strong></p>
      <div className="listener-actions"><button className="primary" onClick={()=>setStatus(status==='paused'?'active':'paused')}><Icon name={status==='paused'?'voice':'pause'}/>{status==='paused'?'Resume listening':'Pause listening'}</button><button className="secondary" onClick={()=>setStatus('reconnecting')}>Simulate reconnect</button></div>
    </section>}
    <div className="dashboard-grid">
      <section className="card sounds-card"><div className="section-head"><div><h2>Your sounds</h2><p>Sounds you teach HearAlert will appear here.</p></div></div>
        <div className="sounds-empty"><span className="empty-plus">+</span><h2>Add your first sound</h2><p>You haven’t saved any sounds yet. Record a few examples to get started.</p><button className="primary" onClick={()=>setScreen('teach')}><span aria-hidden="true">+</span> Teach a sound</button></div>
      </section>
      <aside className="info-card card"><span className="info-icon">i</span><h2>Private by design</h2><p>Demo clips are retained temporarily in this browser’s memory for playback and deleted when you refresh or close this session. Nothing is uploaded.</p><hr/><p><strong>Keep this tab visible.</strong><br/>Browsers may limit microphone access when your screen is locked or the tab is hidden.</p><div className="alert-demo"><button onClick={()=>setScreen('recognized')}>Preview recognized alert</button><button onClick={()=>setScreen('unknown')}>Preview unknown alert</button><button onClick={()=>setScreen('attention')}>Preview attention alert</button></div></aside>
    </div>
  </div>
}

function Teach({ setScreen, done, saved, startRecording, saveSound, deleteRecording }: { setScreen:(s:Screen)=>void; done:boolean[]; saved:boolean; startRecording:(index:number)=>void; saveSound:()=>void; deleteRecording:(index:number)=>void }) {
  const [selected, setSelected] = useState<IconName>('door')
  const [name, setName] = useState('Door knock')
  return <div className="page"><div className="title-row"><div><p className="eyebrow">PERSONAL SOUND LIBRARY</p><h1>Teach a sound</h1><p>Record a few examples so HearAlert can recognize a sound you know.</p></div><span className="step-label">{done.filter(Boolean).length} of 4 recordings</span></div>
    <div className="teach-grid"><div className="teach-left">
      <section className="card form-section"><span className="step">1</span><div className="step-content"><h2>Sound name</h2><label htmlFor="soundName">Use a clear, descriptive name</label><input id="soundName" value={name} onChange={e=>setName(e.target.value)} /></div></section>
      <section className="card form-section"><span className="step">2</span><div className="step-content"><h2>Choose an icon</h2><div className="icon-grid">{categories.map(c=><button key={c.icon} className={selected===c.icon?'selected':''} onClick={()=>setSelected(c.icon)}><Icon name={c.icon}/><small>{c.name}</small></button>)}</div></div></section>
      <section className="card form-section"><span className="step">3</span><div className="step-content"><h2>Record examples</h2><p>Start with Example 1. We’ll guide you through every recording automatically. Completed clips remain in memory until this session ends.</p><div className="record-list">{['Example 1','Example 2','Example 3','Room noise'].map((x,i)=><div className={`record-item ${done[i]?'complete':''}`} key={x}><div className="record-summary"><span className={`record-state ${done[i]?'done':''}`}>{done[i]?<Icon name="check" size={16}/>:i+1}</span><span><strong>{x}</strong><small>{i === 3 ? '10 seconds' : '3 seconds'} · {done[i] ? 'Completed' : i===0 ? 'Ready' : 'Upcoming'}</small></span></div>{done[i]?<><PlaybackControl label={x.toLowerCase()} duration={i===3?10:3}/><div className="record-actions"><button onClick={()=>startRecording(i)}>Re-record</button><button onClick={()=>deleteRecording(i)}>Delete audio</button></div></>:<button className="record-next" onClick={()=>startRecording(i)}>Record <span>›</span></button>}</div>)}</div>{!done.some(Boolean)&&<button className="primary begin-recording" onClick={()=>startRecording(0)}><Icon name="voice"/>Begin recording</button>}</div></section>
    </div><aside className="teach-side card"><div className="preview-icon"><Icon name={selected} size={48}/></div><p>Sound preview</p><h2>{name || 'Untitled sound'}</h2><div className="progress-wrap"><div><span>Recording progress</span><strong>{done.filter(Boolean).length}/4</strong></div><div className="progress"><span style={{width:`${done.filter(Boolean).length*25}%`}}/></div></div><button className="primary" disabled={!done.every(Boolean) || !name || saved} onClick={saveSound}>{saved?<><Icon name="check"/>Sound saved</>:'Save and check sound'}</button><p className="side-help">{saved?'Your sound is saved and ready to use.':'Complete the guided recording to continue.'}</p></aside></div>
  </div>
}

function Recording({ setScreen, index, saveRecording }: { setScreen:(s:Screen)=>void; index:number; saveRecording:()=>void }) {
  const duration = index === 3 ? 10 : 3
  const [time, setTime] = useState(duration)
  const [recording, setRecording] = useState(false)
  useEffect(()=>{if(!recording||time===0)return; const id=setTimeout(()=>setTime(time-1),1000);return()=>clearTimeout(id)},[recording,time])
  const elapsed = duration - time
  return <div className="page recording-page"><button className="back" onClick={()=>setScreen('teach')}>← Back to sound</button><p className="eyebrow">{index === 3 ? 'ROOM NOISE' : `EXAMPLE ${index + 1}`} OF 4</p><h1>{index === 3 ? 'Record room noise' : 'Record an example'}</h1><p>{index === 3 ? 'Final step: capture the normal background sound in this room.' : 'Make your sound during the 3-second recording. The next step will open automatically.'}</p><section className={`record-panel card ${recording?'is-recording':''}`}><div className="record-orbit"><div className="mic-core"><Icon name="voice" size={58}/></div></div><h2>{recording ? (time ? `0:${String(elapsed).padStart(2,'0')} / 0:${String(duration).padStart(2,'0')}` : 'Recording complete') : 'Ready when you are'}</h2><div className="wave" aria-label="Recording level">{[16,30,44,60,72,52,64,38,55,66,42,30,20].map((h,i)=><i key={i} style={{height:`${h}px`}}/>)}</div>{recording&&time===0?<><button className="primary" onClick={saveRecording}><Icon name="check"/>{index === 3 ? 'Finish and save sound' : 'Use and continue'}</button><button className="secondary" onClick={()=>{setTime(duration);setRecording(false)}}>Re-record</button></>:<button className="primary record-button" onClick={()=>setRecording(!recording)}>{recording?'■ Stop recording':<><Icon name="voice"/>Start recording</>}</button>}</section></div>
}

function History() {
  const [events, setEvents] = useState([
    {time:'10:24 AM',sound:'Door knock',type:'Recognized',confidence:'94%',clip:true,duration:3},
    {time:'9:18 AM',sound:'Unknown sound',type:'Unknown',confidence:'—',clip:true,duration:4},
    {time:'8:03 AM',sound:'Dog bark',type:'Recognized',confidence:'88%',clip:false,duration:3},
    {time:'Yesterday',sound:'Smoke alarm-like sound',type:'Attention',confidence:'91%',clip:true,duration:5},
    {time:'Yesterday',sound:'Unknown sound',type:'Unknown',confidence:'—',clip:false,duration:3},
  ])
  const deleteClip = (index:number) => setEvents(current => current.map((event,i) => i === index ? {...event,clip:false} : event))
  return <div className="page"><div className="title-row"><div><p className="eyebrow">ACTIVITY</p><h1>History</h1><p>Recent detections from this device. Demo clips are held only in browser memory for this session.</p></div><button className="secondary">Filter: All events</button></div><section className="card history-card"><div className="history-head"><span>Time</span><span>Sound</span><span>Type</span><span>Clip</span></div>{events.map((e,i)=><div className="history-row" key={i}><time>{e.time}</time><span className="event-name"><span className={`event-icon ${e.type.toLowerCase()}`}><Icon name={e.sound.includes('Door')?'door':e.sound.includes('Dog')?'dog':e.type==='Attention'?'warning':'generic'}/></span><span><strong>{e.sound}</strong><small>{e.confidence === '—' ? 'Confidence unavailable' : `${e.confidence} confidence`}</small></span></span><span><b className={`type ${e.type.toLowerCase()}`}>{e.type}</b></span><span className="history-playback"><PlaybackControl label={e.sound.toLowerCase()} duration={e.duration} available={e.clip} compact/>{e.clip&&<button className="delete-clip" onClick={()=>deleteClip(i)} aria-label={`Delete ${e.sound.toLowerCase()} retained audio`}>Delete</button>}</span></div>)}</section><p className="history-foot">Audio shown here is simulated and retained only in memory until you delete it, refresh, or close this session. Nothing is uploaded.</p></div>
}

function Alert({ type, dismiss, teach }: {type:'recognized'|'unknown'|'attention';dismiss:()=>void;teach:()=>void}) {
  const data = type==='recognized' ? { icon:'door' as const, kicker:'RECOGNIZED SOUND', title:'Door knock', sub:'94% confidence', note:'Detected just now' } : type==='unknown' ? {icon:'generic' as const,kicker:'UNKNOWN SOUND',title:'What was that?',sub:'Possibly a metallic object falling',note:'This is a tentative description'} : {icon:'warning' as const,kicker:'ATTENTION SOUND',title:'Alarm-like sound',sub:'This sound may need your attention',note:'HearAlert has not confirmed an emergency'}
  return <main className={`alert-screen ${type}`}><div className="alert-top"><Brand/><span>Alert remains visible until dismissed</span></div><div className="alert-content"><div className="alert-icon"><Icon name={data.icon} size={76}/></div><p className="alert-kicker">{data.kicker}</p><h1>{data.title}</h1><p className="alert-sub">{data.sub}</p><p className="alert-note">{data.note}</p>{type==='unknown'&&<div className="alert-playback"><PlaybackControl label="detected sound" duration={4}/><small>Simulated detected clip · retained in memory for this demo session</small></div>}<div className="alert-actions">{type==='unknown'&&<button className="alert-secondary" onClick={teach}>Teach this sound</button>}<button className="alert-dismiss" onClick={dismiss}>Dismiss alert</button></div></div></main>
}

export default function App() {
  const [screen, setScreen] = useState<Screen>('listen')
  const [dark, setDark] = useState(false)
  const [recordings, setRecordings] = useState([false, false, false, false])
  const [recordingIndex, setRecordingIndex] = useState(0)
  const [soundSaved, setSoundSaved] = useState(false)
  const startRecording = (index: number) => {
    setRecordingIndex(index)
    setScreen('record')
  }
  const saveRecording = () => {
    setRecordings(current => current.map((saved, index) => index === recordingIndex ? true : saved))
    if (recordingIndex < 3) {
      setRecordingIndex(recordingIndex + 1)
    } else {
      setSoundSaved(true)
      setScreen('teach')
    }
  }
  const deleteRecording = (index:number) => {
    setRecordings(current => current.map((saved,i) => i === index ? false : saved))
    setSoundSaved(false)
  }
  if (['recognized','unknown','attention'].includes(screen)) return <Alert type={screen as 'recognized'|'unknown'|'attention'} dismiss={()=>setScreen('listen')} teach={()=>setScreen('teach')}/>
  return <div className={dark?'theme-dark':''}><Shell screen={screen} setScreen={setScreen} dark={dark} setDark={setDark}>{screen==='listen'?<Listen setScreen={setScreen}/>:screen==='teach'?<Teach setScreen={setScreen} done={recordings} saved={soundSaved} startRecording={startRecording} saveSound={()=>setSoundSaved(true)} deleteRecording={deleteRecording}/>:screen==='record'?<Recording key={recordingIndex} setScreen={setScreen} index={recordingIndex} saveRecording={saveRecording}/>:<History/>}</Shell></div>
}
