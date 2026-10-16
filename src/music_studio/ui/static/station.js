"use strict";
(() => {
  const $ = (id) => document.getElementById(id),
    { uid, duration, splitClip, StationEngine } = Station;
  const engine = new StationEngine(),
    colors = ["#b69aff", "#86c9bc", "#e7b985", "#8cabed", "#d592b5"];
  const s = {
    session: null,
    track: null,
    clip: null,
    view: "assets",
    dock: "mixer",
    zoom: 38,
    position: 0,
    loop: false,
    dirty: false,
    change: 0,
    saving: null,
    models: [],
    tasks: [],
    lang: localStorage.getItem("station-language") || "zh",
  };
  let saveTimer,
    toastTimer,
    polling = false,
    starting = false;
  const words = {
    projects: "Sessions",
    new: "New",
    previous: "Previous workbench ↗",
    export: "Export",
    assets: "Sound library",
    assetsTab: "Assets",
    instruments: "Instruments",
    models: "AI models",
    import: "Import audio",
    sessionAssets: "SESSION ASSETS",
    demoTitle: "A starting point for your sound",
    demoCopy: "Explore arrangement and mixing with an editable sketch.",
    demo: "Open demo session ↗",
    instrumentCopy:
      "Start with notes and choose a sound. Double-click the piano roll to add or remove notes.",
    instrumentNote:
      "Built-in synth sounds need no download. Sampling, sound libraries and third-party plugins will follow.",
    modelCopy:
      "Process the selected clip’s full source audio. Add results directly as new tracks.",
    comingModels: "Creation models · Planned",
    notIntegrated: "Not integrated; cannot run yet.",
    local: "Local production · Your sound stays here",
    signature: "METER",
    ready: "Ready",
    arrangement: "Arrange",
    snap: "Snap",
    tracks: "TRACKS",
    addAudio: "＋ Audio track",
    addMidi: "＋ Instrument track",
    dropHint: "Drop audio here to build your sound.",
    emptyTitle: "Your next piece starts here.",
    emptyCopy: "Import a recording, write a melody or explore the demo.",
    mixer: "Mixer",
    piano: "Piano roll",
    tasks: "Tasks",
    mixerHint: "Listen, adjust and find your balance.",
    inspector: "Inspector",
    workflowNote: "Audio, notes and model outputs belong to one music project.",
    shortcutHint:
      "Space Play/Pause · Ctrl Z Undo · Double-click a clip to edit",
    exportCopy:
      "Export this arrangement with track gain, pan, mute/solo and clip fades.",
    mixExport: "Stereo mix · 44.1 kHz",
    midiExport: "Instrument tracks · Notes, velocity and tempo",
    projectFile: "Project snapshot",
    projectExport: "JSON arrangement; audio assets remain on this computer",
  };
  const chinese = new WeakMap(),
    tr = (zh, en) => (s.lang === "zh" ? zh : en);
  const esc = (x) =>
    String(x ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  const icon = (name) => `<svg><use href="#i-${name}"/></svg>`;
  const content = () => s.session.content;
  const selectedTrack = () => content().tracks.find((t) => t.id === s.track);
  const selectedClip = () =>
    selectedTrack()?.clips.find((c) => c.id === s.clip);
  const asset = (id) => s.session.assets.find((a) => a.id === id);
  const seconds = (value) =>
    `${Math.floor(Math.max(0, value) / 60)
      .toString()
      .padStart(
        2,
        "0",
      )}:${(Math.max(0, value) % 60).toFixed(2).padStart(5, "0")}`;
  const beatSeconds = () => 60 / content().bpm;
  const snap = (value) =>
    $("snap").checked
      ? Math.round(value / (beatSeconds() / 4)) * (beatSeconds() / 4)
      : value;
  function toast(message, error = false) {
    $("toast").textContent = message;
    $("toast").classList.toggle("error", error);
    $("toast").hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(
      () => ($("toast").hidden = true),
      error ? 9000 : 3500,
    );
  }
  async function request(url, body, method = "POST") {
    const opts =
      body === undefined
        ? {}
        : {
            method,
            body: body instanceof FormData ? body : JSON.stringify(body),
            headers:
              body instanceof FormData
                ? {}
                : { "Content-Type": "application/json" },
          };
    const response = await fetch(url, opts);
    let data;
    try {
      data = await response.json();
    } catch (_) {
      throw Error(`HTTP ${response.status}`);
    }
    if (!response.ok)
      throw Error(
        typeof data.detail === "string"
          ? data.detail
          : JSON.stringify(data.detail || data),
      );
    return data;
  }
  const base = () => `/api/workstation/projects/${s.session.id}`;
  function guarded(fn) {
    return async (...args) => {
      try {
        await fn(...args);
      } catch (e) {
        toast(e.message, true);
      }
    };
  }
  function localize() {
    document.documentElement.lang = s.lang === "zh" ? "zh-CN" : "en";
    document.querySelectorAll("[data-t]").forEach((el) => {
      if (el.id === "audio-status") return;
      if (!chinese.has(el)) chinese.set(el, el.textContent);
      el.textContent =
        s.lang === "zh"
          ? chinese.get(el)
          : words[el.dataset.t] || chinese.get(el);
    });
    $("language").textContent = s.lang === "zh" ? "EN" : "中文";
    $("asset-search").placeholder = tr("搜索素材…", "Search assets…");
    $("project-title").setAttribute(
      "aria-label",
      tr("工程名称", "Session name"),
    );
    $("audio-status").textContent = engine.playing
      ? tr("正在播放", "Playing")
      : starting
        ? tr("准备音频…", "Preparing audio…")
        : tr("准备就绪", "Ready");
  }
  function savedLabel() {
    $("save-state").textContent = s.saving
      ? tr("保存中…", "Saving…")
      : s.dirty
        ? tr("尚未保存", "Unsaved")
        : tr("✓ 已保存到本机", "✓ Saved locally");
  }
  function dirty() {
    s.dirty = true;
    s.change++;
    savedLabel();
    clearTimeout(saveTimer);
    saveTimer = setTimeout(
      () => flush().catch((e) => toast(e.message, true)),
      450,
    );
  }
  async function flush() {
    clearTimeout(saveTimer);
    if (s.saving) await s.saving;
    if (!s.dirty) return;
    s.saving = (async () => {
      while (s.dirty) {
        const serial = s.change,
          snapshot = structuredClone(content());
        const result = await request(
          base(),
          { revision: s.session.revision, content: snapshot },
          "PUT",
        );
        s.session.revision = result.revision;
        s.session.can_undo = result.can_undo;
        s.session.can_redo = result.can_redo;
        if (serial === s.change) s.dirty = false;
      }
    })();
    savedLabel();
    try {
      await s.saving;
    } finally {
      s.saving = null;
      savedLabel();
      updateHistoryButtons();
    }
  }
  function pause() {
    engine.pause();
    s.position = Math.max(0, engine.position);
    $("play").innerHTML = icon("play");
    $("audio-status").textContent = tr("准备就绪", "Ready");
  }
  function mutate(fn, { live = false, render = true } = {}) {
    if (!live) pause();
    fn();
    dirty();
    if (live) engine.update(content());
    if (render) renderAll();
  }
  function accept(session, { selectLast = false } = {}) {
    const changedProject = session.id !== s.session?.id;
    s.session = session;
    s.dirty = false;
    s.change = 0;
    if (selectLast) {
      const t = content().tracks.at(-1);
      s.track = t?.id;
      s.clip = t?.clips[0]?.id;
    }
    if (!selectedTrack()) {
      s.track = content().tracks[0]?.id;
      s.clip = content().tracks[0]?.clips[0]?.id;
    }
    history.replaceState({}, "", `/station.html?session=${session.id}`);
    localStorage.setItem("station-session", session.id);
    if (changedProject && duration(content()) > 0)
      s.zoom = Math.max(
        12,
        Math.min(
          38,
          ($("arranger").clientWidth - headWidth() - 15) /
            (duration(content()) + (60 / content().bpm) * 2),
        ),
      );
    renderAll();
  }
  async function open(key) {
    await flush();
    engine.reset();
    s.position = 0;
    s.track = null;
    s.clip = null;
    accept(await request(`/api/workstation/projects/${key}`));
    s.tasks = [];
    renderTasks();
  }
  async function create(demo = false) {
    await flush();
    engine.reset();
    s.position = 0;
    s.track = null;
    s.clip = null;
    accept(
      await request("/api/workstation/projects", {
        title: demo ? "Midnight Sketch" : tr("未命名工程", "Untitled session"),
        demo,
      }),
    );
    if (demo)
      toast(
        tr(
          "内置合成示例已载入，可自由编排和混音。",
          "Built-in synth demo loaded. Arrange and mix freely.",
        ),
      );
  }
  function headWidth() {
    return (
      parseFloat(
        getComputedStyle(document.documentElement).getPropertyValue(
          "--track-head",
        ),
      ) || 188
    );
  }
  function renderAll() {
    if (!s.session) return;
    localize();
    $("browser-title").textContent = {
      assets: tr("声音素材", "Sound library"),
      instruments: tr("乐器与音色", "Instruments"),
      models: tr("本地 AI 模型", "Local AI models"),
    }[s.view];
    $("project-title").value = content().title;
    $("bpm").value = content().bpm;
    renderAssets();
    renderTracks();
    renderMixer();
    renderInspector();
    if (s.dock === "piano") renderPiano();
    renderInstruments();
    updateHistoryButtons();
    savedLabel();
    $("session-summary").textContent = tr(
      `${content().tracks.length} 轨道 · ${s.session.assets.length} 素材`,
      `${content().tracks.length} tracks · ${s.session.assets.length} assets`,
    );
  }
  function updateHistoryButtons() {
    $("undo").disabled = !s.session?.can_undo;
    $("redo").disabled = !s.session?.can_redo;
  }
  function renderAssets() {
    $("asset-count").textContent = s.session.assets.length;
    const query = $("asset-search").value.toLowerCase();
    $("asset-list").innerHTML =
      s.session.assets
        .filter((a) => a.name.toLowerCase().includes(query))
        .map(
          (a, i) =>
            `<button class="asset-item" draggable="true" data-asset="${a.id}" style="--color:${colors[i % colors.length]}" title="${tr("点击添加到轨道，或拖入编排区", "Click to add a track, or drag into the arrangement")}"><span class="asset-symbol">${icon("wave")}</span><span><strong>${esc(a.name)}</strong><small>WAV · ${seconds(a.duration).slice(0, 5)}</small></span><span class="asset-add">＋</span></button>`,
        )
        .join("") ||
      `<p class="empty-assets">${tr("素材导入后会出现在这里", "Imported assets appear here")}</p>`;
  }
  function renderTracks() {
    const bar = beatSeconds() * 4,
      end = Math.max(bar * 12, Math.ceil(duration(content()) / bar + 2) * bar),
      width = Math.ceil(end * s.zoom);
    $("arrangement-content").style.width = `${width + headWidth()}px`;
    $("arrangement-content").style.setProperty(
      "--bar-width",
      `${bar * s.zoom}px`,
    );
    $("ruler-ticks").innerHTML = Array.from(
      { length: Math.ceil(end / bar) },
      (_, i) => `<span style="left:${i * bar * s.zoom}px">${i + 1}</span>`,
    ).join("");
    $("track-list").innerHTML = content()
      .tracks.map(
        (t, i) =>
          `<div class="track ${t.id === s.track ? "selected" : ""}" style="--color:${t.color}" data-track="${t.id}"><div class="track-header"><div class="track-title-row">${icon(t.kind === "midi" ? "keys" : "wave")}<span class="track-name">${esc(t.name)}</span><span class="track-number">${String(i + 1).padStart(2, "0")}</span></div><div class="track-controls"><button class="mini-toggle mute ${t.mute ? "active" : ""}" data-toggle="mute" aria-label="${esc(t.name)} ${tr("静音", "mute")}" aria-pressed="${t.mute}">M</button><button class="mini-toggle ${t.solo ? "active" : ""}" data-toggle="solo" aria-label="${esc(t.name)} ${tr("独奏", "solo")}" aria-pressed="${t.solo}">S</button><input class="track-gain" type="range" min="-60" max="12" step=".5" value="${t.gain_db}" aria-label="${esc(t.name)} ${tr("音量", "level")}" data-level="${t.id}"><button class="track-delete" data-remove-track="${t.id}" aria-label="${tr("删除轨道", "Delete track")} ${esc(t.name)}">×</button></div></div><div class="track-lane" data-lane="${t.id}">${t.clips.map((c) => `<div class="clip ${c.id === s.clip ? "selected" : ""}" tabindex="0" role="button" aria-label="${esc(c.name)} ${tr("片段", "clip")}" data-clip="${c.id}" style="left:${c.start * s.zoom}px;width:${Math.max(12, c.duration * s.zoom)}px"><div class="clip-label">${esc(c.name)}</div><canvas data-wave="${c.id}"></canvas><span class="clip-handle"></span></div>`).join("")}</div></div>`,
      )
      .join("");
    $("empty-guide").hidden = content().tracks.length > 0;
    $("split").disabled = !selectedClip();
    $("duplicate").disabled = !selectedClip();
    $("delete-clip").disabled = !selectedClip();
    for (const t of content().tracks) for (const c of t.clips) drawClip(t, c);
  }
  function drawClip(t, c) {
    const canvas = document.querySelector(`[data-wave="${c.id}"]`);
    if (!canvas) return;
    const width = Math.max(12, Math.ceil(c.duration * s.zoom)),
      h = 49,
      dpr = devicePixelRatio || 1;
    // Avoid allocating an enormous bitmap for a long zoomed-in recording.
    canvas.width = Math.min(width, 8192) * dpr;
    canvas.height = h * dpr;
    const ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);
    ctx.scale(Math.min(width, 8192) / width, 1);
    ctx.fillStyle = t.color;
    if (t.kind === "audio") {
      const a = asset(c.asset);
      if (!a) return;
      const peak = Math.max(0.01, ...a.waveform);
      for (let x = 0; x < width; x += 3) {
        const time = c.offset + x / s.zoom,
          index = Math.min(
            a.waveform.length - 1,
            Math.floor((time / a.duration) * a.waveform.length),
          );
        const amp = (a.waveform[index] / peak) * 20;
        ctx.fillRect(x, h / 2 - amp, 1.3, Math.max(1, amp * 2));
      }
    } else {
      const pitches = c.notes.map((n) => n.pitch),
        low = Math.min(45, ...pitches),
        high = Math.max(80, ...pitches);
      for (const n of c.notes) {
        const start = n.start * beatSeconds() - c.offset,
          stop = start + n.length * beatSeconds();
        if (stop < 0 || start > c.duration) continue;
        ctx.fillRect(
          Math.max(0, start * s.zoom),
          4 + ((high - n.pitch) / (high - low)) * 35,
          Math.max(
            2,
            (Math.min(stop, c.duration) - Math.max(0, start)) * s.zoom - 1,
          ),
          3,
        );
      }
    }
  }
  function renderMixer() {
    $("mixer").innerHTML =
      content()
        .tracks.map(
          (t) =>
            `<div class="channel ${s.track === t.id ? "selected" : ""}" data-channel="${t.id}" style="--color:${t.color}"><span class="channel-name">${esc(t.name)}</span><input class="channel-pan" type="range" min="-1" max="1" step=".05" value="${t.pan}" data-pan="${t.id}" aria-label="${esc(t.name)} ${tr("声像", "pan")}"><div class="fader-row"><input type="range" min="-60" max="12" step=".5" value="${t.gain_db}" data-level="${t.id}" aria-label="${esc(t.name)} ${tr("推子", "fader")}"><div class="vu"><span data-vu="${t.id}"></span></div></div><span class="channel-db" data-db="${t.id}">${t.gain_db.toFixed(1)} dB</span><div class="channel-buttons"><button class="mini-toggle mute ${t.mute ? "active" : ""}" data-mixer-toggle="mute" data-id="${t.id}" aria-label="${esc(t.name)} ${tr("混音静音", "mixer mute")}" aria-pressed="${t.mute}">M</button><button class="mini-toggle ${t.solo ? "active" : ""}" data-mixer-toggle="solo" data-id="${t.id}" aria-label="${esc(t.name)} ${tr("混音独奏", "mixer solo")}" aria-pressed="${t.solo}">S</button></div></div>`,
        )
        .join("") +
      `<div class="channel master-channel"><span class="channel-name">MASTER</span><span class="channel-db">STEREO OUT</span><div class="fader-row"><input type="range" min="-60" max="6" step=".5" value="${content().master_db}" data-master aria-label="${tr("主输出音量", "Master output")}"><div class="vu"><span id="master-vu"></span></div></div><span class="channel-db" id="master-db">${content().master_db.toFixed(1)} dB</span><span class="channel-db">${tr("主输出", "Master")}</span></div>`;
  }
  const field = (label, key, value, attrs = "") =>
    `<label class="field-row"><span>${label}</span><input type="number" data-field="${key}" value="${Number(value.toFixed(6))}" ${attrs.replace(/step="[^"]+"/, 'step="any"')}></label>`;
  function renderInspector() {
    const t = selectedTrack(),
      c = selectedClip();
    if (!t) {
      $("inspector-content").innerHTML =
        `<div class="selection-tag">SESSION</div><div class="selection-name">${esc(content().title)}</div><div class="selection-subtitle">${tr("本地音乐工程", "Local music project")}</div><div class="inspector-section"><h3>${tr("开始制作", "MAKE SOMETHING")}</h3><p>${tr("导入音频创建轨道，或从乐器页开始写旋律。所有操作会自动保存在本机。", "Import audio to create a track, or choose an instrument and write notes. Changes are saved locally.")}</p></div>`;
      return;
    }
    $("inspector-content").innerHTML =
      `<div class="selection-tag" style="--color:${t.color}">● ${t.kind === "midi" ? "INSTRUMENT" : "AUDIO"} ${c ? "CLIP" : "TRACK"}</div><div class="selection-name">${esc(c?.name || t.name)}</div><div class="selection-subtitle">${c ? seconds(c.duration) + " · " : ""}${tr("可撤销编辑", "Reversible edits")}</div><section class="inspector-section"><h3>${tr("轨道设置", "TRACK")}</h3><label class="field-row"><span>${tr("名称", "Name")}</span><input type="text" data-track-name value="${esc(t.name)}" maxlength="150"></label>${field(tr("音量 · dB", "Level · dB"), "track.gain_db", t.gain_db, 'min="-60" max="12" step=".5"')}${field(tr("声像 · L / R", "Pan · L / R"), "track.pan", t.pan, 'min="-1" max="1" step=".05"')}${t.kind === "midi" ? `<label class="field-row"><span>${tr("音色", "Sound")}</span><select data-instrument>${["keys", "bass", "pad"].map((k) => `<option value="${k}" ${t.instrument === k ? "selected" : ""}>${instrumentName(k)}</option>`).join("")}</select></label>` : ""}</section>${c ? `<section class="inspector-section"><h3>${tr("片段位置 · 秒", "CLIP POSITION · SECONDS")}</h3>${field(tr("开始位置", "Start"), "clip.start", c.start, 'min="0" max="599" step=".1"')}${field(tr("素材起点", "Source offset"), "clip.offset", c.offset, 'min="0" max="599" step=".1"')}${field(tr("片段长度", "Duration"), "clip.duration", c.duration, 'min=".01" max="600" step=".1"')}${field(tr("片段增益 · dB", "Clip gain · dB"), "clip.gain_db", c.gain_db, 'min="-60" max="12" step=".5"')}</section><section class="inspector-section"><h3>${tr("淡入与淡出 · 秒", "FADES · SECONDS")}</h3>${field(tr("淡入", "Fade in"), "clip.fade_in", c.fade_in, 'min="0" max="30" step=".05"')}${field(tr("淡出", "Fade out"), "clip.fade_out", c.fade_out, 'min="0" max="30" step=".05"')}</section><div class="inspector-buttons"><button data-inspect-duplicate>${tr("复制片段", "Duplicate")}</button><button data-inspect-remove>${tr("移除片段", "Remove")}</button></div>` : ""}<section class="inspector-section"><h3>${tr("制作提示", "TIP")}</h3><p>${tr(t.kind === "midi" ? "双击片段打开钢琴卷帘。双击网格添加音符，双击音符移除。" : "拖动片段改变位置；拖动右侧边缘改变长度。M 静音，S 独奏。", t.kind === "midi" ? "Double-click the clip to open the piano roll. Double-click the grid to add a note or a note to remove it." : "Drag a clip to move it. Drag its right edge to trim. M mutes; S solos.")}</p></section>`;
  }
  const instrumentName = (k) =>
    ({
      keys: tr("柔和键盘", "Velvet keys"),
      bass: tr("温暖贝斯", "Warm bass"),
      pad: tr("空气铺底", "Air pad"),
    })[k];
  function renderInstruments() {
    $("instrument-list").innerHTML = ["keys", "bass", "pad"]
      .map(
        (k) =>
          `<button class="instrument-card" data-add-instrument="${k}">${icon("keys")}<span><strong>${instrumentName(k)}</strong><small>BUILT-IN SYNTH · ${k.toUpperCase()}</small></span><span>＋</span></button>`,
      )
      .join("");
  }
  function view(name) {
    s.view = name;
    document
      .querySelectorAll("[data-view]")
      .forEach((b) => b.classList.toggle("active", b.dataset.view === name));
    for (const key of ["assets", "instruments", "models"])
      $(key + "-view").hidden = key !== name;
    $("browser-title").textContent = {
      assets: tr("声音素材", "Sound library"),
      instruments: tr("乐器与音色", "Instruments"),
      models: tr("本地 AI 模型", "Local AI models"),
    }[name];
    if (name === "models") loadModels();
  }
  function dock(name) {
    s.dock = name;
    for (const key of ["mixer", "piano", "tasks"]) {
      $(key).hidden = key !== name;
      $(key + "-tab").classList.toggle("active", key === name);
    }
    if (name === "piano") {
      renderPiano();
      $("piano").scrollTop = 100;
    }
    if (name === "tasks") pollTasks();
  }
  function newTrack(kind = "audio", instrument = "keys") {
    const t = {
      id: uid(),
      name:
        kind === "midi"
          ? instrumentName(instrument)
          : tr("音频轨道", "Audio track"),
      kind,
      color: colors[content().tracks.length % colors.length],
      gain_db: 0,
      pan: 0,
      mute: false,
      solo: false,
      instrument,
      clips: [],
    };
    if (kind === "midi")
      t.clips = [
        {
          id: uid(),
          name: t.name,
          asset: null,
          start: snap(s.position),
          offset: 0,
          duration: beatSeconds() * 16,
          gain_db: 0,
          fade_in: 0,
          fade_out: 0,
          notes: [],
        },
      ];
    return t;
  }
  function addTrack(kind = "audio", instrument = "keys") {
    if (content().tracks.length >= 32)
      throw Error(
        tr("当前最多支持 32 条轨道", "This preview supports 32 tracks"),
      );
    mutate(() => {
      const t = newTrack(kind, instrument);
      content().tracks.push(t);
      s.track = t.id;
      s.clip = t.clips[0]?.id;
    });
    if (kind === "midi") dock("piano");
  }
  function addAsset(id, trackId, at = 0) {
    const a = asset(id);
    if (!a) return;
    mutate(() => {
      let t = content().tracks.find(
        (x) => x.id === trackId && x.kind === "audio",
      );
      if (!t) {
        t = newTrack();
        content().tracks.push(t);
        t.name = a.name;
      }
      const c = {
        id: uid(),
        name: a.name,
        asset: id,
        start: Math.min(snap(at), 600 - a.duration),
        offset: 0,
        duration: a.duration,
        gain_db: 0,
        fade_in: 0,
        fade_out: 0,
        notes: [],
      };
      t.clips.push(c);
      s.track = t.id;
      s.clip = c.id;
    });
  }
  function duplicate() {
    const t = selectedTrack(),
      c = selectedClip();
    if (!c) return;
    const copy = structuredClone(c);
    copy.id = uid();
    copy.start = c.start + c.duration;
    if (copy.start + copy.duration > 600)
      throw Error(tr("超过 10 分钟工程限制", "Session limit is 10 minutes"));
    mutate(() => {
      t.clips.push(copy);
      s.clip = copy.id;
    });
  }
  function removeClip() {
    const t = selectedTrack();
    if (!t || !s.clip) return;
    mutate(() => {
      t.clips = t.clips.filter((c) => c.id !== s.clip);
      s.clip = null;
    });
  }
  function toggle(t, key) {
    mutate(() => (t[key] = !t[key]), { live: true });
  }
  async function importFiles(files) {
    pause();
    await flush();
    try {
      for (const file of files) {
        $("audio-status").textContent = tr("正在导入…", "Importing…");
        const form = new FormData();
        form.append("file", file);
        accept(
          await request(
            base() + `/import?revision=${s.session.revision}`,
            form,
          ),
          { selectLast: true },
        );
      }
    } finally {
      $("audio-status").textContent = tr("准备就绪", "Ready");
    }
    toast(tr("音频已加入工程", "Audio added to the session"));
  }
  async function play() {
    if (engine.playing || starting) {
      pause();
      return;
    }
    if (!duration(content()))
      return toast(
        tr("先添加音频或 MIDI 片段", "Add an audio or MIDI clip first"),
      );
    starting = true;
    $("audio-status").textContent = tr("准备音频…", "Preparing audio…");
    try {
      if (s.position >= duration(content())) s.position = 0;
      const ok = await engine.play(
        content(),
        s.session.assets,
        s.session.id,
        s.position,
      );
      if (ok) {
        $("play").textContent = "Ⅱ";
        $("audio-status").textContent = tr("正在播放", "Playing");
      }
    } finally {
      starting = false;
      if (!engine.playing)
        $("audio-status").textContent = tr("准备就绪", "Ready");
    }
  }
  function seek(at) {
    const was = engine.playing;
    pause();
    s.position = Math.max(0, Math.min(at, duration(content()) || at));
    engine.position = s.position;
    if (was) guarded(play)();
  }
  function renderPiano() {
    const t = selectedTrack(),
      c = selectedClip();
    if (t?.kind !== "midi" || !c) {
      $("piano").innerHTML =
        `<div class="piano-message">${tr("选择一个乐器片段编辑音符，或在左侧添加乐器轨道。", "Select an instrument clip to edit notes, or add an instrument track.")}</div>`;
      return;
    }
    const beatWidth = Math.max(30, beatSeconds() * s.zoom),
      beats = Math.max(16, (c.offset + c.duration) / beatSeconds());
    const keys = Array.from({ length: 37 }, (_, i) => {
      const pitch = 84 - i,
        black = [1, 3, 6, 8, 10].includes(pitch % 12);
      return `<button class="piano-key ${black ? "black" : ""}" data-note-key="${pitch}" style="top:${i * 14}px">${pitch % 12 === 0 ? "C" + (Math.floor(pitch / 12) - 1) : ""}</button>`;
    }).join("");
    $("piano").innerHTML =
      `<div class="piano-grid" style="width:${beats * beatWidth}px;height:518px;--note-step:${beatWidth / 4}px" data-beat-width="${beatWidth}">${keys}${c.notes.map((n, i) => `<button class="piano-note" data-note="${i}" aria-label="MIDI ${n.pitch}, ${n.start.toFixed(2)} beats" title="${tr("双击删除", "Double-click to remove")}" style="left:${n.start * beatWidth}px;top:${(84 - n.pitch) * 14 + 1}px;width:${Math.max(4, n.length * beatWidth - 2)}px"></button>`).join("")}</div>`;
  }
  async function loadModels() {
    try {
      s.models = await request("/api/studio/models");
      renderModels();
    } catch (e) {
      toast(e.message, true);
    }
  }
  function renderModels() {
    $("model-list").innerHTML = s.models
      .map(
        (m) =>
          `<div class="model-card"><strong>${esc(m.title[s.lang === "zh" ? 0 : 1])}</strong><small>${esc(m.description[s.lang === "zh" ? 0 : 1])}</small><div class="model-actions"><span>${esc(m.health.state)} · ${m.health.weights ? tr("权重已缓存", "weights cached") : tr("权重待检查", "check weights")}</span><button data-check-model="${m.id}">${tr("检查", "Check")}</button><button data-run-model="${m.id}" ${m.runnable ? "" : "disabled"}>${tr("运行", "Run")}</button></div></div>`,
      )
      .join("");
  }
  async function pollTasks() {
    if (!s.session || polling) return;
    polling = true;
    const key = s.session.id;
    try {
      const projects = [
        ...new Set(s.session.assets.map((a) => a.source_project)),
      ];
      const rows = await Promise.all(
        projects.map(async (p) =>
          (await request(`/api/projects/${p}/studio/tasks`)).map((t) => ({
            ...t,
            source_project: p,
          })),
        ),
      );
      if (s.session.id !== key) return;
      s.tasks = rows.flat().sort((a, b) => b.created_at - a.created_at);
      renderTasks();
    } catch (e) {
      console.warn(e.message);
    } finally {
      polling = false;
    }
  }
  function renderTasks() {
    $("task-count").textContent = s.tasks.filter((t) =>
      ["queued", "checking", "running", "cancelling"].includes(t.status),
    ).length;
    $("tasks").innerHTML =
      s.tasks
        .map(
          (t) =>
            `<div class="task-row"><span><strong>${esc(t.model)}</strong><small>${esc(t.error || t.status)}</small></span>${
              t.artifacts
                .map((a) =>
                  a.kind === "audio"
                    ? `<button data-attach-task="${a.id}" data-project="${t.source_project}">${esc(a.role)} · ${tr("加入工程", "Add track")}</button>`
                    : `<a class="task-artifact" href="/api/projects/${t.source_project}/studio/artifacts/${a.id}?download=true" download>${esc(a.role)} ↧</a>`,
                )
                .join("") || `<span class="task-state">${esc(t.status)}</span>`
            }${["queued", "checking", "running", "cancelling"].includes(t.status) ? `<button data-cancel-task="${t.id}" data-project="${t.source_project}">${tr("取消", "Cancel")}</button>` : `<a class="task-artifact" href="/next.html?project=${t.source_project}" target="_blank" rel="noopener">${tr("详细结果与编辑 ↗", "Details and editing ↗")}</a>`}</div>`,
        )
        .join("") ||
      `<p class="panel-copy">${tr("暂无任务。选择音频片段，在左侧 AI 模型中检查并运行能力。", "No tasks yet. Select audio, then check and run a model from the left panel.")}</p>`;
  }
  async function projectDialog() {
    await flush();
    const [active, deleted] = await Promise.all([
      request("/api/workstation/projects"),
      request("/api/workstation/projects?deleted=true"),
    ]);
    $("project-list").innerHTML =
      active
        .map(
          (p) =>
            `<div class="project-row"><button data-open-session="${p.id}">${esc(p.content.title)}<small>${p.content.tracks.length} ${tr("轨道", "tracks")} · ${new Date(p.updated * 1000).toLocaleString()}</small></button><button data-trash-session="${p.id}" data-revision="${p.revision}">${tr("移入回收站", "Trash")}</button></div>`,
        )
        .join("") +
      (deleted.length
        ? `<p class="section-caption" style="margin-top:25px">${tr("回收站 · 可恢复", "TRASH · RECOVERABLE")}</p>` +
          deleted
            .map(
              (p) =>
                `<div class="project-row"><span>${esc(p.content.title)}</span><button data-restore-session="${p.id}" data-revision="${p.revision}">${tr("恢复", "Restore")}</button></div>`,
            )
            .join("")
        : "");
    if (!$("project-dialog").open) $("project-dialog").showModal();
  }
  async function exportFile(kind) {
    await flush();
    const button = $("export-" + (kind === "mid" ? "midi" : "wav"));
    button.disabled = true;
    try {
      toast(tr("正在导出…", "Rendering export…"));
      const result = await request(base() + "/export/" + kind, {
        revision: s.session.revision,
      });
      const link = document.createElement("a");
      link.href = result.url;
      link.download = "";
      link.click();
      $("export-dialog").close();
      toast(tr("导出完成", "Export ready"));
    } finally {
      button.disabled = false;
    }
  }
  document
    .querySelectorAll("[data-view]")
    .forEach((b) => (b.onclick = () => view(b.dataset.view)));
  $("language").onclick = () => {
    s.lang = s.lang === "zh" ? "en" : "zh";
    localStorage.setItem("station-language", s.lang);
    renderAll();
    view(s.view);
    renderModels();
    renderTasks();
  };
  $("new-project").onclick = guarded(() => create());
  $("demo").onclick = $("empty-demo").onclick = guarded(() => create(true));
  $("open-projects").onclick = guarded(projectDialog);
  $("project-title").onchange = () => {
    const name = $("project-title").value.trim();
    if (name)
      mutate(() => (content().title = name), { live: true, render: false });
    else $("project-title").value = content().title;
  };
  $("project-title").oninput = () => {
    const title = $("project-title").value.trim();
    if (s.session && title && title !== content().title) {
      content().title = title;
      dirty();
    }
  };
  $("bpm").onchange = () => {
    const bpm = Number($("bpm").value);
    if (bpm < 30 || bpm > 300 || !Number.isFinite(bpm))
      return ($("bpm").value = content().bpm);
    const ratio = content().bpm / bpm;
    mutate(() => {
      for (const t of content().tracks)
        if (t.kind === "midi")
          for (const c of t.clips) {
            c.duration *= ratio;
            c.offset *= ratio;
            c.start *= ratio;
          }
      content().bpm = bpm;
    });
  };
  $("import").onclick = $("empty-import").onclick = () =>
    $("audio-files").click();
  $("audio-files").onchange = guarded(async () => {
    try {
      await importFiles($("audio-files").files);
    } finally {
      $("audio-files").value = "";
    }
  });
  $("asset-search").oninput = renderAssets;
  $("asset-list").onclick = guarded((e) => {
    const el = e.target.closest("[data-asset]");
    if (el) addAsset(el.dataset.asset, null, s.position);
  });
  $("asset-list").ondragstart = (e) => {
    const el = e.target.closest("[data-asset]");
    if (el)
      e.dataTransfer.setData("application/x-studio-asset", el.dataset.asset);
  };
  $("add-audio").onclick = guarded(() => addTrack());
  $("add-midi").onclick = guarded(() => addTrack("midi"));
  $("instrument-list").onclick = guarded((e) => {
    const el = e.target.closest("[data-add-instrument]");
    if (el) addTrack("midi", el.dataset.addInstrument);
  });
  $("play").onclick = guarded(play);
  $("stop").onclick = () => {
    pause();
    s.position = engine.position = 0;
  };
  $("rewind").onclick = () => seek(0);
  $("loop").onclick = () => {
    s.loop = !s.loop;
    $("loop").classList.toggle("active", s.loop);
    $("loop").setAttribute("aria-pressed", s.loop);
  };
  $("split").onclick = guarded(() => {
    const c = selectedClip();
    if (!c) return;
    const parts = splitClip(c, snap(s.position));
    if (!parts)
      return toast(
        tr(
          "把播放头放在片段内部再切分",
          "Place the playhead inside the clip to split",
        ),
      );
    mutate(() => {
      const t = selectedTrack();
      t.clips.splice(t.clips.indexOf(c), 1, ...parts);
      s.clip = parts[1].id;
    });
  });
  $("duplicate").onclick = guarded(duplicate);
  $("delete-clip").onclick = removeClip;
  for (const direction of ["undo", "redo"])
    $(direction).onclick = guarded(async () => {
      pause();
      await flush();
      accept(
        await request(base() + "/history/" + direction, {
          revision: s.session.revision,
        }),
      );
    });
  $("zoom-in").onclick = () => {
    s.zoom = Math.min(140, s.zoom * 1.3);
    renderTracks();
    if (s.dock === "piano") renderPiano();
  };
  $("zoom-out").onclick = () => {
    s.zoom = Math.max(12, s.zoom / 1.3);
    renderTracks();
    if (s.dock === "piano") renderPiano();
  };
  $("ruler-ticks").onclick = (e) =>
    seek(
      Math.max(
        0,
        (e.clientX - $("ruler-ticks").getBoundingClientRect().left) / s.zoom,
      ),
    );
  $("track-list").onclick = guarded((e) => {
    const row = e.target.closest("[data-track]");
    if (!row) return;
    const t = content().tracks.find((t) => t.id === row.dataset.track);
    if (e.target.closest("[data-toggle]"))
      return toggle(t, e.target.closest("[data-toggle]").dataset.toggle);
    if (e.target.closest("[data-remove-track]"))
      return mutate(() => {
        content().tracks = content().tracks.filter((x) => x.id !== t.id);
        s.track = content().tracks[0]?.id;
        s.clip = null;
      });
    if (e.target.matches("input")) return;
    s.track = t.id;
    s.clip = e.target.closest("[data-clip]")?.dataset.clip || null;
    document
      .querySelectorAll("[data-track]")
      .forEach((el) =>
        el.classList.toggle("selected", el.dataset.track === s.track),
      );
    document
      .querySelectorAll("[data-clip]")
      .forEach((el) =>
        el.classList.toggle("selected", el.dataset.clip === s.clip),
      );
    $("split").disabled = !selectedClip();
    $("duplicate").disabled = !selectedClip();
    $("delete-clip").disabled = !selectedClip();
    renderMixer();
    renderInspector();
    if (s.dock === "piano") renderPiano();
  });
  $("track-list").ondblclick = (e) => {
    const el = e.target.closest("[data-clip]");
    if (el && selectedTrack()?.kind === "midi") dock("piano");
  };
  $("track-list").onpointerdown = (e) => {
    if (e.button !== 0) return;
    const el = e.target.closest("[data-clip]");
    if (!el) return;
    const t = content().tracks.find(
        (t) => t.id === el.closest("[data-track]").dataset.track,
      ),
      c = t.clips.find((c) => c.id === el.dataset.clip);
    const startX = e.clientX,
      oldStart = c.start,
      oldDuration = c.duration,
      resizing = e.target.classList.contains("clip-handle");
    let moved = false;
    const move = (event) => {
      const delta = (event.clientX - startX) / s.zoom;
      if (Math.abs(event.clientX - startX) < 3 && !moved) return;
      if (!moved) {
        pause();
        moved = true;
      }
      s.track = t.id;
      s.clip = c.id;
      if (resizing) {
        const max =
          t.kind === "audio"
            ? asset(c.asset).duration - c.offset
            : 600 - c.start;
        c.duration = Math.max(
          0.02,
          Math.min(max, snap(oldDuration + delta), 600 - c.start),
        );
        c.fade_in = Math.min(c.fade_in, c.duration);
        c.fade_out = Math.min(c.fade_out, c.duration - c.fade_in);
        el.style.width = `${Math.max(12, c.duration * s.zoom)}px`;
      } else {
        c.start = Math.max(
          0,
          Math.min(600 - c.duration, snap(oldStart + delta)),
        );
        el.style.left = `${c.start * s.zoom}px`;
      }
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      if (moved) {
        dirty();
        renderAll();
      }
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up, { once: true });
  };
  $("arranger").ondragover = (e) => {
    e.preventDefault();
    $("arranger").classList.add("drag-over");
  };
  $("arranger").ondragleave = (e) => {
    if (!$("arranger").contains(e.relatedTarget))
      $("arranger").classList.remove("drag-over");
  };
  $("arranger").ondrop = guarded(async (e) => {
    e.preventDefault();
    $("arranger").classList.remove("drag-over");
    if (e.dataTransfer.files.length) return importFiles(e.dataTransfer.files);
    const id = e.dataTransfer.getData("application/x-studio-asset"),
      lane = e.target.closest("[data-lane]");
    if (id)
      addAsset(
        id,
        lane?.dataset.lane,
        lane
          ? Math.max(
              0,
              (e.clientX - lane.getBoundingClientRect().left) / s.zoom,
            )
          : s.position,
      );
  });
  document.addEventListener("input", (e) => {
    const el = e.target;
    if (!s.session) return;
    if (el.dataset.level) {
      const t = content().tracks.find((t) => t.id === el.dataset.level);
      t.gain_db = Number(el.value);
      document
        .querySelectorAll(`[data-level="${t.id}"]`)
        .forEach((input) => (input.value = el.value));
      document.querySelector(`[data-db="${t.id}"]`).textContent =
        t.gain_db.toFixed(1) + " dB";
      engine.update(content());
      dirty();
    } else if (el.dataset.pan) {
      content().tracks.find((t) => t.id === el.dataset.pan).pan = Number(
        el.value,
      );
      engine.update(content());
      dirty();
    } else if (el.hasAttribute("data-master")) {
      content().master_db = Number(el.value);
      $("master-db").textContent = content().master_db.toFixed(1) + " dB";
      engine.update(content());
      dirty();
    }
  });
  $("mixer").onclick = (e) => {
    const toggleButton = e.target.closest("[data-mixer-toggle]");
    if (toggleButton)
      return toggle(
        content().tracks.find((t) => t.id === toggleButton.dataset.id),
        toggleButton.dataset.mixerToggle,
      );
    const channel = e.target.closest("[data-channel]");
    if (channel && !e.target.matches("input")) {
      s.track = channel.dataset.channel;
      s.clip = selectedTrack().clips[0]?.id;
      renderTracks();
      renderMixer();
      renderInspector();
    }
  };
  $("inspector-content").onchange = guarded((e) => {
    const el = e.target,
      t = selectedTrack(),
      c = selectedClip();
    function edit(fn, live = false) {
      mutate(fn, { live, render: e.type !== "input" });
      if (e.type === "input") {
        renderTracks();
        renderMixer();
      }
    }
    if (el.hasAttribute("data-track-name")) {
      if (el.value.trim() && t.name !== el.value.trim())
        edit(() => (t.name = el.value.trim()), true);
      return;
    }
    if (el.hasAttribute("data-instrument"))
      return t.instrument === el.value
        ? undefined
        : edit(() => (t.instrument = el.value));
    if (!el.dataset.field) return;
    const [kind, key] = el.dataset.field.split("."),
      obj = kind === "track" ? t : c,
      value = Number(el.value);
    if (!Number.isFinite(value) || !el.checkValidity()) {
      if (e.type !== "input") renderInspector();
      return;
    }
    if (obj[key] === value) return;
    const candidate = { ...obj, [key]: value };
    if (
      kind === "clip" &&
      (candidate.start + candidate.duration > 600 ||
        candidate.fade_in + candidate.fade_out > candidate.duration ||
        (t.kind === "audio" &&
          candidate.offset + candidate.duration >
            asset(c.asset).duration + 1 / 44100))
    ) {
      if (e.type === "input") return;
      renderInspector();
      throw Error(
        tr(
          "片段范围超出素材或淡化长度不正确",
          "Clip bounds or fade length are invalid",
        ),
      );
    }
    edit(() => (obj[key] = value), kind === "track");
  });
  $("inspector-content").oninput = $("inspector-content").onchange;
  $("inspector-content").onclick = guarded((e) => {
    if (e.target.closest("[data-inspect-duplicate]")) duplicate();
    if (e.target.closest("[data-inspect-remove]")) removeClip();
  });
  for (const name of ["mixer", "piano", "tasks"])
    $(name + "-tab").onclick = () => dock(name);
  $("piano").onclick = guarded((e) => {
    const key = e.target.closest("[data-note-key]");
    if (key)
      engine.note(Number(key.dataset.noteKey), selectedTrack()?.instrument);
    const note = e.target.closest("[data-note]");
    if (note)
      engine.note(
        selectedClip().notes[Number(note.dataset.note)].pitch,
        selectedTrack().instrument,
      );
  });
  $("piano").ondblclick = guarded((e) => {
    const c = selectedClip(),
      t = selectedTrack(),
      grid = e.target.closest(".piano-grid");
    if (!c || t.kind !== "midi" || !grid || e.target.closest("[data-note-key]"))
      return;
    const n = e.target.closest("[data-note]");
    if (n) return mutate(() => c.notes.splice(Number(n.dataset.note), 1));
    const rect = grid.getBoundingClientRect(),
      start = Math.max(
        0,
        Math.round(
          ((e.clientX - rect.left) / Number(grid.dataset.beatWidth)) * 4,
        ) / 4,
      ),
      pitch = 84 - Math.floor((e.clientY - rect.top) / 14);
    if (
      pitch < 48 ||
      pitch > 84 ||
      start * beatSeconds() >= c.offset + c.duration ||
      c.notes.length >= 512
    )
      return;
    mutate(() => c.notes.push({ pitch, start, length: 0.5, velocity: 90 }));
    engine.note(pitch, t.instrument);
  });
  $("model-list").onclick = guarded(async (e) => {
    const check = e.target.closest("[data-check-model]"),
      run = e.target.closest("[data-run-model]");
    if (check) {
      check.disabled = true;
      check.textContent = "…";
      try {
        const model = await request(
          `/api/studio/models/${check.dataset.checkModel}/check`,
          {},
        );
        s.models = s.models.map((m) => (m.id === model.id ? model : m));
        renderModels();
      } finally {
        check.disabled = false;
      }
      return;
    }
    if (!run) return;
    const c = selectedClip(),
      a = c && asset(c.asset);
    if (!a)
      throw Error(tr("请先选择一段音频素材", "Select an audio clip first"));
    await flush();
    const session = await request(`/api/projects/${a.source_project}/studio`);
    await request(`/api/projects/${a.source_project}/studio/tasks`, {
      revision: session.revision,
      model: run.dataset.runModel,
      asset: a.source_asset,
      device: "auto",
    });
    dock("tasks");
    await pollTasks();
    toast(tr("任务已加入本地队列", "Task queued locally"));
  });
  $("tasks").onclick = guarded(async (e) => {
    const cancel = e.target.closest("[data-cancel-task]");
    if (cancel) {
      await request(
        `/api/projects/${cancel.dataset.project}/studio/tasks/${cancel.dataset.cancelTask}/cancel`,
        {},
      );
      await pollTasks();
      return;
    }
    const el = e.target.closest("[data-attach-task]");
    if (!el) return;
    await flush();
    accept(
      await request(base() + "/attach", {
        revision: s.session.revision,
        source_project: el.dataset.project,
        asset: "asset:" + el.dataset.attachTask,
        at: 0,
      }),
      { selectLast: true },
    );
    toast(tr("处理结果已加入新轨道", "Result added as a new track"));
  });
  $("project-list").onclick = guarded(async (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    if (btn.dataset.openSession) {
      await open(btn.dataset.openSession);
      $("project-dialog").close();
      return;
    }
    const key = btn.dataset.trashSession || btn.dataset.restoreSession,
      restore = !!btn.dataset.restoreSession;
    if (!key) return;
    await request(
      `/api/workstation/projects/${key}/${restore ? "restore" : "trash"}`,
      { revision: Number(btn.dataset.revision) },
    );
    if (!restore && key === s.session.id) {
      s.dirty = false;
      const list = await request("/api/workstation/projects");
      if (list.length) await open(list[0].id);
      else await create();
    }
    await projectDialog();
  });
  $("export").onclick = () => $("export-dialog").showModal();
  $("export-wav").onclick = guarded(() => exportFile("wav"));
  $("export-midi").onclick = guarded(() => exportFile("mid"));
  $("export-project").onclick = guarded(async () => {
    await flush();
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(s.session, null, 2)], {
        type: "application/json",
      }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = "music-studio-session.json";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    $("export-dialog").close();
  });
  document
    .querySelectorAll(".close-dialog")
    .forEach((b) => (b.onclick = () => b.closest("dialog").close()));
  document.querySelectorAll("dialog").forEach(
    (d) =>
      (d.onclick = (e) => {
        if (
          e.target === d &&
          e.offsetX >= 0 &&
          e.offsetX <= d.clientWidth &&
          e.offsetY >= 0 &&
          e.offsetY <= d.clientHeight
        )
          return;
        if (e.target === d) d.close();
      }),
  );
  document.addEventListener("keydown", (e) => {
    if (
      e.target.matches("input,textarea,select") ||
      document.querySelector("dialog[open]")
    )
      return;
    if (e.code === "Space") {
      e.preventDefault();
      guarded(play)();
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
      e.preventDefault();
      $(e.shiftKey ? "redo" : "undo").click();
    }
    if (e.key === "Delete" || e.key === "Backspace") {
      e.preventDefault();
      removeClip();
    }
  });
  window.addEventListener("beforeunload", (e) => {
    if (s.dirty || s.saving) {
      e.preventDefault();
      e.returnValue = "";
    }
  });
  function animate() {
    if (s.session) {
      if (engine.playing) {
        s.position = Math.max(0, engine.current());
        if (s.position >= duration(content())) {
          pause();
          s.position = engine.position = 0;
          if (s.loop) guarded(play)();
        }
      }
      $("time-display").textContent = seconds(s.position);
      const beat = s.position / beatSeconds();
      $("beat-display").textContent =
        `${Math.floor(beat / 4) + 1} . ${Math.floor(beat % 4) + 1} . ${Math.floor((beat % 1) * 4) + 1}`;
      $("playhead").style.left = `${headWidth() + s.position * s.zoom}px`;
      for (const t of content().tracks) {
        const level = engine.meter(t.id),
          el = document.querySelector(`[data-vu="${t.id}"]`);
        if (el)
          el.style.height = `${Math.min(100, Math.max(0, ((20 * Math.log10(level || 1e-6) + 60) / 60) * 100))}%`;
      }
      if ($("master-vu"))
        $("master-vu").style.height =
          `${Math.min(100, Math.max(0, ((20 * Math.log10(engine.masterMeter() || 1e-6) + 60) / 60) * 100))}%`;
    }
    requestAnimationFrame(animate);
  }
  guarded(async () => {
    localize();
    const sessions = await request("/api/workstation/projects"),
      key =
        new URLSearchParams(location.search).get("session") ||
        localStorage.getItem("station-session");
    const exists = sessions.find((p) => p.id === key) || sessions[0];
    if (exists) accept(exists);
    else await create();
    animate();
    setInterval(() => {
      if (
        s.dock === "tasks" ||
        s.view === "models" ||
        s.tasks.some((t) =>
          ["queued", "checking", "running"].includes(t.status),
        )
      )
        pollTasks();
    }, 4000);
  })();
})();
