import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { isReadyToSave } from './teach-state.ts';

const appSource = readFileSync(new URL('./App.tsx', import.meta.url), 'utf8');
const completeRecordings = Array.from({ length: 4 }, () => ({
  blob: new Blob(['recording'], { type: 'audio/wav' }),
  valid: true,
}));

test('a fresh Teach draft starts blank and remains a controlled App-level field', () => {
  assert.match(appSource, /const \[name, setName\] = useState\(''\)/);
  assert.doesNotMatch(appSource, /useState\('Door knock'\)/);
  assert.match(appSource, /<input id="soundName" value=\{name\} onChange=\{e=>setName\(e\.target\.value\)\} \/>/);
  assert.match(appSource, /<Teach [^>]*name=\{name\} setName=\{setName\}/);
});

test('Save remains blocked for a blank name and accepts a custom name', () => {
  assert.equal(isReadyToSave('', completeRecordings), false);
  assert.equal(isReadyToSave('   ', completeRecordings), false);
  assert.equal(isReadyToSave('Front entry chime', completeRecordings), true);
});
