import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
const sounds = JSON.parse(await readFile(new URL('../src/fixtures/sounds.json', import.meta.url), 'utf8'));
const page = await (await fetch(`http://127.0.0.1:${process.env.BROWSER_DEBUG_PORT ?? 9223}/json/new?about:blank`, { method: 'PUT' })).json();
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise(resolve => ws.onopen = resolve);
let id = 0;
const pending = new Map();
ws.onmessage = ({ data }) => { const message = JSON.parse(data); if (message.id) { pending.get(message.id)?.(message); pending.delete(message.id); } };
const send = (method, params = {}) => new Promise(resolve => { const next = ++id; pending.set(next, resolve); ws.send(JSON.stringify({ id: next, method, params })); });
const evaluate = async expression => {
  const response = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true, userGesture: true });
  if (response.result?.exceptionDetails) throw Error(JSON.stringify(response.result.exceptionDetails));
  return response.result?.result.value;
};
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
const click = label => evaluate(`Array.from(document.querySelectorAll('button')).find(button => button.textContent.trim() === ${JSON.stringify(label)}).click()`);
try {
  await send('Page.enable');
  await send('Page.addScriptToEvaluateOnNewDocument', { source: `
    for (const key of ['hear-for-you-history','hear-for-you-builtins','hear-for-you-custom-sounds']) localStorage.removeItem(key);
    window.testContexts=[]; window.tracks=[]; window.captureCalls=0; window.detectCalls=0;
    window.fetch=async(url,init)=>{
      if(url==='/api/sounds') return new Response(JSON.stringify(${JSON.stringify(sounds)}));
      if(url==='/api/sounds/builtin_glass_breaking') return new Response(JSON.stringify({sound_id:'builtin_glass_breaking',name:'Glass breaking',icon:'glass',kind:'builtin',enabled:JSON.parse(init.body).enabled,latency_ms:1}));
      if(url==='/api/detect') { window.detectCalls++; const response={event_id:'evt_global_'+window.detectCalls,kind:'builtin',label:'Glass breaking',sound_id:'builtin_glass_breaking',confidence:.9,description:null,latency_ms:1};
        if(window.delayDetection) return new Promise(resolve=>window.finishDetection=()=>resolve(new Response(JSON.stringify(response))));
        return new Response(JSON.stringify(response)); }
      throw Error('Unexpected API request in isolated test');
    };
    navigator.mediaDevices.getUserMedia=async()=>{
      window.captureCalls++;
      if(window.tracks.some(track=>track.readyState==='live')) throw Error('Overlapping microphone acquisitions');
      const context=new AudioContext(); await context.resume();
      const oscillator=context.createOscillator(), gain=context.createGain(), destination=context.createMediaStreamDestination();
      gain.gain.value=.001; oscillator.connect(gain); gain.connect(destination); oscillator.start();
      window.testGain=gain; window.tracks.push(...destination.stream.getTracks()); window.testContexts.push(context); return destination.stream;
    };
  ` });
  await send('Page.navigate', { url: process.env.FRONTEND_URL ?? 'http://localhost:5173' });
  await wait(1200); await click('Listen'); await wait(100);
  assert.equal(await evaluate('window.captureCalls'),0);
  await click('Start Listening'); await wait(500);
  assert.equal(await evaluate('window.captureCalls'),1);
  for (const label of ['Home','My Sounds','History','Teach','Login','Listen']) {
    await click(label); await wait(100);
    assert.equal(await evaluate('window.captureCalls'),1,label);
    assert.equal(await evaluate('window.tracks.filter(track=>track.readyState==="live").length'),1,label);
  }
  assert.match(await evaluate('document.body.innerText'),/Listening now/);
  await click('History'); await wait(1400);
  await evaluate('window.testGain.gain.value=.8'); await wait(3100);
  assert.equal(await evaluate('!!document.querySelector(".alert-screen")'),true);
  assert.equal(await evaluate('JSON.parse(localStorage.getItem("hear-for-you-history")).length'),1);
  await click('Dismiss alert');
  assert.equal(await evaluate('document.querySelectorAll(".history-row").length'),1);
  console.log('PASS one stream across every page; real onset generates alert and local History on History page');

  await click('Teach'); await click('Begin recording'); await wait(200);
  assert.equal(await evaluate('window.tracks.every(track=>track.readyState==="ended")'),true);
  await click('Start recording'); await wait(300); await evaluate('window.testGain.gain.value=.2'); await wait(3200);
  assert.match(await evaluate('document.body.innerText'),/Recording complete/);
  assert.equal(await evaluate('window.captureCalls'),2);
  assert.equal(await evaluate('window.detectCalls'),1);
  assert.equal(await evaluate('window.tracks.every(track=>track.readyState==="ended")'),true);
  assert.equal(await evaluate('document.querySelector("audio").duration'),3);
  await click('Use and Continue'); await wait(100);
  await click('← Back to sound'); await wait(400);
  assert.equal(await evaluate('window.captureCalls'),3);
  await evaluate('document.querySelector("audio").play()'); await wait(150);
  assert.equal(await evaluate('window.tracks.every(track=>track.readyState==="ended")'),true);
  await evaluate('document.querySelector("audio").pause()'); await wait(300);
  assert.equal(await evaluate('window.captureCalls'),4);
  assert.equal(await evaluate('window.detectCalls'),1);
  await evaluate('document.querySelector("audio").play()'); await wait(100);
  await click('Listen'); await wait(400);
  assert.equal(await evaluate('window.captureCalls'),5);
  assert.match(await evaluate('document.body.innerText'),/Listening now/);
  console.log('PASS Teach owns the microphone exclusively, produces a valid reviewed clip, pauses for preview playback and resumes safely');

  await click('My Sounds');
  await evaluate(`document.querySelector('button[aria-label="Disable Glass breaking"]').click()`); await wait(200);
  await click('History'); await wait(1300); await evaluate('window.testGain.gain.value=.8'); await wait(3100);
  assert.equal(await evaluate('window.detectCalls'),2);
  assert.equal(await evaluate('!!document.querySelector(".alert-screen")'),false);
  assert.equal(await evaluate('JSON.parse(localStorage.getItem("hear-for-you-history")).length'),1);
  console.log('PASS disabled categories suppressed off Listen without new local History');

  await click('Listen'); await click('Stop Listening'); await wait(200);
  assert.equal(await evaluate('window.tracks.every(track=>track.readyState==="ended")'),true);
  await click('My Sounds');
  await evaluate(`document.querySelector('button[aria-label="Enable Glass breaking"]').click()`); await wait(200);
  await click('Listen'); await evaluate('window.delayDetection=true'); await click('Start Listening');
  await wait(1600); await evaluate('window.testGain.gain.value=.8'); await wait(3100);
  await click('Stop Listening'); await evaluate('window.finishDetection()'); await wait(200);
  assert.equal(await evaluate('!!document.querySelector(".alert-screen")'),false);
  assert.equal(await evaluate('JSON.parse(localStorage.getItem("hear-for-you-history")).length'),1);
  console.log('PASS Stop releases all tracks and discards pending API responses');

  await click('Start Listening'); await wait(300);
  await evaluate('window.tracks.filter(track=>track.readyState==="live").forEach(track=>track.dispatchEvent(new Event("ended")))'); await wait(200);
  assert.match(await evaluate('document.body.innerText'),/Listening OFF/);
  assert.match(await evaluate('document.body.innerText'),/disconnected/);
  await send('Page.reload'); await wait(1000); await click('Listen');
  assert.equal(await evaluate('window.captureCalls'),0);
  assert.match(await evaluate('document.body.innerText'),/Listening OFF/);
  console.log('PASS device interruption stops global session; refresh defaults OFF without microphone access');
} finally {
  await evaluate(`Promise.all((window.testContexts??[]).map(context=>context.state==='closed'?undefined:context.close()))`);
  await send('Target.closeTarget', { targetId: page.id });
  ws.close();
}
