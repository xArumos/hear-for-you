import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
const sounds = JSON.parse(await readFile(new URL('../src/fixtures/sounds.json', import.meta.url), 'utf8'));
const pages = await (await fetch(`http://127.0.0.1:${process.env.BROWSER_DEBUG_PORT ?? 9223}/json/list`)).json();
const ws = new WebSocket(pages.find(page => page.type === 'page').webSocketDebuggerUrl);
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
    window.testContexts=[]; window.detectCalls=0;
    window.fetch=async(url)=>{
      if(url==='/api/sounds') return new Response(JSON.stringify(${JSON.stringify(sounds)}));
      if(url==='/api/detect') { window.detectCalls++; return new Response(JSON.stringify(window.nextDetection)); }
      throw Error('Unexpected API request in isolated test');
    };
    navigator.mediaDevices.getUserMedia=async()=>{
      const context=new AudioContext(); await context.resume();
      const oscillator=context.createOscillator(), gain=context.createGain(), destination=context.createMediaStreamDestination();
      gain.gain.value=.001; oscillator.connect(gain); gain.connect(destination); oscillator.start();
      window.testGain=gain; window.testContexts.push(context); return destination.stream;
    };
  ` });
  await send('Page.navigate', { url: process.env.FRONTEND_URL ?? 'http://localhost:5173' });
  await wait(1200); await click('Listen'); await wait(100);
  const cases = [
    { event_id:'evt_speech', kind:'unknown', label:null, sound_id:null, confidence:null, description:'Someone is speaking.', expected:false },
    { event_id:'evt_amplitude', kind:'unknown', label:null, sound_id:null, confidence:null, description:null, expected:false },
    { event_id:'evt_low', kind:'builtin', label:'Dog bark', sound_id:'builtin_dog_bark', confidence:.4, description:null, expected:false },
    { event_id:'evt_glass', kind:'builtin', label:'Glass breaking', sound_id:'builtin_glass_breaking', confidence:.9, description:null, expected:true },
    { event_id:'evt_mixed', kind:'unknown', label:null, sound_id:null, confidence:null, description:'A doorbell rings while someone is speaking.', expected:true },
  ];
  for (const { expected, ...result } of cases) {
    await evaluate(`window.nextDetection=${JSON.stringify({ ...result, latency_ms:1 })}`);
    await click('Start Listening'); await wait(1600);
    await evaluate('window.testGain.gain.value=.8'); await wait(3100);
    assert.equal(await evaluate('!!document.querySelector(".alert-screen")'), expected, result.event_id);
    assert.equal(await evaluate(`JSON.parse(localStorage.getItem('hear-for-you-history')??'[]').some(event=>event.event_id===${JSON.stringify(result.event_id)})`), expected);
    if (expected) await click('Dismiss alert');
    await click('Stop Listening');
  }
  assert.equal(await evaluate('window.detectCalls'), cases.length);
  await click('History');
  assert.equal(await evaluate('document.querySelectorAll(".history-row").length'),2);
  console.log('PASS real onset gate → controlled API → relevance policy → matching alert/local History; single glass and mixed event preserved');
} finally {
  await evaluate(`Promise.all((window.testContexts??[]).map(context=>context.state==='closed'?undefined:context.close()))`);
  await send('Page.navigate', { url:'about:blank' });
  ws.close();
}
