import assert from 'node:assert/strict';
const pages=await(await fetch(`http://127.0.0.1:${process.env.BROWSER_DEBUG_PORT ?? 9223}/json/list`)).json();
const ws=new WebSocket(pages.find(p=>p.type==='page').webSocketDebuggerUrl);await new Promise(r=>ws.onopen=r);
let id=0;const pending=new Map(), events=[];
ws.onmessage=({data})=>{const m=JSON.parse(data);if(m.id){pending.get(m.id)?.(m);pending.delete(m.id)}else events.push(m)};
const send=(method,params={})=>new Promise(r=>{const n=++id;pending.set(n,r);ws.send(JSON.stringify({id:n,method,params}));});
const evaluate=async expression=>{const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true,userGesture:true});if(r.result?.exceptionDetails)throw Error(JSON.stringify(r.result.exceptionDetails));return r.result?.result.value};
const wait=ms=>new Promise(r=>setTimeout(r,ms));
const click=label=>evaluate(`(()=>{const b=Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()===${JSON.stringify(label)});if(!b)throw Error('Missing button '+${JSON.stringify(label)});b.click()})()`);
const text=()=>evaluate('document.body.innerText');
await send('Page.enable');await send('Runtime.enable');await send('Network.enable');
await send('Page.navigate',{url:process.env.FRONTEND_URL ?? 'http://localhost:5173'});await wait(1500);
await evaluate(`window.captureCalls=0;window.liveTracks=[];window.contexts=[];navigator.mediaDevices.getUserMedia=async()=>{window.captureCalls++;const ctx=new AudioContext();await ctx.resume();const osc=ctx.createOscillator();const gain=ctx.createGain();gain.gain.value=.2;const dest=ctx.createMediaStreamDestination();osc.connect(gain);gain.connect(dest);osc.start();window.testGain=gain;window.liveTracks.push(...dest.stream.getTracks());window.contexts.push(ctx);return dest.stream}`);
assert.equal(await evaluate('window.captureCalls'),0);
await click('Listen');await wait(100);assert.match(await text(),/Listening OFF/);assert.equal(await evaluate('window.captureCalls'),0);
await click('Teach');await wait(100);await click('Begin recording');await wait(100);
await evaluate('window.testGetUserMedia=navigator.mediaDevices.getUserMedia');
for(const [name,message] of [['NotAllowedError',/browser site settings/],['NotFoundError',/No microphone/],['NotReadableError',/busy or unreadable/],['OverconstrainedError',/audio settings/],['SecurityError',/security settings/]]) {
 await evaluate(`navigator.mediaDevices.getUserMedia=async()=>{throw new DOMException('test',${JSON.stringify(name)})}`);
 await click('Start recording');await wait(150);assert.match(await text(),message);await click('Try again');await wait(50);
}
await evaluate('navigator.mediaDevices.getUserMedia=window.testGetUserMedia');
console.log('PASS permission/device/security failures have distinct explanations and can be retried');
for(let i=0;i<4;i++){
 await click('Start recording');await wait(i===3?10800:3700);
 assert.match(await text(),/Recording complete/);assert.match(await text(),i===3?/ROOM NOISE/:new RegExp(`EXAMPLE ${i+1}`));
 assert.equal(await evaluate('window.liveTracks.every(t=>t.readyState==="ended")'),true);
 const audio=await evaluate(`(async()=>{const a=document.querySelector('audio');await a.play();await new Promise(r=>setTimeout(r,100));a.pause();return {duration:a.duration,paused:a.paused,src:a.currentSrc}})()`);
 assert.ok(Math.abs(audio.duration-(i===3?10:3))<.01);assert.ok(audio.src.startsWith('blob:'));
 if(i===1){await click('Re-record');await wait(3700);assert.match(await text(),/EXAMPLE 2/);assert.match(await text(),/Recording complete/)}
 await click(i===3?'Use and return to review':'Use and Continue');await wait(120);
}
assert.match(await text(),/4 of 4 recordings/);
assert.equal(await evaluate('document.querySelectorAll("audio").length'),4);
console.log('PASS four independent recordings, explicit acceptance, selected re-record, playable WAVs, released tracks');
// Test-only API responses: production code always uses its normal API client.
await evaluate(`window.realFetch=window.fetch;window.saveMode='fail';window.teachPayloads=[];window.fetch=async(url,init)=>{
 if(url==='/api/teach'){
  const form=init.body;const clips=await Promise.all(['example_1','example_2','example_3','room'].map(async key=>{const blob=form.get(key);const view=new DataView(await blob.arrayBuffer());return {key,type:blob.type,rate:view.getUint32(24,true),channels:view.getUint16(22,true),bits:view.getUint16(34,true),samples:view.getUint32(40,true)/2}}));
  window.teachPayloads.push({fields:Array.from(form.keys()),clips});
  return new Response(JSON.stringify(window.saveMode==='fail'?{error:{code:'upstream_error',message:'Test backend unavailable'}}:{sound_id:'snd_browser_test',name:form.get('name'),icon:form.get('icon'),self_check:{passed:window.saveMode==='pass',score:.9,threshold:.7},latency_ms:1}),{status:window.saveMode==='fail'?502:200,headers:{'Content-Type':'application/json'}});
 }
 if(String(url).includes('snd_browser_test')&&init?.method==='PATCH')return new Response(JSON.stringify({sound_id:'snd_browser_test',name:'Test',icon:'door',kind:'taught',enabled:false,latency_ms:1}));
 return window.realFetch(url,init);
}`);
await click('Save and check sound');await wait(300);assert.match(await text(),/Test backend unavailable/);assert.equal(await evaluate('document.querySelectorAll("audio").length'),4);
await evaluate("window.saveMode='selfcheck-fail'");await click('Save and check sound');await wait(300);assert.match(await text(),/Self-check did not pass/);
await evaluate("window.saveMode='pass'");await click('Save and check sound');await wait(300);assert.match(await text(),/self-check passed/);
const payload=await evaluate('window.teachPayloads[0]');
assert.deepEqual(payload.fields,['name','icon','example_1','example_2','example_3','room']);
for(const [index,clip] of payload.clips.entries()){assert.equal(clip.type,'audio/wav');assert.equal(clip.rate,16000);assert.equal(clip.channels,1);assert.equal(clip.bits,16);assert.equal(clip.samples,index===3?160000:48000)}
console.log('PASS exact teach API payload, save failure preserves clips, failed self-check is not success, explicit save succeeds only on confirmation');
await click('Listen');await wait(100);assert.match(await text(),/Listening OFF/);
const before=await evaluate('window.captureCalls');await click('Start Listening');await wait(500);assert.match(await text(),/Listening now/);assert.equal(await evaluate('window.captureCalls'),before+1);
await click('Stop Listening');await wait(200);assert.match(await text(),/Listening OFF/);assert.equal(await evaluate('window.liveTracks.every(t=>t.readyState==="ended")'),true);
await click('Start Listening');await click('Stop Listening');await wait(500);assert.match(await text(),/Listening OFF/);assert.equal(await evaluate('window.liveTracks.every(t=>t.readyState==="ended")'),true);
console.log('PASS Listen OFF by default, no page-load capture, Start acquires audio, Stop/rapid stop releases streams');

// Verify the detection pipeline without spending Gemini quota.
await evaluate(`window.detectCalls=0;window.detectMode='stale';window.fetch=async(url,init)=>{
 if(url==='/api/detect') {window.detectCalls++;window.detectForm=init.body;return new Promise(resolve=>{window.completeDetect=()=>resolve(new Response(JSON.stringify({event_id:'evt_browser_test',kind:'builtin',label:'Dog bark',sound_id:'builtin_dog_bark',confidence:.95,description:null,latency_ms:1})))})}
 return window.realFetch(url,init);
}`);
await click('Start Listening');await wait(1200);await evaluate('window.testGain.gain.value=.001');await wait(11000);await evaluate('window.testGain.gain.value=.8');await wait(3500);
assert.equal(await evaluate('window.detectCalls'),1);
const detectPayload=await evaluate(`(async()=>{const form=window.detectForm;const blob=form.get('clip');return {keys:Array.from(form.keys()),bytes:blob.size,level:Number(form.get('level_db'))}})()`);
assert.deepEqual(detectPayload.keys,['clip','level_db']);assert.equal(detectPayload.bytes,96044);assert.ok(detectPayload.level<0);
await click('Stop Listening');await evaluate('window.completeDetect()');await wait(200);assert.equal(await evaluate('!!document.querySelector(".alert-screen")'),false);
console.log('PASS real onset audio sends valid detect payload; stopped session ignores stale response');
// Disable a category through its actual UI switch, using a controlled backend response.
await evaluate(`window.fetch=async(url,init)=>{
 if(url==='/api/sounds/builtin_dog_bark')return new Response(JSON.stringify({sound_id:'builtin_dog_bark',name:'Dog bark',icon:'dog',kind:'builtin',enabled:JSON.parse(init.body).enabled,latency_ms:1}));
 if(url==='/api/detect'){window.detectCalls++;return new Response(JSON.stringify({event_id:'evt_disabled_test',kind:'builtin',label:'Dog bark',sound_id:'builtin_dog_bark',confidence:.95,description:null,latency_ms:1}))}
 return window.realFetch(url,init);
}`);
await click('My Sounds');await wait(100);await evaluate(`document.querySelector('button[aria-label="Disable Dog bark"]').click()`);await wait(200);
assert.ok(await evaluate(`!!document.querySelector('button[aria-label="Enable Dog bark"]')`));
await click('Listen');await wait(100);assert.match(await text(),/Dog bark/);
await click('Start Listening');await wait(1200);await evaluate('window.testGain.gain.value=.001');await wait(11000);await evaluate('window.testGain.gain.value=.8');await wait(3500);
assert.equal(await evaluate('window.detectCalls'),2);
assert.equal(await evaluate('!!document.querySelector(".alert-screen")'),false);
assert.equal(await evaluate(`JSON.parse(localStorage.getItem('hear-for-you-history')).some(event=>event.event_id==='evt_disabled_test')`),false);
await click('Stop Listening');
// Re-enabling restores real-result eligibility and local history insertion.
await click('My Sounds');await wait(100);await evaluate(`document.querySelector('button[aria-label="Enable Dog bark"]').click()`);await wait(200);
await click('Listen');await wait(100);await click('Start Listening');await wait(1200);await evaluate('window.testGain.gain.value=.001');await wait(11000);await evaluate('window.testGain.gain.value=.8');await wait(3500);
assert.equal(await evaluate('window.detectCalls'),3);
assert.ok(await evaluate('!!document.querySelector(".alert-screen")'));
assert.equal(await evaluate(`JSON.parse(localStorage.getItem('hear-for-you-history')).some(event=>event.event_id==='evt_disabled_test')`),true);
await click('Dismiss alert');await click('Stop Listening');
console.log('PASS re-enabled category produces an alert and genuine-response history');
// A permission grant arriving after Stop must release its track immediately.
await evaluate(`navigator.mediaDevices.getUserMedia=()=>new Promise(resolve=>{window.lateGrant=async()=>resolve(await window.testGetUserMedia())})`);
await click('Start Listening');await click('Stop Listening');await evaluate('window.lateGrant()');await wait(300);
assert.equal(await evaluate('window.liveTracks.every(t=>t.readyState==="ended")'),true);
assert.match(await text(),/Listening OFF/);
console.log('PASS disabled category remains visible without alerts/history; late grant after Stop releases tracks');
await evaluate(`window.fetch=window.realFetch;for(const key of ['hear-for-you-custom-sounds','hear-for-you-history','hear-for-you-builtins'])localStorage.removeItem(key);Promise.all(window.contexts.map(c=>c.state==='closed'?undefined:c.close()))`);
console.log('Runtime exceptions:' ,events.filter(e=>e.method==='Runtime.exceptionThrown').map(e=>e.params.exceptionDetails.text));
ws.close();
