const test = require("node:test");
const assert = require("node:assert/strict");
const {
  StationEngine,
  splitClip,
  audible,
  midiBuffer,
} = require("../src/music_studio/ui/static/station-engine.js");

test("splitting retains source offset and notes, with no overlapping fades", () => {
  const clip = {
    id: "0123456789abcdef",
    start: 2,
    offset: 3,
    duration: 5,
    fade_in: 0.5,
    fade_out: 1,
    notes: [{ pitch: 60, start: 0, length: 1, velocity: 90 }],
  };
  const parts = splitClip(clip, 4);
  assert.equal(parts[0].duration, 2);
  assert.equal(parts[1].start, 4);
  assert.equal(parts[1].offset, 5);
  assert.equal(parts[1].duration, 3);
  assert.equal(parts[0].fade_out, 0);
  assert.equal(parts[1].fade_in, 0);
  assert.deepEqual(parts[1].notes, clip.notes);
  assert.equal(clip.duration, 5);
  assert.equal(splitClip(clip, 2), null);
  assert.equal(splitClip(clip, 7), null);
});
test("mute overrides solo, and solo excludes other tracks", () => {
  const a = { mute: false, solo: false },
    b = { mute: false, solo: true };
  assert.equal(audible(a, [a, b]), false);
  assert.equal(audible(b, [a, b]), true);
  b.mute = true;
  assert.equal(audible(b, [a, b]), false);
});
class FakeContext {
  constructor() {
    this.sampleRate = 1000;
    this.currentTime = 0;
    this.destination = {};
    this.sources = [];
  }
  async resume() {}
  createBuffer(ch, length) {
    const data = Array.from({ length: ch }, () => new Float32Array(length));
    return {
      getChannelData: (i) => data[i],
      copyToChannel: (d, i) => data[i].set(d),
    };
  }
  node() {
    return {
      gain: {
        value: 1,
        setValueAtTime() {},
        setTargetAtTime() {},
        linearRampToValueAtTime() {},
      },
      connect() {},
      disconnect() {},
      getFloatTimeDomainData(a) {
        a.fill(0);
      },
    };
  }
  createGain() {
    return this.node();
  }
  createChannelSplitter() {
    return this.node();
  }
  createChannelMerger() {
    return this.node();
  }
  createAnalyser() {
    return this.node();
  }
  createBufferSource() {
    const node = this.node();
    node.start = (...args) => (node.started = args);
    node.stop = () => (node.stopped = true);
    this.sources.push(node);
    return node;
  }
  async decodeAudioData() {
    return this.createBuffer(2, 1000);
  }
}
test("MIDI synthesis makes finite identical stereo channels and keeps silence around notes", () => {
  const ctx = new FakeContext();
  const b = midiBuffer(
    ctx,
    {
      offset: 0,
      duration: 1,
      notes: [{ pitch: 60, start: 0.5, length: 0.5, velocity: 100 }],
    },
    120,
    "keys",
  );
  const data = b.getChannelData(0);
  assert.ok(data.every(Number.isFinite));
  assert.ok(data.slice(0, 250).every((x) => x === 0));
  assert.ok(data.some((x) => Math.abs(x) > 0.01));
  assert.deepEqual(data, b.getChannelData(1));
  assert.ok(data.slice(500).every((x) => x === 0));
});
test("task/UI refresh and live mix updates never reload audio; pause cancels an in-flight start", async () => {
  const oldFetch = global.fetch;
  let loads = 0,
    release;
  global.fetch = async () => {
    loads++;
    return { ok: true, arrayBuffer: async () => new ArrayBuffer(4) };
  };
  try {
    const ctx = new FakeContext(),
      engine = new StationEngine(() => ctx);
    const track = {
      id: "a",
      gain_db: 0,
      pan: 0,
      mute: false,
      solo: false,
      kind: "audio",
      clips: [
        {
          id: "c",
          asset: "source",
          start: 1,
          offset: 0,
          duration: 1,
          gain_db: 0,
          fade_in: 0,
          fade_out: 0,
        },
      ],
    };
    const content = { tracks: [track], master_db: -6 },
      assets = [{ id: "source", duration: 1 }];
    await engine.play(content, assets, "project", 0);
    assert.equal(ctx.sources[0].started[0], 1.04);
    for (let i = 0; i < 100; i++) {
      track.gain_db = -i / 10;
      engine.update(content);
    }
    assert.equal(loads, 1);
    assert.equal(ctx.sources.length, 1);
    engine.pause();
    await engine.play(content, assets, "project", 0.5);
    assert.equal(loads, 1);
    engine.reset();
    global.fetch = () => new Promise((resolve) => (release = resolve));
    const pending = engine.play(content, assets, "project", 0);
    await new Promise((r) => setImmediate(r));
    engine.pause();
    release({ ok: true, arrayBuffer: async () => new ArrayBuffer(4) });
    assert.equal(await pending, false);
    assert.equal(engine.playing, false);
  } finally {
    global.fetch = oldFetch;
  }
});
