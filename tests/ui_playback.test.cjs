const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {Player, effectiveVersion, resultKey, shouldLoadResult} = require('../src/music_studio/ui/static/playback.js');

// Exercise the actual app poll handler with controlled server responses, without a browser or models.
const app = fs.readFileSync(path.join(__dirname, '../src/music_studio/ui/static/app.js'), 'utf8');
const pollSource = app.slice(app.indexOf('async function poll()'), app.indexOf('\nfunction viewDuration()'));
function pollingFixture(legacy = false) {
  const state = {legacy, checking: false, selecting: false, generation: 1, version: legacy ? 'original' : 'v1',
    job: {id: 'song', status: 'complete', has_result: true, current_version: 'v1'},
    loadedResultKey: resultKey('song', legacy ? 'original' : 'v1'), project: {}, jobs: []};
  const calls = {loads: 0, candidates: 0};
  const env = {state, MusicPlayback: {effectiveVersion, resultKey, shouldLoadResult},
    refreshProjects: async () => { state.jobs = [{...state.job}]; }, renderStatus() {}, notice() {},
    loadResult: async id => { calls.loads++; state.loadedResultKey = resultKey(id, state.version); },
    showCandidate: async () => { calls.candidates++; }};
  return {state, calls, env, poll: vm.runInNewContext(`${pollSource}\npoll`, env)};
}

const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return {promise, resolve, reject};
};
function fixture(extra = {}) {
  const requests = [], sources = [], oscillators = [], decoded = [];
  let mode = 'source', generation = 1;
  const param = () => ({value: 0, setTargetAtTime() {}, setValueAtTime() {}, linearRampToValueAtTime() {}});
  const context = {
    currentTime: 0, destination: {},
    async resume() {},
    async decodeAudioData(bytes) { decoded.push(bytes); return {duration: 900, tag: bytes}; },
    createGain() { return {gain: param(), connect() {}, disconnect() {}}; },
    createBufferSource() {
      const node = {connect() {}, disconnect() {}, stopped: false,
        start(at, offset) { this.at = at; this.offset = offset; }, stop() { this.stopped = true; }};
      sources.push(node);
      return node;
    },
    createOscillator() {
      const node = {frequency: param(), connect() {}, disconnect() {}, start() {}, stop() {}};
      oscillators.push(node);
      return node;
    }
  };
  const player = new Player({
    contextFactory: () => context,
    getMode: () => mode, getGeneration: () => generation,
    getNotes: () => [{start: 1, end: 2, pitch: 60}, {start: 20, end: 20.005, pitch: 67}],
    fetcher: async (url, {signal}) => { requests.push({url, signal}); return {ok: true, arrayBuffer: async () => url}; },
    ...extra
  });
  return {player, context, requests, sources, oscillators, decoded,
    mode(value) { mode = value; }, generation(value) { generation = value; }};
}

test('legacy status polling keeps the original version loaded even when the server advertises a revision', async () => {
  const {player, requests} = fixture();
  const job = {id: 'song', status: 'complete', has_result: true, current_version: 'new-model'};
  let loaded = null, loads = 0;
  for (let tick = 0; tick < 30; tick++) {
    if (shouldLoadResult(job, true, loaded, null)) {
      const version = effectiveVersion(job, true);
      await player.load(job.id, 900, 1, version);
      loaded = resultKey(job.id, version);
      loads++;
    }
  }
  assert.equal(loads, 1);
  assert.equal(requests.length, 1);
  assert.match(requests[0].url, /version=original$/);
});

test('same-version completion and candidate completion do not reload audio; an adopted new version does', () => {
  const job = {id: 'song', status: 'running', has_result: true, current_version: 'v1'};
  const loaded = resultKey('song', 'v1');
  assert.equal(shouldLoadResult(job, false, loaded, null), false);
  job.status = 'complete'; job.candidate_version = 'candidate';
  assert.equal(shouldLoadResult(job, false, loaded, null), false);
  job.current_version = 'v2';
  assert.equal(shouldLoadResult(job, false, loaded, null), true);
  assert.equal(shouldLoadResult(job, false, loaded, resultKey('song', 'v2')), false);
  assert.equal(shouldLoadResult({...job, status: 'ready', has_result: false}, false, null, null), false);
});

test('actual UI poll handler never reloads a legacy result over repeated status updates', async () => {
  const f = pollingFixture(true);
  for (let i = 0; i < 30; i++) await f.poll();
  assert.equal(f.calls.loads, 0);
  assert.equal(f.state.generation, 1);
});

test('actual UI poll handler loads an adopted version once and shows a candidate without reloading', async () => {
  const f = pollingFixture();
  f.state.job.status = 'running';
  f.env.refreshProjects = async () => { f.state.jobs = [{...f.state.job, status: 'complete', candidate_version: 'candidate'}]; };
  await f.poll(); await f.poll();
  assert.equal(f.calls.candidates, 1);
  assert.equal(f.calls.loads, 0);
  f.env.refreshProjects = async () => { f.state.jobs = [{...f.state.job, current_version: 'v2'}]; };
  await f.poll(); await f.poll();
  assert.equal(f.calls.loads, 1);
});

test('status response from before a song selection cannot reload or overwrite the new song', async () => {
  const f = pollingFixture();
  f.env.refreshProjects = async () => {
    f.state.jobs = [{...f.state.job, current_version: 'v2'}];
    f.state.generation++;
    f.state.job = {id: 'other', status: 'complete'};
  };
  await f.poll();
  assert.equal(f.state.job.id, 'other');
  assert.equal(f.calls.loads, 0);
  f.state.selecting = true;
  await f.poll();
  assert.equal(f.calls.loads, 0);
});

test('concurrent and repeated loads fetch and decode only one source, with no eager stems', async () => {
  const f = fixture();
  await Promise.all([f.player.load('song', 900, 1, 'v1'), f.player.load('song', 900, 1, 'v1')]);
  await f.player.load('song', 900, 1, 'v1');
  assert.equal(f.requests.length, 1);
  assert.equal(f.decoded.length, 1);
  assert.deepEqual(Object.keys(f.player.buffers), ['source']);
  assert.equal(f.player.ready, true);
});

test('first stem selection is deduplicated and joins the running clock without stopping source', async () => {
  const f = fixture();
  await f.player.load('song', 900, 1);
  await f.player.play();
  f.context.currentTime = 40;
  const before = f.player.time, anchor = f.player.anchor;
  await Promise.all([f.player.ensureTrack('vocals'), f.player.ensureTrack('vocals')]);
  assert.equal(f.requests.length, 2);
  assert.equal(f.player.playing, true);
  assert.equal(f.player.anchor, anchor);
  assert.equal(f.player.time, before);
  assert.equal(f.sources[0].stopped, false);
  assert.equal(f.sources[1].offset, 40);
  f.mode('vocals'); f.player.setMix();
  await f.player.ensureTrack('vocals');
  await f.player.seek(120);
  assert.equal(f.requests.length, 2);
  assert.equal(f.player.playing, true);
  assert.equal(f.player.time, 120);
});

test('audio playback creates MIDI oscillators only when melody is selected', async () => {
  const f = fixture();
  await f.player.load('song', 900, 1);
  await f.player.play();
  assert.equal(f.oscillators.length, 0);
  f.mode('melody'); f.player.setMix();
  assert.equal(f.oscillators.length, 2);
  f.player.setMix();
  assert.equal(f.oscillators.length, 2);
  f.mode('source'); f.player.setMix();
  assert.equal(f.player.melodyNodes.length, 0);
});

test('changing songs aborts old requests and ignores a late decode from the old song', async () => {
  const f = fixture();
  const oldDecode = deferred();
  let decodingOld = false;
  f.context.decodeAudioData = bytes => {
    if (bytes.includes('/old/')) { decodingOld = true; return oldDecode.promise; }
    return Promise.resolve({duration: 900, tag: 'new'});
  };
  const oldLoad = f.player.load('old', 900, 1);
  while (!decodingOld) await Promise.resolve();
  f.generation(2);
  await f.player.load('new', 900, 2);
  oldDecode.resolve({duration: 10, tag: 'stale'});
  await oldLoad;
  assert.equal(f.requests[0].signal.aborted, true);
  assert.equal(f.player.buffers.source.tag, 'new');
  assert.equal(f.player.duration, 900);
});

test('a failed stem can be retried without resetting the playable source', async () => {
  const f = fixture();
  await f.player.load('song', 900, 1);
  let attempts = 0;
  f.player.options.fetcher = async () => ({ok: ++attempts > 1, arrayBuffer: async () => 'stem'});
  await assert.rejects(f.player.ensureTrack('instrumental'), /retry/);
  assert.equal(f.player.isLoading('instrumental'), false);
  assert.equal(f.player.ready, true);
  await f.player.ensureTrack('instrumental');
  assert.equal(attempts, 2);
  assert.equal(f.player.buffers.instrumental.tag, 'stem');
});

test('pause or switching songs while AudioContext resumes cannot start stale playback', async () => {
  const f = fixture(), resumed = deferred();
  await f.player.load('song', 900, 1);
  f.context.resume = () => resumed.promise;
  const play = f.player.play();
  f.player.pause();
  resumed.resolve(); await play;
  assert.equal(f.player.playing, false);
  assert.equal(f.sources.length, 0);
  assert.equal(f.player.current(null), false);
});

test('rapid seeking during a pending resume preserves playback at the last requested position', async () => {
  const f = fixture(), resumed = deferred();
  await f.player.load('song', 900, 1);
  await f.player.play();
  f.context.resume = () => resumed.promise;
  const firstSeek = f.player.seek(100);
  const lastSeek = f.player.seek(240);
  resumed.resolve();
  await Promise.all([firstSeek, lastSeek]);
  assert.equal(f.player.playing, true);
  assert.equal(f.player.time, 240);
  assert.equal(f.sources.length, 2);
  assert.equal(f.sources[1].offset, 240);
  assert.equal(f.requests.length, 1);
});
