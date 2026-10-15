/* Audio sessions are independent of project-status polling. */
(function (root) {
  "use strict";
  const effectiveVersion = (job, legacy) => legacy ? "original" : job.current_version || "original";
  const resultKey = (id, version) => `${id}:${version}`;
  const shouldLoadResult = (job, legacy, loaded, pending) => {
    const key = resultKey(job.id, effectiveVersion(job, legacy));
    return (job.has_result || job.status === "complete") && key !== loaded && key !== pending;
  };

  class Player {
    constructor(options = {}) {
      this.options = options;
      this.context = null;
      this.buffers = {};
      this.nodes = [];
      this.melodyNodes = [];
      this.gains = {};
      this.ready = false;
      this.playing = false;
      this.playIntent = false;
      this.offset = 0;
      this.anchor = 0;
      this.duration = 0;
      this.session = null;
      this.playRequest = 0;
    }
    update() { this.options.onUpdate?.(); }
    current(session) {
      return !!session && this.session === session && !session.controller.signal.aborted &&
        (!this.options.getGeneration || this.options.getGeneration() === session.generation);
    }
    get time() {
      return Math.min(this.duration, this.offset + (this.playing ? Math.max(0, this.context.currentTime - this.anchor) : 0));
    }
    isLoading(kind) { return !!this.session?.pending[kind]; }
    async load(projectId, duration, generation, version = "original") {
      const key = resultKey(projectId, version);
      if (this.session?.key === key && !this.session.controller.signal.aborted) {
        this.session.generation = generation;
        return this.ensureTrack("source");
      }
      this.reset();
      this.duration = duration;
      this.context ||= this.options.contextFactory?.() || new AudioContext();
      this.session = {key, projectId, version, generation, controller: new AbortController(), pending: {}};
      // Load only the source. Stems are fetched and decoded on explicit selection.
      return this.ensureTrack("source");
    }
    async ensureTrack(kind) {
      if (kind === "melody" || this.buffers[kind]) return this.buffers[kind];
      const session = this.session;
      if (!session || !this.current(session)) return;
      if (session.pending[kind]) return session.pending[kind];
      const fetcher = this.options.fetcher || fetch;
      const promise = (async () => {
        const response = await fetcher(`/api/projects/${session.projectId}/assets/${kind}?version=${encodeURIComponent(session.version)}`, {signal: session.controller.signal});
        if (!response.ok) throw new Error(typeof MusicI18n === "object" ? MusicI18n.t("音轨载入失败，请再次点击音轨重试") : "Audio could not load. Click the track to retry.");
        const bytes = await response.arrayBuffer();
        if (!this.current(session)) return;
        const buffer = await this.context.decodeAudioData(bytes);
        if (!this.current(session)) return;
        this.buffers[kind] = buffer;
        if (kind === "source") this.ready = true;
        // A newly requested stem joins the existing clock without pausing playback.
        if (this.playing && this.gains[kind]) {
          const at = this.context.currentTime + 0.025;
          const offset = this.offset + Math.max(0, at - this.anchor);
          if (offset < buffer.duration) this.startBuffer(kind, buffer, at, offset);
        }
        return buffer;
      })();
      session.pending[kind] = promise;
      this.update();
      try { return await promise; }
      finally {
        if (session.pending[kind] === promise) delete session.pending[kind];
        if (this.session === session) this.update();
      }
    }
    startBuffer(kind, buffer, at, offset) {
      const source = this.context.createBufferSource();
      source.buffer = buffer;
      source.connect(this.gains[kind]);
      source.start(at, offset);
      this.nodes.push(source);
    }
    stopMelody() {
      for (const node of this.melodyNodes) {
        try { node.stop(); node.disconnect(); } catch (_) {}
      }
      this.melodyNodes = [];
    }
    stopNodes() {
      for (const node of this.nodes) {
        try { node.stop(); node.disconnect(); } catch (_) {}
      }
      this.nodes = [];
      this.stopMelody();
      for (const gain of Object.values(this.gains)) gain.disconnect();
      this.gains = {};
    }
    pause() {
      ++this.playRequest;
      this.playIntent = false;
      if (this.playing) this.offset = this.time;
      this.playing = false;
      this.stopNodes();
      this.update();
    }
    reset() {
      this.session?.controller.abort();
      this.session = null;
      this.pause();
      this.offset = 0;
      this.ready = false;
      this.buffers = {};
      this.duration = 0;
    }
    async play() {
      if (!this.ready) return;
      const session = this.session;
      const request = ++this.playRequest;
      this.playIntent = true;
      try { await this.context.resume(); }
      catch (error) {
        if (request === this.playRequest) this.playIntent = false;
        throw error;
      }
      if (!this.ready || !this.current(session) || request !== this.playRequest || this.playing) return;
      if (this.offset >= this.duration - .01) this.offset = 0;
      this.anchor = this.context.currentTime + .025;
      for (const kind of ["source", "vocals", "instrumental", "melody"]) {
        const gain = this.context.createGain();
        gain.connect(this.context.destination);
        this.gains[kind] = gain;
      }
      this.playing = true;
      this.setMix();
      for (const [kind, buffer] of Object.entries(this.buffers)) this.startBuffer(kind, buffer, this.anchor, this.offset);
      this.update();
    }
    scheduleMelody() {
      const now = this.time;
      for (const note of this.options.getNotes?.() || []) {
        if (note.end <= now) continue;
        const at = Math.max(this.context.currentTime + .01, this.anchor + note.start - this.offset);
        const end = this.anchor + note.end - this.offset;
        if (end <= at) continue;
        const oscillator = this.context.createOscillator(), envelope = this.context.createGain();
        oscillator.type = "triangle";
        oscillator.frequency.value = 440 * Math.pow(2, (note.pitch - 69) / 12);
        const attack = Math.min(at + .012, end), release = Math.max(attack, end - .025);
        envelope.gain.setValueAtTime(0, at);
        envelope.gain.linearRampToValueAtTime(.22, attack);
        envelope.gain.setValueAtTime(.22, release);
        envelope.gain.linearRampToValueAtTime(0, end);
        oscillator.connect(envelope);
        envelope.connect(this.gains.melody);
        oscillator.onended = () => envelope.disconnect();
        oscillator.start(at);
        oscillator.stop(end);
        this.melodyNodes.push(oscillator);
      }
    }
    setMix() {
      if (!this.context) return;
      const mode = this.options.getMode?.() || "source", volume = this.options.getVolume?.() ?? .7;
      for (const [kind, gain] of Object.entries(this.gains)) {
        const guide = mode === "instrumental" && kind === "vocals" ? (this.options.getGuideVolume?.() || 0) : 0;
        gain.gain.setTargetAtTime((kind === mode ? 1 : guide) * volume, this.context.currentTime, .008);
      }
      if (this.playing && mode === "melody" && !this.melodyNodes.length) this.scheduleMelody();
      else if (mode !== "melody") this.stopMelody();
    }
    async seek(time) {
      const wasPlaying = this.playing || this.playIntent;
      this.pause();
      this.offset = Math.max(0, Math.min(this.duration, time));
      if (wasPlaying) await this.play();
      this.options.onSeek?.();
    }
  }
  const exported = {Player, effectiveVersion, resultKey, shouldLoadResult};
  if (typeof module !== "undefined" && module.exports) module.exports = exported;
  else root.MusicPlayback = exported;
})(typeof window !== "undefined" ? window : globalThis);
