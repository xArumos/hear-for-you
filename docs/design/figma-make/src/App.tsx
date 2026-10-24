import { useEffect, useState } from 'react'

type Screen = 'home' | 'listen' | 'teach' | 'record' | 'history' | 'sounds' | 'account' | 'auth' | 'recognized' | 'unknown' | 'attention'
type AuthMode = 'signin' | 'create' | 'verify' | 'forgot' | 'reset' | 'expired'
type IconName = 'door' | 'bell' | 'alarm' | 'baby' | 'dog' | 'kettle' | 'microwave' | 'phone' | 'voice' | 'glass' | 'siren' | 'water' | 'generic'

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

function Sidebar({ screen, navigate, signedIn }: { screen: Screen; navigate: (s: Screen) => void; signedIn:boolean }) {
  return <aside className="sidebar">
    <Brand />
    <nav aria-label="Main navigation">
      <button className={screen === 'home' ? 'active' : ''} onClick={() => navigate('home')}><Icon name="home"/>Home</button>
      <button className={screen === 'listen' ? 'active' : ''} onClick={() => navigate('listen')}><Icon name="voice"/>Listen</button>
      <button className={screen === 'teach' || screen === 'record' ? 'active' : ''} onClick={() => navigate('teach')}><Icon name="generic"/>Teach</button>
      <button className={screen === 'sounds' ? 'active' : ''} onClick={() => navigate('sounds')}><Icon name="bell"/>My Sounds</button>
      <button className={screen === 'history' ? 'active' : ''} onClick={() => navigate('history')}><Icon name="history"/>History</button>
      <button className={screen === 'account' || screen === 'auth' ? 'active' : ''} onClick={() => navigate(signedIn?'account':'auth')}><Icon name="account"/>{signedIn?'Account':'Sign in'}</button>
    </nav>
    <div className="sidebar-note"><Icon name="moon"/><span>Screen stays awake<br/><small>While listening</small></span></div>
  </aside>
}

function Shell({ children, screen, navigate, signedIn, dark, setDark }: React.PropsWithChildren<{screen: Screen; navigate: (s: Screen) => void; signedIn:boolean; dark: boolean; setDark: (v:boolean)=>void}>) {
  return <div className="app-shell"><Sidebar screen={screen} navigate={navigate} signedIn={signedIn}/><main className="main"><header className="topbar"><div className="mobile-brand"><Brand/></div><span className="topbar-motto">Here when it matters. Hearing what matters.</span><span className="prototype-badge">Prototype · simulated data</span><button className="theme-toggle" aria-label="Toggle color theme" onClick={() => setDark(!dark)}><Icon name="moon"/><span>{dark ? 'Light' : 'Dark'} theme</span></button></header>{children}</main></div>
}

function Home({ signedIn, getStarted, demo, dashboard }: {signedIn:boolean;getStarted:()=>void;demo:()=>void;dashboard:()=>void}) {
  return <div className="page home-page"><section className="home-hero"><div><p className="eyebrow">PERSONALIZED SOUND AWARENESS</p><h1>Here when it matters.<br/>Hearing what matters.</h1><h2>Stay connected to the sounds that matter.</h2><p>Hear For You helps you recognize important sounds around you through personalized detection and clear visual alerts — so you can stay aware, informed, and in control.</p><div className="hero-actions"><button className="primary" onClick={signedIn?dashboard:getStarted}>{signedIn?'Go to Dashboard':'Get Started'}</button><button className="secondary" onClick={demo}>Try Live Demo</button></div><small>Sound detection, accounts, and storage are simulated in this prototype.</small></div><aside className="hero-status card"><div className="hero-mark"><span className="brand-mark"><i/><i/><i/><i/></span></div><p>Here when it matters. Hearing what matters.</p><h2>Clear alerts. Personal sounds. More confidence in your surroundings.</h2><div className="hero-feature"><Icon name="voice"/><span><strong>Stay aware</strong><small>Visual alerts for sounds around you</small></span></div><div className="hero-feature"><Icon name="generic"/><span><strong>Make it personal</strong><small>Teach the sounds that matter to you</small></span></div><div className="hero-feature"><Icon name="warning"/><span><strong>Stay in control</strong><small>Clear labels without unnecessary alarm</small></span></div></aside></section></div>
}

function Listen({ setScreen }: { setScreen: (s:Screen)=>void }) {
  const [status, setStatus] = useState<'active'|'paused'|'reconnecting'|'denied'>('active')
  const statusText = { active: 'Listening now', paused: 'Listening paused', reconnecting: 'Reconnecting…', denied: 'Microphone access needed' }[status]
  return <div className="page listen-page">
    <div className="title-row"><div><p className="eyebrow">LIVE AWARENESS</p><h1>Listen</h1><p>Stay aware of the sounds around you.</p></div><span className={`status-pill ${status}`}><span/>{statusText}</span></div>
    {status === 'denied' ? <section className="permission card"><Icon name="warning" size={30}/><div><h2>Allow microphone access</h2><p>Hear For You needs permission to analyze nearby sound on this device. Live microphone audio is not continuously saved.</p></div><button onClick={()=>setStatus('active')} className="primary">Try again</button></section> :
    <section className={`listener card ${status}`}>
      <div className="sound-orbit"><div className="level-ring"/><div className="mic-core"><Icon name="voice" size={52}/></div></div>
      <h2>{statusText}</h2><p className="room-level"><span className="level-bars"><i/><i/><i/><i/><i/></span>Room level: <strong>{status === 'paused' ? '—' : 'Quiet'}</strong></p>
      <div className="listener-actions"><button className="primary" onClick={()=>setStatus(status==='paused'?'active':'paused')}><Icon name={status==='paused'?'voice':'pause'}/>{status==='paused'?'Resume listening':'Pause listening'}</button><button className="secondary" onClick={()=>setStatus('reconnecting')}>Simulate reconnect</button></div>
    </section>}
    <div className="dashboard-grid">
      <section className="card sounds-card"><div className="section-head"><div><h2>Your sounds</h2><p>Sounds you teach Hear For You will appear here.</p></div></div>
        <div className="sounds-empty"><span className="empty-plus">+</span><h2>Add your first sound</h2><p>You haven’t saved any sounds yet. Record a few examples to get started.</p><button className="primary" onClick={()=>setScreen('teach')}><span aria-hidden="true">+</span> Teach a sound</button></div>
      </section>
      <aside className="info-card card"><span className="info-icon">i</span><h2>Private by design</h2><p>Demo clips are retained temporarily in this browser’s memory for playback and deleted when you refresh or close this session. Nothing is uploaded.</p><hr/><p><strong>Keep this tab visible.</strong><br/>Browsers may limit microphone access when your screen is locked or the tab is hidden.</p><div className="alert-demo"><button onClick={()=>setScreen('recognized')}>Preview recognized alert</button><button onClick={()=>setScreen('unknown')}>Preview unknown alert</button><button onClick={()=>setScreen('attention')}>Preview attention alert</button></div></aside>
    </div>
  </div>
}

function Teach({ setScreen, done, saved, startRecording, saveSound, deleteRecording }: { setScreen:(s:Screen)=>void; done:boolean[]; saved:boolean; startRecording:(index:number)=>void; saveSound:()=>void; deleteRecording:(index:number)=>void }) {
  const [selected, setSelected] = useState<IconName>('door')
  const [name, setName] = useState('Door knock')
  return <div className="page"><div className="title-row"><div><p className="eyebrow">PERSONAL SOUND LIBRARY</p><h1>Teach a sound</h1><p>Teach Hear For You the sounds that matter to you.</p></div><span className="step-label">{done.filter(Boolean).length} of 4 recordings</span></div>
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

function AuthScreen({ initialMode, onSignIn }: {initialMode:AuthMode;onSignIn:()=>void}) {
  const [mode,setMode]=useState(initialMode)
  const [showPassword,setShowPassword]=useState(false)
  const [email,setEmail]=useState('')
  const title={signin:'Sign in',create:'Create your account',verify:'Verify your email',forgot:'Forgot password',reset:'Reset password',expired:'Your session expired'}[mode]
  if(mode==='verify') return <div className="page auth-page"><section className="card auth-card"><p className="eyebrow">ACCOUNT PROTOTYPE</p><h1>{title}</h1><p>We sent a simulated verification link to <strong>{email||'you@example.com'}</strong>.</p><button className="primary" onClick={()=>setMode('signin')}>I verified my email</button><button className="text-button" onClick={()=>setMode('create')}>Use a different email</button></section></div>
  return <div className="page auth-page"><section className="card auth-card"><p className="eyebrow">HEAR FOR YOU ACCOUNT · PROTOTYPE</p><h1>{title}</h1><p>{mode==='expired'?'Sign in again to continue. Your intended destination is preserved.':mode==='signin'?"Welcome back. We're here for you. Sign in to access your sounds and detection history.":'Authentication is simulated in this prototype; no account is created.'}</p>
    <form onSubmit={e=>{e.preventDefault();mode==='create'?setMode('verify'):mode==='forgot'?setMode('reset'):onSignIn()}}>
      <label htmlFor="auth-email">Email address</label><input id="auth-email" type="email" value={email} onChange={e=>setEmail(e.target.value)} required placeholder="you@example.com"/>
      {mode!=='forgot'&&<><label htmlFor="auth-password">{mode==='reset'?'New password':'Password'}</label><div className="password-field"><input id="auth-password" type={showPassword?'text':'password'} minLength={8} required/><button type="button" onClick={()=>setShowPassword(!showPassword)} aria-label={`${showPassword?'Hide':'Show'} password`}>{showPassword?'Hide':'Show'}</button></div><small>Use at least 8 characters.</small></>}
      <button className="primary" type="submit">{mode==='create'?'Create account':mode==='forgot'?'Send reset link':mode==='reset'?'Reset password':'Sign in'}</button>
    </form>
    {mode==='signin'||mode==='expired'?<div className="auth-links"><button onClick={()=>setMode('forgot')}>Forgot password?</button><button onClick={()=>setMode('create')}>Create account</button></div>:mode!=='reset'&&<button className="text-button" onClick={()=>setMode('signin')}>Back to sign in</button>}
  </section></div>
}

type SavedSound={id:number;name:string;recordings:number}
function MySounds({ sounds, add, remove, signedIn, requireSignIn }: {sounds:SavedSound[];add:()=>void;remove:(id:number)=>void;signedIn:boolean;requireSignIn:()=>void}) {
  const [selected,setSelected]=useState<SavedSound|null>(null)
  const [confirm,setConfirm]=useState<SavedSound|null>(null)
  if(!signedIn) return <div className="page"><div className="title-row"><div><p className="eyebrow">MY SOUNDS</p><h1>Your personal sound library</h1><p>Teach Hear For You the sounds that matter to you.</p></div></div><section className="card guest-gate"><span className="empty-plus"><Icon name="bell" size={30}/></span><h2>Sign in to add and view your sounds</h2><p>Create a private library of saved sounds and training recordings. Guest activity is not automatically saved.</p><button className="primary" onClick={requireSignIn}>Sign in to continue</button><small>Authentication and storage are simulated in this prototype.</small></section></div>
  return <div className="page"><div className="title-row"><div><p className="eyebrow">REQUIRES SIGN-IN · SIMULATED</p><h1>My Sounds</h1><p>Your saved sounds and training recordings are private to your account.</p></div><button className="primary" onClick={add}>+ Add sound</button></div>
    {sounds.length===0?<section className="card sounds-empty"><span className="empty-plus">+</span><h2>Your sounds, your world. Add your first sound to get started.</h2><p>Add up to five private training recordings for each sound.</p><button className="primary" onClick={add}>Add sound</button></section>:<div className="library-grid">{sounds.map(sound=><article className="card sound-card" key={sound.id}><span className="sound-icon"><Icon name="door"/></span><div><h2>{sound.name}</h2><p>{sound.recordings} private training recordings</p></div><button className="secondary" onClick={()=>setSelected(sound)}>View details</button></article>)}</div>}
    {selected&&<div className="dialog-backdrop" role="presentation"><section className="card dialog" role="dialog" aria-modal="true" aria-labelledby="sound-detail-title"><h2 id="sound-detail-title">{selected.name}</h2><p>Private to your account · up to 5 recordings</p>{Array.from({length:selected.recordings},(_,i)=><div className="detail-recording" key={i}><strong>Training recording {i+1}</strong><PlaybackControl label={`${selected.name} recording ${i+1}`} duration={3}/><button className="text-button">Delete recording</button></div>)}<div className="dialog-actions"><button className="secondary">Rename</button><button className="secondary">Add recording</button><button className="danger-button" onClick={()=>setConfirm(selected)}>Delete sound</button><button className="primary" onClick={()=>setSelected(null)}>Done</button></div></section></div>}
    {confirm&&<div className="dialog-backdrop"><section className="card dialog" role="alertdialog" aria-modal="true"><h2>Delete {confirm.name}?</h2><p>This removes the sound and its training recordings. Previous detections will remain in your history.</p><div className="dialog-actions"><button className="secondary" onClick={()=>setConfirm(null)}>Cancel</button><button className="danger-button" onClick={()=>{remove(confirm.id);setConfirm(null);setSelected(null)}}>Delete sound</button></div></section></div>}
  </div>
}

function Account({ signOut, expire }: {signOut:()=>void;expire:()=>void}) {
  return <div className="page"><div className="title-row"><div><p className="eyebrow">REQUIRES SIGN-IN · SIMULATED</p><h1>Account</h1><p>Manage this prototype session and privacy choices.</p></div></div><div className="account-grid"><section className="card account-card"><h2>Account details</h2><label>Email address</label><strong>alex@example.com</strong><button className="secondary">Reset password</button><button className="secondary" onClick={expire}>Simulate expired session</button><button className="danger-button" onClick={signOut}>Sign out</button></section><section className="card account-card"><h2>Privacy</h2><p>Your saved sounds and training recordings are private to your account.</p><p>Live microphone audio is not continuously saved.</p><p>This prototype uses in-memory simulated data only. Nothing is uploaded or persisted.</p><hr/><h2>Import browser-local sounds</h2><p>No browser-local sounds are available to import.</p></section></div></div>
}

function History({signedIn,requireSignIn}:{signedIn:boolean;requireSignIn:()=>void}) {
  const allEvents=[
    {time:'Today, 10:24 AM',sound:'Door knock',type:'Recognized'},
    {time:'Today, 9:18 AM',sound:'Unknown sound',type:'Unknown'},
    {time:'Yesterday, 8:03 PM',sound:'Dog bark',type:'Recognized'},
    {time:'Yesterday, 7:41 PM',sound:'Smoke alarm-like sound',type:'Attention'},
    {time:'May 18, 6:11 PM',sound:'Unknown sound',type:'Unknown'},
  ]
  const [soundFilter,setSoundFilter]=useState('All')
  const [dateFilter,setDateFilter]=useState('All')
  const [limit,setLimit]=useState(3)
  const filtered=allEvents.filter(e=>(soundFilter==='All'||e.sound===soundFilter)&&(dateFilter==='All'||e.time.startsWith(dateFilter)))
  if(!signedIn) return <div className="page"><div className="title-row"><div><p className="eyebrow">DETECTION HISTORY</p><h1>Review past detections</h1><p>See recognized and unknown sound events from your account.</p></div></div><section className="card guest-gate"><span className="empty-plus"><Icon name="history" size={30}/></span><h2>Sign in to view your detection history</h2><p>Detection history is available only for signed-in accounts. Sounds detected while using this guest demo are not automatically saved.</p><button className="primary" onClick={requireSignIn}>Sign in to continue</button><small>Authentication and history storage are simulated in this prototype.</small></section></div>
  return <div className="page"><div className="title-row"><div><p className="eyebrow">REQUIRES SIGN-IN · SIMULATED</p><h1>Detection History</h1><p>Event labels and times only. Detection audio is not retained.</p></div></div><section className="card history-filters"><label>Date<select value={dateFilter} onChange={e=>setDateFilter(e.target.value)}><option>All</option><option>Today</option><option>Yesterday</option></select></label><label>Sound<select value={soundFilter} onChange={e=>setSoundFilter(e.target.value)}><option>All</option><option>Door knock</option><option>Unknown sound</option><option>Dog bark</option></select></label><button className="secondary" onClick={()=>{setDateFilter('All');setSoundFilter('All')}}>Clear filters</button></section><section className="card history-card"><div className="history-head event-only"><span>Date and time</span><span>Original detected label</span><span>Status</span></div>{filtered.length===0?<div className="history-empty"><h2>No matching results</h2><p>Try clearing one or more filters.</p></div>:filtered.slice(0,limit).map((e,i)=><div className="history-row event-only" key={i}><time>{e.time}</time><span className="event-name"><span className={`event-icon ${e.type.toLowerCase()}`}><Icon name={e.sound.includes('Door')?'door':e.sound.includes('Dog')?'dog':e.type==='Attention'?'warning':'generic'}/></span><span><strong>{e.sound}</strong><small>Original label preserved</small></span></span><span><b className={`type ${e.type.toLowerCase()}`}>{e.type}</b></span></div>)}</section>{limit<filtered.length&&<button className="secondary load-more" onClick={()=>setLimit(limit+3)}>Load more history</button>}<p className="history-foot">Renaming or deleting a saved sound does not change previous detection labels.</p></div>
}

function Alert({ type, dismiss, teach }: {type:'recognized'|'unknown'|'attention';dismiss:()=>void;teach:()=>void}) {
  const data = type==='recognized' ? { icon:'door' as const, kicker:'RECOGNIZED SOUND', title:'Door knock', sub:'94% confidence', note:'Detected just now' } : type==='unknown' ? {icon:'generic' as const,kicker:'UNKNOWN SOUND',title:'What was that?',sub:'Possibly a metallic object falling',note:'This is a tentative description'} : {icon:'warning' as const,kicker:'ATTENTION SOUND',title:'Alarm-like sound',sub:'This sound may need your attention',note:'Hear For You has not confirmed an emergency'}
  return <main className={`alert-screen ${type}`}><div className="alert-top"><Brand/><span>Alert remains visible until dismissed</span></div><div className="alert-content"><div className="alert-icon"><Icon name={data.icon} size={76}/></div><p className="alert-kicker">{data.kicker}</p><h1>{data.title}</h1><p className="alert-sub">{data.sub}</p><p className="alert-note">{data.note}</p>{type==='unknown'&&<div className="alert-playback"><PlaybackControl label="detected sound" duration={4}/><small>Simulated detected clip · retained in memory for this demo session</small></div>}<div className="alert-actions">{type==='unknown'&&<button className="alert-secondary" onClick={teach}>Teach this sound</button>}<button className="alert-dismiss" onClick={dismiss}>Dismiss alert</button></div></div></main>
}

export default function App() {
  const [screen, setScreen] = useState<Screen>('home')
  const [dark, setDark] = useState(false)
  const [signedIn,setSignedIn]=useState(false)
  const [authMode,setAuthMode]=useState<AuthMode>('signin')
  const [intended,setIntended]=useState<Screen>('home')
  const [savedSounds,setSavedSounds]=useState<SavedSound[]>([
    {id:1,name:'Door knock',recordings:3},
    {id:2,name:'Kitchen timer',recordings:2},
  ])
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
      if(!signedIn){
        setIntended('sounds')
        setAuthMode('signin')
        setScreen('auth')
      }else{
        setSoundSaved(true)
        setSavedSounds(current=>[...current,{id:Date.now(),name:'Door knock',recordings:4}])
        setScreen('teach')
      }
    }
  }
  const deleteRecording = (index:number) => {
    setRecordings(current => current.map((saved,i) => i === index ? false : saved))
    setSoundSaved(false)
  }
  const navigate=(next:Screen)=>{
    if(next==='account'&&!signedIn){
      setIntended(next)
      setAuthMode('signin')
      setScreen('auth')
      return
    }
    setScreen(next)
  }
  const signIn=()=>{setSignedIn(true);setScreen(intended)}
  const signOut=()=>{setSignedIn(false);setScreen('listen')}
  const expire=()=>{setSignedIn(false);setIntended('account');setAuthMode('expired');setScreen('auth')}
  const requireSignIn=(destination:Screen)=>{setIntended(destination);setAuthMode('signin');setScreen('auth')}
  if (['recognized','unknown','attention'].includes(screen)) return <Alert type={screen as 'recognized'|'unknown'|'attention'} dismiss={()=>setScreen('listen')} teach={()=>setScreen('teach')}/>
  return <div className={dark?'theme-dark':''}><Shell screen={screen} navigate={navigate} signedIn={signedIn} dark={dark} setDark={setDark}>{screen==='home'?<Home signedIn={signedIn} getStarted={()=>{setIntended('sounds');setAuthMode('create');setScreen('auth')}} demo={()=>setScreen('listen')} dashboard={()=>setScreen('listen')}/>:screen==='listen'?<Listen setScreen={navigate}/>:screen==='teach'?<Teach setScreen={navigate} done={recordings} saved={soundSaved} startRecording={startRecording} saveSound={()=>{if(!signedIn){requireSignIn('sounds')}else{setSoundSaved(true);setSavedSounds(current=>[...current,{id:Date.now(),name:'Door knock',recordings:4}])}}} deleteRecording={deleteRecording}/>:screen==='record'?<Recording key={recordingIndex} setScreen={navigate} index={recordingIndex} saveRecording={saveRecording}/>:screen==='sounds'?<MySounds signedIn={signedIn} requireSignIn={()=>requireSignIn('sounds')} sounds={savedSounds} add={()=>setScreen('teach')} remove={id=>setSavedSounds(current=>current.filter(sound=>sound.id!==id))}/>:screen==='account'?<Account signOut={signOut} expire={expire}/>:screen==='auth'?<AuthScreen initialMode={authMode} onSignIn={signIn}/>:<History signedIn={signedIn} requireSignIn={()=>requireSignIn('history')}/>}</Shell></div>
}
