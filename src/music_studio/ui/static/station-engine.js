(function (root) {
  "use strict";
  const uid = () =>
    typeof crypto !== "undefined"
      ? crypto.randomUUID().replaceAll("-", "").slice(0, 16)
      : Math.random().toString(16).slice(2).padEnd(16, "0");
  const duration = (content) =>
    Math.max(
      0,
      ...content.tracks.flatMap((t) =>
        t.clips.map((c) => c.start + c.duration),
      ),
    );
  const gain = (db) => 10 ** (db / 20);
  function audible(track, tracks) {
    return !track.mute && (!tracks.some((t) => t.solo) || track.solo);
  }
  function splitClip(clip, at) {
    const first = at - clip.start;
    if (first < 0.01 || clip.duration - first < 0.01) return null;
    const left = structuredClone(clip),
      right = structuredClone(clip);
    left.duration = first;
    left.fade_out = 0;
    left.fade_in = Math.min(left.fade_in, first);
    right.id = uid();
    right.start = at;
    right.offset += first;
    right.duration -= first;
    right.fade_in = 0;
    right.fade_out = Math.min(right.fade_out, right.duration);
    return [left, right];
  }
  function midiBuffer(ctx, clip, bpm, instrument) {
    const rate = ctx.sampleRate,
      seconds = clip.offset + clip.duration;
    const buffer = ctx.createBuffer(2, Math.ceil(seconds * rate), rate);
    const data = buffer.getChannelData(0),
      beat = 60 / bpm;
    for (const note of clip.notes) {
      const start = Math.round(note.start * beat * rate),
        end = Math.min(
          data.length,
          Math.ceil((note.start + note.length) * beat * rate),
        );
      const frequency = 440 * 2 ** ((note.pitch - 69) / 12),
        length = note.length * beat;
      for (let i = start; i < end; i++) {
        const x = i / rate - note.start * beat;
        if (x < 0 || x >= length) continue;
        const phase = 2 * Math.PI * frequency * x;
        const tone =
          instrument === "bass"
            ? Math.sin(phase) * 0.85 + Math.sin(phase * 2) * 0.15
            : (Math.sin(phase) +
                0.25 * Math.sin(phase * 2) +
                0.12 * Math.sin(phase * 3)) /
              1.37;
        const attack = instrument === "pad" ? 0.08 : 0.008;
        let envelope =
          Math.min(x / attack, 1) * Math.min((length - x) / 0.04, 1);
        if (instrument === "keys") envelope *= Math.exp(-x * 2);
        data[i] += ((tone * 0.2 * note.velocity) / 127) * envelope;
      }
    }
    buffer.copyToChannel(data, 1);
    return buffer;
  }
  class StationEngine {
    constructor(makeContext = () => new AudioContext({ sampleRate: 44100 })) {
      this.makeContext = makeContext;
      this.ctx = null;
      this.cache = new Map();
      this.nodes = [];
      this.graphs = new Map();
      this.playing = false;
      this.position = 0;
      this.epoch = 0;
    }
    context() {
      if (!this.ctx) {
        this.ctx = this.makeContext();
        this.master = this.ctx.createGain();
        this.masterAnalyser = this.ctx.createAnalyser();
        this.masterAnalyser.fftSize = 256;
        this.masterData = new Float32Array(256);
        this.master.connect(this.masterAnalyser);
        this.masterAnalyser.connect(this.ctx.destination);
      }
      return this.ctx;
    }
    current() {
      return this.playing
        ? this.position + this.ctx.currentTime - this.started
        : this.position;
    }
    pause() {
      this.position = this.current();
      this.playing = false;
      this.epoch++;
      for (const node of this.nodes) {
        try {
          node.stop();
        } catch (_) {}
        node.disconnect();
      }
      for (const graph of this.graphs.values())
        for (const node of graph.nodes) node.disconnect();
      this.nodes = [];
      this.graphs.clear();
    }
    reset() {
      this.pause();
      this.position = 0;
      this.cache.clear();
    }
    async buffer(key, url) {
      if (!this.cache.has(key)) {
        this.cache.set(
          key,
          fetch(url)
            .then((r) => {
              if (!r.ok) throw Error(`Audio HTTP ${r.status}`);
              return r.arrayBuffer();
            })
            .then((b) => this.context().decodeAudioData(b))
            .catch((e) => {
              this.cache.delete(key);
              throw e;
            }),
        );
      }
      return this.cache.get(key);
    }
    graph(track) {
      const ctx = this.context(),
        input = ctx.createGain(),
        splitter = ctx.createChannelSplitter(2);
      const left = ctx.createGain(),
        right = ctx.createGain(),
        merge = ctx.createChannelMerger(2);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      input.connect(splitter);
      splitter.connect(left, 0);
      splitter.connect(right, 1);
      left.connect(merge, 0, 0);
      right.connect(merge, 0, 1);
      merge.connect(analyser);
      analyser.connect(this.master);
      const graph = {
        input,
        left,
        right,
        analyser,
        data: new Float32Array(256),
        nodes: [input, splitter, left, right, merge, analyser],
      };
      this.graphs.set(track.id, graph);
      return graph;
    }
    update(content) {
      if (!this.ctx) return;
      this.master.gain.setTargetAtTime(
        gain(content.master_db),
        this.ctx.currentTime,
        0.015,
      );
      for (const t of content.tracks) {
        const g = this.graphs.get(t.id);
        if (!g) continue;
        g.input.gain.setTargetAtTime(
          audible(t, content.tracks) ? gain(t.gain_db) : 0,
          this.ctx.currentTime,
          0.015,
        );
        g.left.gain.setTargetAtTime(
          t.pan > 0 ? Math.cos((t.pan * Math.PI) / 2) : 1,
          this.ctx.currentTime,
          0.015,
        );
        g.right.gain.setTargetAtTime(
          t.pan < 0 ? Math.cos((-t.pan * Math.PI) / 2) : 1,
          this.ctx.currentTime,
          0.015,
        );
      }
    }
    async play(content, assets, project, at = this.position) {
      this.pause();
      const epoch = this.epoch,
        ctx = this.context();
      await ctx.resume();
      const needed = new Set(
        content.tracks.flatMap((t) =>
          t.clips.filter((c) => c.asset).map((c) => c.asset),
        ),
      );
      const keep = new Set([...needed].map((id) => project + ":" + id));
      for (const track of content.tracks)
        if (track.kind === "midi")
          for (const clip of track.clips)
            keep.add(
              JSON.stringify([
                content.bpm,
                track.instrument,
                clip.offset,
                clip.duration,
                clip.notes,
              ]),
            );
      for (const key of this.cache.keys())
        if (!keep.has(key)) this.cache.delete(key);
      const bytes =
        [...needed].reduce(
          (sum, id) =>
            sum + (assets.find((a) => a.id === id)?.duration || 0) * 44100 * 8,
          0,
        ) +
        content.tracks
          .flatMap((t) => (t.kind === "midi" ? t.clips : []))
          .reduce((s, c) => s + (c.offset + c.duration) * 44100 * 8, 0);
      if (bytes > 256 * 1024 * 1024)
        throw Error(
          "Preview memory limit (256 MiB). Use a shorter arrangement.",
        );
      const buffers = new Map();
      await Promise.all(
        [...needed].map(async (id) =>
          buffers.set(
            id,
            await this.buffer(
              project + ":" + id,
              `/api/workstation/projects/${project}/audio/${id}`,
            ),
          ),
        ),
      );
      if (epoch !== this.epoch) return false;
      for (const track of content.tracks)
        if (track.kind === "midi")
          for (const clip of track.clips) {
            const key = JSON.stringify([
              content.bpm,
              track.instrument,
              clip.offset,
              clip.duration,
              clip.notes,
            ]);
            if (!this.cache.has(key))
              this.cache.set(
                key,
                midiBuffer(ctx, clip, content.bpm, track.instrument),
              );
            buffers.set(clip.id, this.cache.get(key));
          }
      if (epoch !== this.epoch) return false;
      this.position = at;
      this.started = ctx.currentTime + 0.04;
      this.master.gain.setValueAtTime(gain(content.master_db), ctx.currentTime);
      for (const track of content.tracks) {
        const graph = this.graph(track);
        graph.input.gain.value = audible(track, content.tracks)
          ? gain(track.gain_db)
          : 0;
        graph.left.gain.value =
          track.pan > 0 ? Math.cos((track.pan * Math.PI) / 2) : 1;
        graph.right.gain.value =
          track.pan < 0 ? Math.cos((-track.pan * Math.PI) / 2) : 1;
        for (const clip of track.clips) {
          const skip = Math.max(0, at - clip.start),
            length = clip.duration - skip;
          if (length <= 0) continue;
          const source = ctx.createBufferSource(),
            level = ctx.createGain();
          source.buffer = buffers.get(clip.asset || clip.id);
          source.connect(level);
          level.connect(graph.input);
          source.onended = () => {
            source.disconnect();
            level.disconnect();
          };
          const when = this.started + Math.max(0, clip.start - at),
            amp = gain(clip.gain_db);
          const points = [
            ...new Set([
              skip,
              clip.duration,
              Math.max(skip, clip.fade_in),
              Math.max(skip, clip.duration - clip.fade_out),
            ]),
          ]
            .filter((s) => s >= skip && s <= clip.duration)
            .sort((a, b) => a - b);
          const envelope = (s) =>
            Math.max(
              0,
              Math.min(1, clip.fade_in ? s / clip.fade_in : 1) *
                Math.min(
                  1,
                  clip.fade_out ? (clip.duration - s) / clip.fade_out : 1,
                ),
            ) * amp;
          level.gain.setValueAtTime(envelope(skip), when);
          for (const s of points.slice(1))
            level.gain.linearRampToValueAtTime(envelope(s), when + s - skip);
          source.start(when, clip.offset + skip, length);
          this.nodes.push(source);
        }
      }
      this.playing = true;
      this.update(content);
      return true;
    }
    meter(id) {
      const graph = this.graphs.get(id);
      if (!graph || !this.playing) return 0;
      graph.analyser.getFloatTimeDomainData(graph.data);
      return Math.sqrt(
        graph.data.reduce((n, x) => n + x * x, 0) / graph.data.length,
      );
    }
    async note(pitch, instrument = "keys") {
      // Audition uses the same basic synthesis as clips and offline export.
      const ctx = this.context();
      await ctx.resume();
      const source = ctx.createBufferSource();
      source.buffer = midiBuffer(
        ctx,
        {
          offset: 0,
          duration: 0.5,
          notes: [{ pitch, start: 0, length: 1, velocity: 85 }],
        },
        120,
        instrument,
      );
      source.connect(this.master);
      source.onended = () => source.disconnect();
      source.start();
    }
    masterMeter() {
      if (!this.masterAnalyser || !this.playing) return 0;
      this.masterAnalyser.getFloatTimeDomainData(this.masterData);
      return Math.sqrt(
        this.masterData.reduce((sum, x) => sum + x * x, 0) /
          this.masterData.length,
      );
    }
  }
  const api = { StationEngine, uid, duration, audible, splitClip, midiBuffer };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.Station = api;
})(typeof window !== "undefined" ? window : globalThis);
