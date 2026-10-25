// Chronological audio -> real frontend gate -> real API -> alert and local History.
// Requires Node 22 and a disposable Chrome profile with remote debugging enabled.
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { resolve, relative, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';

const args = process.argv.slice(2);
const input = args[0], output = args[1];
if (!input || !output) throw Error('Usage: node data/replay_corpus.mjs data/raw/replay.json data/raw/replay-results.json');
const raw = fileURLToPath(new URL('./raw/', import.meta.url));
for (const path of [input, output]) {
  const rel = relative(raw, resolve(path));
  if (rel.startsWith('..') || rel.startsWith('/')) throw Error('Replay inputs and results must stay under data/raw.');
}
const bundle = JSON.parse(await readFile(input, 'utf8'));
if (bundle.version !== 1 || bundle.evidence !== 'digital_microphone_replay' || !bundle.trials?.length) throw Error('Invalid replay bundle.');
for (const trial of bundle.trials) {
  if (createHash('sha256').update(Buffer.from(trial.wav_base64, 'base64')).digest('hex') !== trial.audio_sha256) throw Error(`Audio hash mismatch: ${trial.trial_id}`);
}
const port = Number(process.env.BROWSER_DEBUG_PORT ?? 9223);
const frontend = process.env.FRONTEND_URL ?? 'http://localhost:5173';
if (!['localhost', '127.0.0.1'].includes(new URL(frontend).hostname)) throw Error('Use an isolated local frontend and backend.');
const page = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: 'PUT' })).json();
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
let nextId = 0;
const pending = new Map();
ws.onmessage = ({ data }) => {
  const message = JSON.parse(data);
  const request = pending.get(message.id);
  if (request) { pending.delete(message.id); clearTimeout(request.timer); message.error ? request.reject(Error(message.error.message)) : request.resolve(message); }
};
const send = (method, params = {}) => new Promise((resolve, reject) => {
  const id = ++nextId;
  const timer = setTimeout(() => { pending.delete(id); reject(Error(`CDP timeout: ${method}`)); }, 30000);
  pending.set(id, { resolve, reject, timer }); ws.send(JSON.stringify({ id, method, params }));
});
const evaluate = async expression => {
  const response = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true, userGesture: true });
  if (response.result?.exceptionDetails) throw Error(JSON.stringify(response.result.exceptionDetails));
  return response.result?.result.value;
};
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
const until = async (expression, timeout = 15000) => {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) { if (await evaluate(expression)) return; await wait(100); }
  throw Error(`Timed out waiting for ${expression}`);
};
const click = label => evaluate(`(() => { const button=Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()===${JSON.stringify(label)}); if(!button) throw Error('Missing button '+${JSON.stringify(label)}); button.click(); })()`);
const results = [];
let failure = null;
try {
  await mkdir(dirname(resolve(output)), { recursive:true });
  await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride', {width:1280,height:900,deviceScaleFactor:1,mobile:false});
  await send('Page.addScriptToEvaluateOnNewDocument', { source: `
    for (const key of ['hear-for-you-history','hear-for-you-builtins','hear-for-you-custom-sounds']) localStorage.removeItem(key);
    window.corpus={calls:[],alerts:[],contexts:[],active:0};
    const realFetch=window.fetch.bind(window);
    window.fetch=async (...args)=>{
      const url=String(args[0] instanceof Request ? args[0].url : args[0]);
      const pathname=new URL(url,location.href).pathname;
      if(pathname.endsWith('/api/sounds')) { const response=await realFetch(...args); window.corpus.sounds_status=response.status; return response; }
      if(!pathname.endsWith('/api/detect')) return realFetch(...args);
      const call={started_ms:performance.now()}; window.corpus.calls.push(call); window.corpus.active++;
      try { const response=await realFetch(...args); call.status=response.status; call.body=await response.clone().json(); return response; }
      catch(error) { call.error=String(error); throw error; }
      finally { call.ended_ms=performance.now(); window.corpus.active--; }
    };
    navigator.mediaDevices.getUserMedia=async()=>{
      const context=new AudioContext(); await context.resume();
      const destination=context.createMediaStreamDestination();
      window.corpus.contexts.push(context); window.corpus.context=context; window.corpus.destination=destination;
      return destination.stream;
    };
    new MutationObserver(()=>{
      const alert=document.querySelector('.alert-screen');
      if(alert && !window.corpus.visible) window.corpus.alerts.push({at_ms:performance.now(),text:alert.innerText});
      window.corpus.visible=!!alert;
    }).observe(document,{childList:true,subtree:true});
  ` });
  for (const trial of bundle.trials) {
    if (results.length) await wait(11000); // Backend's ongoing-event grouping gap is ten seconds.
    await send('Page.navigate', { url: frontend });
    await until(`Array.from(document.querySelectorAll('button')).some(b=>b.textContent.trim()==='Listen')`);
    await click('Listen');
    await until('window.corpus.sounds_status===200'); // Fixture mode must not masquerade as a live run.
    await until(`Array.from(document.querySelectorAll('button')).some(b=>b.textContent.trim()==='Start Listening')`);
    await click('Start Listening');
    await until(`!!window.corpus.context && document.body.innerText.includes('Listening now')`);
    await evaluate(`(async()=>{
      const bytes=Uint8Array.from(atob(${JSON.stringify(trial.wav_base64)}),c=>c.charCodeAt(0));
      const buffer=await window.corpus.context.decodeAudioData(bytes.buffer);
      const source=window.corpus.context.createBufferSource(); source.buffer=buffer;
      source.connect(window.corpus.destination); window.corpus.started=performance.now(); source.start();
      window.corpus.ended=false; source.onended=()=>window.corpus.ended=true;
    })()`);
    const deadline = Date.now() + trial.duration_seconds * 1000 + 45000;
    let settled = false;
    let screenshot = null;
    while (Date.now() < deadline) {
      // Dismiss after observation so a sustained recording can expose subsequent alerts.
      if (process.env.CORPUS_SCREENSHOTS === '1' && !screenshot && await evaluate(`!!document.querySelector('.alert-screen')`)) {
        const shot = await send('Page.captureScreenshot', {format:'png'});
        screenshot = `${output}.${trial.trial_id.replace(/[^A-Za-z0-9_-]/g,'_')}.png`;
        await writeFile(screenshot, Buffer.from(shot.result.data, 'base64'));
      }
      await evaluate(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()==='Dismiss alert')?.click()`);
      if (await evaluate('window.corpus.ended && window.corpus.active===0')) { settled = true; break; }
      await wait(100);
    }
    // Allow a queued three-second gate window and pending-request slot to finish.
    await wait(6000);
    await until('window.corpus.active===0', 30000);
    const observation = await evaluate(`({calls:window.corpus.calls,alerts:window.corpus.alerts,
      started:window.corpus.started,history:JSON.parse(localStorage.getItem('hear-for-you-history')??'[]')})`);
    await click('Stop Listening');
    const calls = observation.calls.map(c => ({ ...c, started_ms:c.started_ms-observation.started, ended_ms:c.ended_ms-observation.started }));
    const alerts = observation.alerts.map(a => ({ ...a, at_ms:a.at_ms-observation.started }));
    const expected = trial.events.filter(e => e.expected_alert);
    const failures = calls.filter(c => c.error || c.status >= 400);
    // Candidate timing only: no forced event-to-alert pairing for overlapping events.
    const eventResults = expected.map(event => {
      const next = alerts.find(a => a.at_ms >= event.at_seconds*1000);
      return { ...event, candidate_time_to_alert_ms:next ? next.at_ms-event.at_seconds*1000 : null };
    });
    const apiIds = calls.map(c=>c.body?.sound_id).filter(Boolean);
    results.push({ ...Object.fromEntries(Object.entries(trial).filter(([key])=>key!=='wav_base64')),
      evidence:'digital_microphone_replay', settled, screenshot, calls, alerts, local_history:observation.history,
      local_history_count:observation.history.length, no_gate_request:calls.length===0,
      request_failures:failures.length, expected_events:eventResults,
      positive_without_alert:expected.length>0 && alerts.length===0,
      negative_with_alert:expected.length===0 && alerts.length>0,
      wrong_api_categories:apiIds.filter(id=>expected.length && !expected.some(e=>e.sound_id===id)),
      needs_manual_event_matching:expected.length>1 || alerts.length>1 });
    console.log(`${trial.trial_id}: requests=${calls.length} alerts=${alerts.length} failures=${failures.length}`);
    if (!settled) throw Error(`Playback or requests did not settle: ${trial.trial_id}`);
  }
} catch (error) { failure=String(error); process.exitCode=1; }
finally {
  await mkdir(dirname(resolve(output)), { recursive:true });
  await writeFile(output, JSON.stringify({version:1,status:failure?'incomplete':'complete',failure,
    evidence:'digital_microphone_replay',manifest_sha256:bundle.manifest_sha256,frontend,viewport:{width:1280,height:900},
    trials:results,reliability_established:false,
    notes:'Candidate latency requires manual event matching. No physical-distance or false-alerts/hour claim is inferred.'},null,2)+'\n');
  try { await send('Target.closeTarget', {targetId:page.id}); } finally { ws.close(); }
}
