"use strict";

const t = (key, values) => MusicI18n.t(key, values);
const $ = (selector) => document.querySelector(selector);
const state = {
  legacy: false,
  switchingVersion: false,
  defaultQuality: "text",
  defaultAlignment: "native",
  defaultInput: "vocals",
  jobs: [],
  job: null,
  project: null,
  peaks: {},
  pitch: null,
  mode: "source",
  selectedLine: 0,
  loop: false,
  loopPadding: 0,
  candidate: null,
  singalongLine: -2,
  viewStart: 0,
  importing: false,
  generation: 0,
  activeLine: -2,
  activeWords: "",
  checking: false,
  selecting: false,
  loadedResultKey: null,
  loadingResult: null,
  trackRequest: 0,
  edits: {
    revision: 0,
    changes: {},
    original: {}
  },
  editingLine: null,
  lastDeleted: null
};
state.version = "original";
state.versions = [];
const versionQuery = () => `?version=${encodeURIComponent(state.version)}`;
const statuses = {
  ready: "待分析",
  running: "正在分析",
  cancelling: "正在停止",
  complete: "分析完成",
  cancelled: "已停止",
  interrupted: "已中断",
  failed: "分析失败"
};
const stageNames = ["准备音频", "分离音轨", "识别歌词", "提取旋律", "检测节拍", "分析和弦"];
const trackNames = {
  source: "原曲",
  vocals: "人声",
  instrumental: "伴奏",
  melody: "旋律 MIDI"
};
const escape = (value) => String(value).replace(/[&<>"']/g, (c) => ({
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;"
} [c]));
const fmt = (time, precise = false) => {
  time = Math.max(0, Number(time) || 0);
  const whole = Math.floor(time),
    minutes = Math.floor(whole / 60);
  return `${minutes}:${String(whole % 60).padStart(2, "0")}${precise ? `.${String(Math.floor((time % 1) * 100 + 1e-6)).padStart(2, "0")}` : ""}`;
};

async function api(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let message = t("请求失败（{status}）", {status: response.status});
    try {
      const data = await response.json();
      message = typeof data.detail === "string" ? t(data.detail) : message;
    } catch (_) {}
    throw new Error(message);
  }
  return response.json();
}
const post = (url, data = {}) => api(url, {
  method: "POST",
  headers: {
    "Content-Type": "application/json"
  },
  body: JSON.stringify(data)
});
const patch = (url, data) => api(url, {
  method: "PATCH",
  headers: {
    "Content-Type": "application/json"
  },
  body: JSON.stringify(data)
});

function toast(message, deleted = null) {
  state.lastDeleted = deleted;
  $("#toast-text").textContent = message;
  $("#toast-undo").hidden = !deleted;
  $("#toast").hidden = false;
}

function notice(text, error = false) {
  $("#notice").hidden = !text;
  $("#notice").classList.toggle("error", error);
  $("#notice").textContent = text || "";
}

const player = new MusicPlayback.Player({
  onUpdate: updateControls,
  getGeneration: () => state.generation,
  getMode: () => state.mode,
  getVolume: () => Number($("#volume").value),
  getGuideVolume: () => Number($("#guide-volume").value),
  getNotes: () => state.project?.melody.notes || [],
  onSeek: refreshPlayback
});

function updateControls() {
  const busy = state.switchingVersion || state.jobs.some((j) => ["running", "cancelling"].includes(j.status));
  const currentRunning = state.job && ["running", "cancelling"].includes(state.job.status);
  $("#analyze-button").disabled = !state.job || busy || state.importing || state.legacy;
  $("#analyze-button").textContent = currentRunning ? t("分析中…") : state.job?.has_result ? ($("#analysis-scope").value === "full" ? t("✦ 重新分析") : $("#analysis-scope").value === "align" ? t("✦ 重新对齐") : t("✦ 更新歌词")) : state.job && ["failed", "cancelled", "interrupted"].includes(state.job.status) ? t("✦ 继续分析") : t("✦ 开始分析");
  $("#cancel-button").hidden = !currentRunning;
  $("#cancel-button").disabled = state.job?.status === "cancelling";
  for (const id of ["#play-button", "#rewind", "#seek", "#loop-button"]) $(id).disabled = !player.ready;
  $("#export").disabled = !state.project || state.switchingVersion;
  $("#project-actions").hidden = !state.job;
  $("#delete-button").disabled = !!currentRunning;
  for (const id of ["#previous-line", "#next-line"]) $(id).disabled = !player.ready || !state.project?.lyrics.segments.length;
  $("#play-button").textContent = player.playing ? "Ⅱ" : "▶";
  $("#play-button").setAttribute("aria-label", player.playing ? t("暂停") : t("播放"));
  document.querySelectorAll("[data-track]").forEach((button) => {
    button.disabled = !player.ready;
    const loading = player.isLoading(button.dataset.track);
    button.classList.toggle("loading", loading);
    button.setAttribute("aria-busy", String(loading));
    button.classList.toggle("active", button.dataset.track === state.mode);
    button.setAttribute("aria-pressed", String(button.dataset.track === state.mode));
  });
  $("#guide-volume").disabled = !player.ready || state.mode !== "instrumental";
  for (const id of ["#demo-button", "#new-project", "#choose-file"]) $(id).disabled = state.importing;
  for (const id of ["#language", "#device", "#offline", "#quality", "#alignment", "#lyrics-source", "#analysis-scope"]) $(id).disabled = !!currentRunning;
  for (const option of $("#analysis-scope").options) option.disabled = option.value !== "full" && !state.job?.has_result;
  $("#reference-button").disabled = !state.project || busy || state.legacy;
  $("#retry-line-button").disabled = busy || state.legacy;
  $("#mark-reviewed").disabled = busy || state.legacy;
  $("#next-review").disabled = !player.ready || !(state.edits.review?.counts.pending > 0);
  $("#singalong-button").disabled = !player.ready || !state.project?.lyrics.segments.length;
  $("#singalong-play").textContent = player.playing ? "Ⅱ" : "▶";
  $("#singalong-play").setAttribute("aria-label", player.playing ? t("跟唱暂停") : t("跟唱播放"));
  $("#version-picker").disabled = !!currentRunning || state.legacy;
  $("#compare-button").disabled = state.versions.filter(v => v.status === "complete").length < 2;
  $("#candidate-button").hidden = !state.job?.candidate_version || state.legacy;
  $("#candidate-button").disabled = !!currentRunning || !state.project;
}

function renderProjects() {
  $("#project-count").textContent = state.jobs.length;
  const query = $("#project-search").value.trim().toLocaleLowerCase();
  const filtered = state.jobs.filter((j) => `${j.title} ${j.filename}`.toLocaleLowerCase().includes(query));
  $("#project-list").innerHTML = filtered.length ? filtered.map((job) => `<div class="project-row">
    <button class="project-item ${state.job?.id === job.id ? "selected" : ""}" data-project="${job.id}" ${state.job?.id === job.id ? 'aria-current="page"' : ""}>
    <span class="project-glyph">♫</span><span class="project-name"><strong>${escape(job.title)}</strong>
    <small><i class="project-dot ${job.status}"></i>${escape(t(statuses[job.status] || job.status))}${job.duration ? ` · ${fmt(job.duration)}` : ""}</small></span></button><button class="row-delete" data-delete="${job.id}" aria-label="${escape(t("删除歌曲 {title}", {title: job.title}))}" title="${t("移入回收站")}" ${["running", "cancelling"].includes(job.status) ? "disabled" : ""}>×</button></div>`).join("") : `<p class="history-empty">${query ? t("没有匹配的歌曲") : t("导入的歌曲会保存在这里，<br>随时回来继续探索。")}</p>`;
  $("#project-picker").innerHTML = `<option value="">${t("我的项目")}</option>` + state.jobs.map((job) => `<option value="${job.id}">${escape(job.title)} · ${escape(t(statuses[job.status] || job.status))}</option>`).join("");
  $("#project-picker").value = state.job?.id || "";
  updateControls();
}

function renderStatus() {
  const job = state.job;
  $("#song-title").textContent = job?.title || t("把歌曲，展开来看");
  $("#breadcrumb-title").textContent = job?.title || t("歌曲分析");
  $("#song-subtitle").textContent = job ? (job.attribution ? `${job.attribution.artist} · ${job.attribution.license} · ${t("公开授权示例")}` : job.filename) : t("导入音频，在同一条时间轴上探索歌词、旋律与伴奏。");
  $("#status-badge").textContent = job ? t(statuses[job.status] || job.status) : t("等待导入");
  $("#status-badge").className = `status-badge ${job?.status || ""}`;
  const running = job && ["running", "cancelling"].includes(job.status);
  $("#progress-panel").hidden = !running;
  if (running) {
    const done = job.completed_stages || 0, total = job.total_stages || 6;
    $("#progress-label").textContent = job.status === "cancelling" ? t("正在停止，已完成的阶段会保留…") : t(job.stage_label);
    $("#progress-count").textContent = `${done} / ${total}`;
    $("#analysis-progress").max = total;
    $("#analysis-progress").value = done;
    const detail = job.progress_detail;
    $("#progress-detail").textContent = `${detail ? `${t(detail.label)} · ${Math.round(detail.completed)} / ${Math.round(detail.total)} ${t(detail.unit || "段")} · ` : ''} ${t("已用时")} ${fmt(job.elapsed_seconds || 0)}`;
    $("#stage-list").innerHTML = (total === 1 ? [t("更新歌词与时间")] : stageNames).map((name, index) => `<span class="${index < done ? "done" : index === done ? "working" : ""}">${index < done ? "✓ " : ""}${t(name)}</span>`).join("");
  }
  $("#error-details").hidden = job?.status !== "failed";
  if (job?.status === "failed") {
    notice(job.has_result ? t("本次更新未完成，之前的结果仍可试听。可展开诊断信息，调整设置后重试。") : t("「{stage}」未完成。检查模型与设备后可继续分析。", {stage: t(job.stage_label || "分析")}), true);
    $("#error-log").textContent = t(job.error || "") || t("请重新导入有效音频。");
  }
  const credit = job?.attribution;
  $("#attribution").innerHTML = credit ? `${escape(credit.artist)} · <a href="https://creativecommons.org/licenses/by/3.0/" target="_blank" rel="noreferrer">${escape(credit.license)}</a> · ${t("自动估计")}` : t("自动分析结果可通过试听核对");
  updateControls();
}

function resetResult() {
  document.body.classList.remove("has-result");
  state.loadedResultKey = null;
  state.loadingResult = null;
  ++state.trackRequest;
  state.mode = "source";
  player.reset();
  state.project = null;
  state.pitch = null;
  state.peaks = {};
  state.loop = false;
  state.loopPadding = 0;
  state.singalongLine = -2;
  $("#singalong").close();
  $("#review-filter").value = "all";
  $("#review-summary").textContent = t("先听，再修正");
  state.selectedLine = 0;
  state.activeLine = -2;
  state.activeWords = "";
  state.viewStart = 0;
  state.edits = {
    revision: 0,
    changes: {},
    original: {}
  };
  state.versions = [];
  $("#version-bar").hidden = true;
  $("#edited-count").textContent = "";
  $("#line-position").textContent = "0 / 0";
  $("#playhead").hidden = true;
  $("#timeline-empty").hidden = false;
  $("#stat-duration").textContent = "—";
  $("#stat-bpm").innerHTML = "—<small>BPM</small>";
  $("#stat-lyrics").innerHTML = `—<small>${t("句")}</small>`;
  $("#stat-notes").innerHTML = `—<small>${t("个")}</small>`;
  $("#lyric-list").innerHTML = `<div class="empty-lyrics">♫<p>${t("歌词会出现在这里")}</p><small>${t("自动识别后可逐句试听核对")}</small></div>`;
  $("#seek").value = 0;
  $("#seek").max = 1;
  $("#current-time").textContent = "0:00.00";
  $("#total-time").textContent = "0:00";
  $("#audio-status").textContent = t("选择歌曲后开始分析");
  $("#loop-button").setAttribute("aria-pressed", "false");
  updateViewControls();
  drawTimeline();
}

async function selectProject(id) {
  const generation = ++state.generation;
  state.selecting = true;
  try {
    resetResult();
    notice("");
    const job = await api(`/api/projects/${id}`);
    if (generation !== state.generation) return;
    state.job = job;
    state.version = MusicPlayback.effectiveVersion(job, state.legacy);
    $("#analysis-scope").value = job.has_result ? "lyrics" : "full";
    $("#quality").value = state.defaultQuality;
    $("#alignment").value = state.defaultAlignment;
    $("#lyrics-source").value = state.defaultInput;
    $("#analysis-options").open = !job.has_result;
    $("#analysis-options-label").textContent = job.has_result ? t("更新分析与歌词") : t("分析设置");
    history.replaceState(null, "", `?project=${id}`);
    if (state.job.settings) {
      $("#language").value = state.job.settings.language || "";
      $("#device").value = job.precomputed_demo ? state.system.defaults.device : state.job.settings.device;
      $("#offline").checked = state.job.settings.offline;
      $("#quality").value = state.defaultQuality;
      $("#alignment").value = state.defaultAlignment;
      $("#lyrics-source").value = state.defaultInput;
    }
    renderProjects();
    renderStatus();
    if (state.job.has_result || state.job.status === "complete") await loadResult(id, generation);
    else $("#audio-status").textContent = t("设置语言与设备，然后开始分析");
  } finally {
    if (generation === state.generation) state.selecting = false;
  }
}

async function loadResult(id, generation) {
  const version = state.version;
  const key = MusicPlayback.resultKey(id, version);
  if (state.loadedResultKey === key || (state.loadingResult?.key === key && state.loadingResult.generation === generation)) return;
  const loading = {key, generation};
  state.loadingResult = loading;
  try {
    const query = `?version=${encodeURIComponent(version)}`;
    const [project, peaks, pitch, edits, versions] = await Promise.all([
      api(`/api/projects/${id}/result${query}`), api(`/api/projects/${id}/waveforms${query}`), api(`/api/projects/${id}/assets/pitch${query}`), api(`/api/projects/${id}/lyrics${query}`), api(`/api/projects/${id}/versions`).catch(() => ({versions: [{id: "original", status: "complete", scope: "full", created_at: state.job.created_at, settings: state.job.settings}]}))
    ]);
    if (generation !== state.generation || state.loadingResult !== loading) return;
    state.loadedResultKey = key;
    state.project = project;
    state.peaks = peaks;
    state.pitch = pitch;
    state.edits = edits;
    state.versions = versions.versions;
    renderVersions();
    document.body.classList.add("has-result");
    $("#timeline-empty").hidden = true;
    $("#stat-duration").textContent = fmt(project.audio.duration);
    $("#stat-bpm").innerHTML = `${project.rhythm.bpm ? Math.round(project.rhythm.bpm) : "—"}<small>BPM</small>`;
    $("#stat-lyrics").innerHTML = `${project.lyrics.segments.length}<small>${t("句")}</small>`;
    $("#stat-notes").innerHTML = `${project.melody.notes.length}<small>${t("个")}</small>`;
    $("#seek").max = project.audio.duration;
    $("#total-time").textContent = fmt(project.audio.duration);
    renderLyrics();
    updateViewControls();
    drawTimeline();
    updateControls();
    $("#audio-status").textContent = t("正在载入试听音轨…");
    await player.load(id, project.audio.duration, generation, version);
    if (generation !== state.generation) return;
    $("#audio-status").textContent = t("试听：原曲 · 空格播放 / 暂停");
    updateControls();
    refreshPlayback();
  } catch (error) {
    if (generation === state.generation) {
      notice(t(error.message), true);
      $("#audio-status").textContent = t("音轨载入失败，可重新选择项目");
    }
  } finally {
    if (state.loadingResult === loading) state.loadingResult = null;
  }
}

function lyricMarkup(line, index) {
  const sentence = (text) => `<button class="word untimed-word" data-seek="${line.start}" data-line-index="${index}" title="${t("尚无可靠词级时间，按句定位")}">${escape(text)}</button>`;
  if (!line.words.length) return sentence(line.text || t("（空白歌词）"));
  let cursor = 0, result = "";
  for (const word of line.words) {
    const text = word.text.trim(), at = line.text.indexOf(text, cursor);
    if (!text || at < 0) return sentence(line.text);
    const gap = line.text.slice(cursor, at);
    result += /[\p{L}\p{N}]/u.test(gap) ? sentence(gap) : escape(gap);
    result += `<button class="word" data-word="${escape(word.id)}" data-seek="${word.start}" data-line-index="${index}" title="${fmt(word.start, true)} – ${fmt(word.end, true)}">${escape(text)}</button>`;
    cursor = at + text.length;
  }
  const tail = line.text.slice(cursor);
  return result + (/[\p{L}\p{N}]/u.test(tail) ? sentence(tail) : escape(tail));
}

function renderLyrics() {
  const lines = state.project?.lyrics.segments || [];
  $("#edited-count").textContent = Object.keys(state.edits.changes).length ? t("{count} 句已修改", {count: Object.keys(state.edits.changes).length}) : "";
  const counts = state.edits.review?.counts;
  $("#review-summary").textContent = counts ? t("文字提示 {text} · 待定位 {timing} · 已核对 {reviewed}", counts) : t("提示用于安排试听");
  $("#review-summary").title = t("未标记的歌词也可能有误；时间缺失与文字错误分别处理。");
  const filter = $("#review-filter").value;
  let visible = 0;
  $("#lyric-list").innerHTML = lines.map((line, index) => {
    const review = state.edits.review?.lines[line.id] || {kinds: [], reviewed: false};
    const show = filter === "all" || (filter === "reviewed" ? review.reviewed : review.kinds.includes(filter) && !review.reviewed);
    visible += show ? 1 : 0;
    const badges = review.reviewed ? `<span class="checked-badge">${t("✓ 已核对")}</span>` : `${review.kinds.includes('text') ? `<span class="review-badge" title="${escape(review.text_reasons.map(reason => t(reason)).join("; "))}">${t("文字疑点")}</span>` : ''}${review.kinds.includes('timing') ? `<span class="timing-badge" title="${t("文字仍完整保留；部分词只有句级定位，不代表文字识别错误")}">${t("待定位")}</span>` : ''}`;
    return `<article class="lyric-line ${line.id in state.edits.changes ? 'edited' : ''}" data-line="${index}" role="listitem" ${show ? '' : 'hidden'}><div class="line-meta"><button class="line-time" data-seek="${line.start}" data-line-index="${index}" aria-label="${t("跳转到第 {line} 句歌词，{time}", {line: index + 1, time: fmt(line.start)})}">${fmt(line.start, true)}</button>${line.id in state.edits.changes ? `<span class="edited-badge">${t("已修改")}</span>` : ''}${badges}<button class="edit-lyric" data-edit="${index}" aria-label="${t("编辑第 {line} 句歌词", {line: index + 1})}" title="${t("修改歌词文字")}">✎</button></div><div class="lyric-words">${lyricMarkup(line, index)}</div></article>`;
  }).join('');
  if (!visible) $("#lyric-list").insertAdjacentHTML('beforeend', `<div class="empty-lyrics">✓<p>${lines.length ? t("当前筛选下没有待处理的歌词") : t("没有识别到可用歌词")}</p><small>${t("核对标记不代表模型正确率。")}</small></div>`);
  state.activeLine = -2;
  state.activeWords = "";
  state.singalongLine = -2;
  updateControls();
}

async function refreshProjects() {
  state.jobs = await api("/api/projects");
  renderProjects();
}
async function importFile(file) {
  if (!file || state.importing) return;
  state.importing = true;
  updateControls();
  notice(t("正在导入音频…"));
  try {
    const form = new FormData();
    form.append("file", file);
    const job = await api("/api/projects", {
      method: "POST",
      body: form
    });
    await refreshProjects();
    await selectProject(job.id);
    notice(t("音频已就绪，点击「开始分析」。"));
  } catch (error) {
    notice(t(error.message), true);
  } finally {
    state.importing = false;
    updateControls();
    $("#file-input").value = "";
  }
}

async function poll() {
  if (state.checking || state.selecting || state.switchingVersion) return;
  state.checking = true;
  const generation = state.generation, id = state.job?.id;
  try {
    await refreshProjects();
    if (generation !== state.generation || state.selecting || state.switchingVersion || id !== state.job?.id) return;
    if (id) {
      const job = state.jobs.find((j) => j.id === id);
      if (job) {
        const candidateReady = job.status === "complete" && job.candidate_version &&
          (state.job.status !== "complete" || state.job.candidate_version !== job.candidate_version);
        state.job = job;
        renderStatus();
        if (MusicPlayback.shouldLoadResult(job, state.legacy, state.loadedResultKey, state.loadingResult?.key)) {
          ++state.generation;
          state.version = MusicPlayback.effectiveVersion(job, state.legacy);
          notice("");
          await loadResult(job.id, state.generation);
        }
        if (candidateReady && state.job?.id === id && state.project) await showCandidate(job.candidate_version);
      }
    }
  } catch (_) {
    /* Keep the loaded song playable during a temporary network interruption. */
  } finally {
    state.checking = false;
  }
}

function viewDuration() {
  const total = state.project?.audio.duration || 30,
    zoom = Number($("#zoom").value);
  return Math.min(total, zoom || total);
}

function updateViewControls() {
  const total = state.project?.audio.duration || 30,
    window = viewDuration();
  state.viewStart = Math.max(0, Math.min(state.viewStart, total - window));
  $("#view-range").max = Math.max(0, total - window);
  $("#view-range").value = state.viewStart;
  $("#view-range").disabled = !state.project || total <= window;
  $("#view-start").textContent = fmt(state.viewStart);
  $("#view-end").textContent = fmt(state.viewStart + window);
}

function drawTimeline() {
  const canvas = $("#timeline"),
    bounds = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1,
    width = bounds.width,
    height = bounds.height;
  if (canvas.width !== Math.round(width * ratio) || canvas.height !== Math.round(height * ratio)) {
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, width, height);
  const left = 57,
    plotWidth = width - left - 12;
  ctx.font = '9px "Segoe UI", sans-serif';
  const duration = viewDuration(),
    start = state.viewStart,
    end = start + duration;
  const x = (time) => left + (time - start) / duration * plotWidth;
  const scale = Math.min(1, height / 315), sy = value => value * scale;
  const waveTop = height - sy(139),
    noteTop = sy(100),
    noteBottom = waveTop - sy(10);
  $("#playhead").style.top = `${sy(26)}px`;
  ctx.strokeStyle = "#283036";
  ctx.lineWidth = 1;
  for (const y of [sy(26), sy(62), sy(94), waveTop - 1, waveTop + sy(44), waveTop + sy(88)]) {
    ctx.beginPath();
    ctx.moveTo(0, y + 0.5);
    ctx.lineTo(width, y + 0.5);
    ctx.stroke();
  }
  const step = duration > 60 ? 20 : duration > 20 ? 5 : 2;
  for (let t = Math.ceil(start / step) * step; t <= end; t += step) {
    ctx.strokeStyle = "#252e34";
    ctx.beginPath();
    ctx.moveTo(x(t), sy(26));
    ctx.lineTo(x(t), height);
    ctx.stroke();
    ctx.fillStyle = "#84949f";
    ctx.fillText(fmt(t), x(t) + 3, sy(17));
  }
  ctx.fillStyle = "#92a4af";
  for (const [label, y] of [
      [t("和弦"), sy(48)],
      [t("歌词"), sy(82)],
      [t("旋律"), sy(116)],
      [t("原曲"), waveTop + sy(25)],
      [t("人声"), waveTop + sy(69)],
      [t("伴奏"), waveTop + sy(113)]
    ]) ctx.fillText(label, 8, y, 45);
  if (!state.project) return;
  const project = state.project;
  ctx.save();
  ctx.beginPath();
  ctx.rect(left, sy(26), plotWidth, height - sy(26));
  ctx.clip();
  ctx.strokeStyle = "#7eaaa311";
  for (const time of project.rhythm.beats)
    if (time >= start && time <= end) {
      ctx.beginPath();
      ctx.moveTo(x(time), sy(27));
      ctx.lineTo(x(time), height);
      ctx.stroke();
    }
  for (const chord of project.harmony.chords) {
    if (chord.end <= start || chord.start >= end) continue;
    const begin = Math.max(left, x(chord.start)),
      stop = Math.min(width - 12, x(chord.end));
    ctx.fillStyle = chord.label === "N" ? "#343a3d" : "#6b4e32";
    ctx.fillRect(begin + 1, sy(33), Math.max(1, stop - begin - 2), sy(22));
    ctx.fillStyle = chord.label === "N" ? "#83929c" : "#f1c796";
    if (stop - begin > 15) ctx.fillText(chord.label, begin + 5, sy(48), Math.max(1, stop - begin - 8));
  }
  for (const line of project.lyrics.segments) {
    if (line.end <= start || line.start >= end) continue;
    const begin = Math.max(left, x(line.start)),
      stop = Math.min(width - 12, x(line.end));
    ctx.fillStyle = "#2b3a37";
    ctx.fillRect(begin + 1, sy(69), stop - begin - 2, sy(18));
    ctx.fillStyle = "#b0c7be";
    if (stop - begin > 20) {
      ctx.save();
      ctx.beginPath();
      ctx.rect(begin + 4, sy(69), stop - begin - 8, sy(18));
      ctx.clip();
      ctx.fillText(line.text, begin + 4, sy(81));
      ctx.restore();
    }
  }
  const pitches = project.melody.notes.map((n) => n.pitch);
  const low = pitches.length ? Math.floor(Math.min(...pitches) / 12) * 12 - 1 : 47;
  const high = pitches.length ? Math.max(low + 19, Math.ceil(Math.max(...pitches) / 12) * 12 + 1) : 73;
  const y = (pitch) => noteBottom - (pitch - low) / (high - low) * (noteBottom - noteTop);
  for (let pitch = low; pitch <= high; pitch++) {
    ctx.strokeStyle = pitch % 12 === 0 ? "#3a454b" : "#273035";
    ctx.beginPath();
    ctx.moveTo(left, y(pitch));
    ctx.lineTo(width, y(pitch));
    ctx.stroke();
  }
  for (const note of project.melody.notes) {
    if (note.end <= start || note.start >= end) continue;
    const begin = x(note.start),
      stop = x(note.end);
    ctx.fillStyle = note.score < 0.5 ? "#668f82" : "#75c6ad";
    ctx.fillRect(begin, y(note.pitch) - 2.5, Math.max(2, stop - begin - 1), 5);
  }
  if (state.pitch) {
    ctx.strokeStyle = "#d3e9df65";
    ctx.lineWidth = 0.7;
    ctx.beginPath();
    let connected = false;
    for (let i = 0; i < state.pitch.times.length; i += 2) {
      const time = state.pitch.times[i],
        hz = state.pitch.frequency_hz[i];
      if (time < start || time > end || !hz) {
        connected = false;
        continue;
      }
      const pitch = 69 + 12 * Math.log2(hz / 440);
      if (pitch < low || pitch > high) {
        connected = false;
        continue;
      }
      if (connected) ctx.lineTo(x(time), y(pitch));
      else ctx.moveTo(x(time), y(pitch));
      connected = true;
    }
    ctx.stroke();
  }
  ["source", "vocals", "instrumental"].forEach((kind, index) => {
    const data = state.peaks[kind];
    if (!data?.length) return;
    const center = waveTop + sy(index * 44 + 22),
      maximum = Math.max(0.02, ...data);
    ctx.strokeStyle = ["#758da1", "#8dccb6", "#b69ad0"][index];
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let i = 0; i < data.length; i++) {
      const time = i / data.length * project.audio.duration;
      if (time < start || time > end) continue;
      const amplitude = Math.min(1, data[i] / maximum) * sy(15);
      ctx.moveTo(x(time), center - amplitude);
      ctx.lineTo(x(time), center + amplitude);
    }
    ctx.stroke();
  });
  const playhead = player.time;
  ctx.restore();
  updatePlayhead(playhead);
}

function updatePlayhead(time = player.time) {
  const head = $("#playhead");
  head.hidden = !state.project || time < state.viewStart || time > state.viewStart + viewDuration();
  if (!head.hidden) head.style.transform = `translateX(${57 + (time - state.viewStart) / viewDuration() * ($("#timeline").clientWidth - 69)}px)`;
}

function refreshPlayback() {
  const time = player.time;
  $("#current-time").textContent = fmt(time, true);
  $("#seek").value = time;
  if (!state.project) return;
  const lines = state.project.lyrics.segments;
  const index = lines.findIndex((line) => time >= line.start && time < line.end);
  $("#line-position").textContent = `${Math.max(0, (index >= 0 ? index : state.selectedLine) + 1)} / ${lines.length}`;
  if (index !== state.activeLine) {
    state.activeLine = index;
    document.querySelectorAll(".lyric-line.current").forEach((element) => element.classList.remove("current"));
    const current = $(`[data-line="${index}"]`);
    if (current && !current.hidden) {
      current.classList.add("current");
      if (!state.loop) state.selectedLine = index;
      if ($("#follow").checked) {
        const list = $("#lyric-list"),
          row = current.getBoundingClientRect(),
          box = list.getBoundingClientRect();
        if (row.top < box.top) list.scrollTop += row.top - box.top - 8;
        else if (row.bottom > box.bottom) list.scrollTop += row.bottom - box.bottom + 8;
      }
    }
  }
  const words = index < 0 ? [] : lines[index].words.filter((word) => time >= word.start && time < word.end);
  const key = words.map((word) => word.id).join(",");
  if (key !== state.activeWords) {
    state.activeWords = key;
    document.querySelectorAll(".word.current").forEach((element) => element.classList.remove("current"));
    for (const word of words) document.querySelectorAll(`[data-word="${CSS.escape(word.id)}"]`).forEach(element => element.classList.add("current"));
  }
  if ($("#follow").checked && (time < state.viewStart || time >= state.viewStart + viewDuration())) {
    state.viewStart = Math.max(0, time - 2);
    updateViewControls();
    drawTimeline();
  }
  updatePlayhead();
  refreshSingalong(time, index);
}

let lastPaint = 0;

function animate(now) {
  if (player.playing) {
    const line = state.project?.lyrics.segments[state.selectedLine];
    if (state.loop && line && player.time >= Math.min(player.duration, line.end + state.loopPadding)) player.seek(Math.max(0, line.start - state.loopPadding)).catch((e) => notice(t(e.message), true));
    else if (player.time >= player.duration) {
      player.pause();
      player.offset = player.duration;
    }
    updatePlayhead();
    if (now - lastPaint > 40) {
      refreshPlayback();
      lastPaint = now;
    }
  }
  requestAnimationFrame(animate);
}

for (const id of ["#new-project", "#choose-file", "#mobile-import"]) $(id).onclick = () => $("#file-input").click();
$("#file-input").onchange = (event) => importFile(event.target.files[0]);
$("#import-panel").onclick = (event) => {
  if (!event.target.closest("button")) $("#file-input").click();
};
for (const type of ["dragenter", "dragover"]) $("#import-panel").addEventListener(type, (event) => {
  event.preventDefault();
  $("#import-panel").classList.add("dragging");
});
for (const type of ["dragleave", "drop"]) $("#import-panel").addEventListener(type, (event) => {
  event.preventDefault();
  $("#import-panel").classList.remove("dragging");
  if (type === "drop") importFile(event.dataTransfer.files[0]);
});
$("#demo-button").onclick = async () => {
  if (state.importing) return;
  state.importing = true;
  updateControls();
  notice(t("正在载入授权示例…"));
  try {
    const job = await post("/api/demo");
    await refreshProjects();
    await selectProject(job.id);
    notice(job.precomputed_demo ? t("示例已就绪，无需模型即可试听、纠词和导出。分析自己的歌曲需安装推理依赖与模型。") : t("示例音频已就绪，请开始分析。免模型示例需要重启更新后的服务。"));
  } catch (error) {
    notice(t(error.message), true);
  } finally {
    state.importing = false;
    updateControls();
  }
};
async function startAnalysis(extra = {}) {
  if (!state.job) return;
    const projectId = state.job.id;
    const job = await post(`/api/projects/${state.job.id}/analyze`, {
      language: $("#language").value || null,
      device: $("#device").value,
      offline: $("#offline").checked,
      quality: $("#quality").value,
      scope: $("#analysis-scope").value,
      alignment: $("#alignment").value,
      lyrics_input: $("#lyrics-source").value,
      base_version: state.version,
      edit_revision: state.edits.revision,
      ...extra
    });
    if (state.job?.id !== projectId) return;
    job.completed_stages = 0;
    job.total_stages = (extra.scope || $("#analysis-scope").value) === "full" ? 6 : 1;
    job.stage_label = t("准备分析");
    state.job = job;
    await refreshProjects();
    renderStatus();
    $("#analysis-options").open = false;
}
$("#analyze-button").onclick = async () => {
  try {
    notice("");
    await startAnalysis();
  } catch (error) {
    notice(t(error.message), true);
  }
};
$("#cancel-button").onclick = async () => {
  try {
    await post(`/api/projects/${state.job.id}/cancel`);
    await poll();
  } catch (error) {
    notice(t(error.message), true);
  }
};
$("#project-list").onclick = (event) => {
  const deletion = event.target.closest("[data-delete]");
  if (deletion) {
    deleteProject(deletion.dataset.delete).catch((e) => notice(t(e.message), true));
    return;
  }
  const button = event.target.closest("[data-project]");
  if (button && button.dataset.project !== state.job?.id) selectProject(button.dataset.project).catch((error) => notice(t(error.message), true));
};
$("#project-picker").onchange = (event) => {
  if (event.target.value) selectProject(event.target.value).catch((error) => notice(t(error.message), true));
};
$("#play-button").onclick = () => player.playing ? player.pause() : player.play().catch((error) => notice(t(error.message), true));
$("#rewind").onclick = () => {
  state.loop = false;
  $("#loop-button").setAttribute("aria-pressed", "false");
  player.seek(0);
};
$("#seek").oninput = (event) => player.seek(Number(event.target.value));
$("#volume").oninput = () => player.setMix();
async function chooseTrack(kind) {
  const request = ++state.trackRequest, generation = state.generation;
  try {
    if (kind !== "melody" && !player.buffers[kind]) {
      $("#audio-status").textContent = t("正在载入{track}，当前播放继续…", {track: t(trackNames[kind])});
      await player.ensureTrack(kind);
    }
    if (request !== state.trackRequest || generation !== state.generation || !player.ready) return;
    state.mode = kind;
    player.setMix();
    updateControls();
    $("#audio-status").textContent = t("试听：{track} · 空格播放 / 暂停", {track: t(trackNames[state.mode])});
    if (kind === "instrumental" && Number($("#guide-volume").value) > 0) await loadGuideVoice();
  } catch (error) {
    if (request !== state.trackRequest || generation !== state.generation) return;
    notice(t(error.message), true);
    $("#audio-status").textContent = t("{track}载入失败，点击音轨可重试 · 当前试听：{current}", {track: t(trackNames[kind]), current: t(trackNames[state.mode])});
  }
}
document.querySelectorAll("[data-track]").forEach((button) => {
  button.onclick = () => chooseTrack(button.dataset.track);
});
$("#lyric-list").onclick = (event) => {
  const edit = event.target.closest("[data-edit]");
  if (edit) {
    openLyricEditor(Number(edit.dataset.edit));
    return;
  }
  const button = event.target.closest("[data-seek]");
  if (button && player.ready) {
    state.selectedLine = Number(button.dataset.lineIndex);
    player.seek(Number(button.dataset.seek));
  }
};
$("#loop-button").onclick = () => {
  if (!state.project?.lyrics.segments.length) {
    notice(t("当前歌曲没有可循环的歌词句，可以拖动进度条试听。"));
    return;
  }
  state.loop = !state.loop;
  state.loopPadding = 0;
  $("#loop-button").setAttribute("aria-pressed", String(state.loop));
  if (state.loop) {
    const line = state.project.lyrics.segments[state.selectedLine];
    if (player.time < line.start || player.time >= line.end) player.seek(line.start);
  }
};
$("#zoom").onchange = () => {
  updateViewControls();
  drawTimeline();
};
$("#view-range").oninput = (event) => {
  state.viewStart = Number(event.target.value);
  updateViewControls();
  drawTimeline();
};
$("#timeline").onclick = (event) => {
  if (!player.ready) return;
  const bounds = event.target.getBoundingClientRect(),
    position = event.clientX - bounds.left;
  if (position >= 57) player.seek(state.viewStart + (position - 57) / (bounds.width - 69) * viewDuration());
};
$("#export").onchange = (event) => {
  const kind = event.target.value;
  if (!kind || !state.job) return;
  const anchor = document.createElement("a");
  anchor.href = `/api/projects/${state.job.id}/assets/${kind}${versionQuery()}`;
  anchor.download = kind;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  event.target.value = "";
};
document.addEventListener("keydown", (event) => {
  if ($("#lyrics-dialog").open && event.ctrlKey && event.key === "Enter") {
    event.preventDefault();
    $("#lyrics-save").click();
    return;
  }
  if ($("#singalong").open && !["INPUT", "SELECT"].includes(event.target.tagName)) {
    if (event.code === "Space") { event.preventDefault(); $("#play-button").click(); }
    if (event.key === "ArrowUp" || event.key === "ArrowDown") { event.preventDefault(); navigateLine(event.key === "ArrowUp" ? -1 : 1); }
    return;
  }
  if (document.querySelector("dialog[open]")) return;
  if (["INPUT", "SELECT", "TEXTAREA", "BUTTON"].includes(event.target.tagName) || !player.ready) return;
  if (event.key.toLowerCase() === "n") { event.preventDefault(); navigateReview(); }
  if (event.key.toLowerCase() === "k") { event.preventDefault(); $("#singalong-button").click(); }
  if (event.code === "Space") {
    event.preventDefault();
    $("#play-button").click();
  }
  if (event.code === "ArrowLeft" || event.code === "ArrowRight") {
    event.preventDefault();
    player.seek(player.time + (event.code === "ArrowLeft" ? -5 : 5));
  }
  if (event.code === "ArrowUp" || event.code === "ArrowDown") {
    event.preventDefault();
    navigateLine(event.code === "ArrowUp" ? -1 : 1);
  }
});
new ResizeObserver(() => drawTimeline()).observe($("#timeline"));

async function deleteProject(id) {
  const deleted = await api(`/api/projects/${id}`, {
    method: "DELETE"
  });
  toast(t("「{title}」已移入回收站", {title: deleted.title}), id);
  const wasSelected = state.job?.id === id;
  if (wasSelected) {
    ++state.generation;
    state.job = null;
    resetResult();
    history.replaceState(null, "", "/");
  }
  await refreshProjects();
  if (wasSelected) {
    if (state.jobs.length) await selectProject(state.jobs[0].id);
    else renderStatus();
  }
  await refreshTrash();
}

async function refreshTrash() {
  const rows = await api("/api/trash");
  state.trashRows = rows;
  renderTrash(rows);
}
function renderTrash(rows = state.trashRows || []) {
  $("#trash-count").textContent = rows.length || "";
  $("#trash-list").innerHTML = rows.length ? rows.map((row) => `<div class="trash-row"><span><strong>${escape(row.title)}</strong><small>${escape(t(statuses[row.status] || row.status))} · ${new Date(row.deleted_at * 1000).toLocaleDateString(MusicI18n.locale)}</small></span><button class="button" data-restore="${row.id}">${t("恢复")}</button></div>`).join("") : `<div class="trash-empty"><span>♲</span><p>${t("回收站是空的")}</p><small>${t("删除的歌曲可以从这里找回。")}</small></div>`;
}

async function restoreProject(id) {
  const job = await post(`/api/trash/${id}/restore`);
  await refreshProjects();
  await refreshTrash();
  if (!state.job) await selectProject(job.id);
  toast(t("「{title}」已恢复", {title: job.title}));
}

async function navigateReview() {
  const lines = state.project?.lyrics.segments || [], filter = $("#review-filter").value;
  const from = state.activeLine < 0 ? -1 : state.selectedLine;
  for (let step = 1; step <= lines.length; step++) {
    const index = (from + step) % lines.length, review = state.edits.review?.lines[lines[index].id];
    if (!review || review.reviewed || !review.kinds.length || (filter !== "all" && !review.kinds.includes(filter))) continue;
    state.selectedLine = index;
    state.loop = true;
    state.loopPadding = 0.8;
    $("#loop-button").setAttribute("aria-pressed", "true");
    await player.seek(Math.max(0, lines[index].start - 0.8));
    await player.play();
    await openLyricEditor(index);
    return;
  }
  toast(t("当前筛选下没有尚待核对的歌词。核对记录不会改变实际词时间。"));
}

async function markReviewed() {
  const edit = state.editingLine;
  if ($("#lyrics-input").value !== state.project.lyrics.segments[edit.index].text) {
    $("#lyrics-error").textContent = t("请先保存修改，再标记已核对。");
    return;
  }
  $("#mark-reviewed").disabled = true;
  try {
    const checked = !state.edits.review?.lines[edit.id]?.reviewed;
    const response = await patch(`/api/projects/${edit.projectId}/review`, {version: edit.version, revision: state.edits.revision, line_id: edit.id, reviewed: checked});
    if (state.job?.id !== edit.projectId || state.version !== edit.version) return;
    state.edits = {...state.edits, ...response};
    renderLyrics();
    $("#lyrics-dialog").close();
    if (checked && state.edits.review.counts.pending) await navigateReview();
    else toast(checked ? t("已记录试听核对，实际词时间保持原样") : t("已取消核对标记"));
  } catch (error) { $("#lyrics-error").textContent = error.message; }
  finally { updateControls(); }
}

async function showCandidate(version) {
  const id = state.job?.id;
  const generation = state.generation;
  if (!id) return;
  const [project, info] = await Promise.all([
    api(`/api/projects/${id}/result?version=${encodeURIComponent(version)}`),
    api(`/api/projects/${id}/versions`)
  ]);
  if (state.job?.id !== id || generation !== state.generation || !state.project) return;
  state.versions = info.versions;
  renderVersions();
  const metadata = info.versions.find(v => v.id === version);
  if (!metadata?.candidate) { toast(t("该候选已经处理，可在结果版本中查看")); return; }
  if (metadata.base_version !== state.version) {
    toast(t("原版本已切换，请切回原版本查看候选，或重新生成"));
    return;
  }
  const lineId = metadata.line_id;
  const before = state.project.lyrics.segments.find(l => l.id === lineId);
  const found = project.lyrics.segments.filter(l => l.id === lineId || l.id.startsWith(`${lineId}-r`));
  state.candidate = {id, version, base: state.version};
  state.candidateView = {before, found, project};
  renderCandidate();
  $("#candidate-listen").onclick = async () => {
    state.loop = false;
    $("#loop-button").setAttribute("aria-pressed", "false");
    await player.seek(Math.max(0, (before?.start || 0) - 0.8));
    await player.play();
  };
  $("#candidate-error").textContent = "";
  $("#candidate-dialog").showModal();
}
function renderCandidate() {
  const {before, found, project} = state.candidateView;
  const previousListener = $("#candidate-listen")?.onclick;
  $("#candidate-content").innerHTML = `<div class="candidate-text"><small>${t("正在使用")}</small><p>${escape(before?.text || '')}</p></div><div class="candidate-text"><small>${t("候选")} · ${escape(modelLabel(project.settings))}</small><p>${escape(found.map(l => l.text).join(' '))}</p></div><button id="candidate-listen" class="button subtle">${t("♫ 试听原音频")}</button>`;
  $("#candidate-listen").onclick = previousListener;
}

function refreshSingalong(time, active) {
  if (!$("#singalong").open || !state.project) return;
  const lines = state.project.lyrics.segments;
  let index = active;
  if (index < 0) index = lines.findIndex(line => line.start > time);
  if (index < 0) index = lines.length - 1;
  $("#singalong-time").textContent = `${fmt(time)} / ${fmt(player.duration)}`;
  $("#singalong-seek").value = time;
  if (index === state.singalongLine) return;
  state.singalongLine = index;
  const line = lines[index];
  $("#singalong-previous").textContent = lines[index - 1]?.text || "";
  $("#singalong-current").innerHTML = line ? lyricMarkup(line, index) : "";
  $("#singalong-next").textContent = lines[index + 1]?.text || "";
  $("#singalong-hint").textContent = active < 0 ? t("间奏 · 等待下一句") : t("点击歌词可定位 · 灰色文字只有句级时间");
  for (const word of line?.words || []) {
    if (time >= word.start && time < word.end) $("#singalong-current").querySelector(`[data-word="${CSS.escape(word.id)}"]`)?.classList.add("current");
  }
}

$("#review-filter").onchange = () => { renderLyrics(); refreshPlayback(); };
$("#next-review").onclick = () => navigateReview().catch(e => notice(t(e.message), true));
$("#mark-reviewed").onclick = markReviewed;
$("#candidate-button").onclick = () => showCandidate(state.job.candidate_version).catch(e => notice(t(e.message), true));
$("#candidate-accept").onclick = async () => {
  const candidate = state.candidate;
  $("#candidate-accept").disabled = true;
  try {
    await post(`/api/projects/${candidate.id}/versions/select`, {version: candidate.version, expected_current: candidate.base});
    $("#candidate-dialog").close();
    await refreshProjects();
    await selectProject(candidate.id);
    toast(t("已采用候选版本，原版本可随时切回"));
  } catch (error) { $("#candidate-error").textContent = error.message; }
  finally { $("#candidate-accept").disabled = false; }
};
$("#singalong-button").onclick = () => {
  if (!state.project || !player.ready) return;
  $("#singalong-title").textContent = state.job.title;
  $("#singalong-seek").max = player.duration;
  state.singalongLine = -2;
  $("#singalong").showModal();
  refreshPlayback();
};
$("#singalong-play").onclick = () => $("#play-button").click();
$("#singalong-prev").onclick = () => navigateLine(-1);
$("#singalong-next-button").onclick = () => navigateLine(1);
$("#singalong-seek").oninput = e => player.seek(Number(e.target.value));
$("#guide-volume").oninput = e => {
  $("#guide-value").value = `${Math.round(Number(e.target.value) * 100)}%`;
  player.setMix();
  if (Number(e.target.value) > 0 && state.mode === "instrumental") loadGuideVoice();
};
async function loadGuideVoice() {
  const generation = state.generation;
  try {
    await player.ensureTrack("vocals");
    if (generation === state.generation) player.setMix();
  } catch (error) {
    if (generation === state.generation) notice(t(error.message), true);
  }
}
$("#singalong-current").onclick = e => {
  const button = e.target.closest("[data-seek]");
  if (button) player.seek(Number(button.dataset.seek));
};

function navigateLine(direction) {
  const lines = state.project?.lyrics.segments;
  if (!lines?.length) return;
  state.loopPadding = 0;
  const current = lines.findIndex((line) => player.time >= line.start && player.time < line.end);
  state.selectedLine = Math.max(0, Math.min(lines.length - 1, (current >= 0 ? current : state.selectedLine) + direction));
  player.seek(lines[state.selectedLine].start);
}

async function openLyricEditor(index) {
  const projectId = state.job.id;
  try {
    const version = state.version;
    const [edits, project] = await Promise.all([api(`/api/projects/${projectId}/lyrics${versionQuery()}`), api(`/api/projects/${projectId}/result${versionQuery()}`)]);
    if (state.job?.id !== projectId) return;
    const latest = await api(`/api/projects/${projectId}`);
    if ((latest.current_version || "original") !== version) throw new Error(t("当前结果已更新，请重新打开歌曲后再编辑。"));
    state.edits = edits;
    state.project = project;
    renderLyrics();
  } catch (e) {
    notice(t(e.message), true);
    return;
  }
  const line = state.project.lyrics.segments[index];
  state.editingLine = {
    id: line.id,
    index,
    projectId: state.job.id,
    version: state.version
  };
  $("#lyrics-editor-title").textContent = t("修改第 {line} 句歌词", {line: index + 1});
  $("#edit-line-time").textContent = `${fmt(line.start, true)} — ${fmt(line.end, true)}`;
  $("#lyrics-input").value = line.text;
  $("#original-lyric").textContent = state.edits.original[line.id];
  $("#lyrics-error").textContent = "";
  $("#lyrics-restore").disabled = !(line.id in state.edits.changes);
  $("#retry-quality").value = ["cpu-small", "cuda-small"].includes(state.system?.distribution) ? "balanced" : state.project.settings.asr_backend === "qwen" ? "text" : state.defaultQuality === "qwen" ? "qwen" : "text";
  $("#retry-source").value = $("#lyrics-source").value;
  $("#mark-reviewed").textContent = state.edits.review?.lines[line.id]?.reviewed ? t("取消已核对") : t("✓ 已试听核对");
  $("#lyrics-dialog").showModal();
  $("#lyrics-input").focus();
}

async function saveLyric(text) {
  const edit = state.editingLine;
  $("#lyrics-save").disabled = true;
  $("#lyrics-restore").disabled = true;
  try {
    const changes = await patch(`/api/projects/${edit.projectId}/lyrics`, {
      revision: state.edits.revision,
      ...(state.legacy ? {} : {version: edit.version}),
      changes: {
        [edit.id]: text
      }
    });
    const project = await api(`/api/projects/${edit.projectId}/result?version=${edit.version}`);
    if (state.job?.id !== edit.projectId || state.version !== edit.version) return;
    state.edits = await api(`/api/projects/${edit.projectId}/lyrics?version=${edit.version}`);
    state.project = project;
    renderLyrics();
    drawTimeline();
    refreshPlayback();
    $("#lyrics-dialog").close();
    toast(text === null ? t("已恢复识别原文") : t("歌词已保存，导出文件已同步更新"));
  } catch (error) {
    $("#lyrics-error").textContent = error.message;
  } finally {
    $("#lyrics-save").disabled = false;
    $("#lyrics-restore").disabled = false;
  }
}

$("#project-search").oninput = renderProjects;
$("#delete-button").onclick = () => deleteProject(state.job.id).catch((e) => notice(t(e.message), true));
$("#trash-button").onclick = () => {
  refreshTrash().catch((e) => notice(t(e.message), true));
  $("#trash-dialog").showModal();
};
$("#mobile-trash").onclick = $("#trash-button").onclick;
$("#toast-close").onclick = () => {
  $("#toast").hidden = true;
};
$("#toast-undo").onclick = async () => {
  const id = state.lastDeleted;
  $("#toast-undo").disabled = true;
  try {
    if (id) await restoreProject(id);
  } catch (e) {
    notice(t(e.message), true);
  } finally {
    $("#toast-undo").disabled = false;
  }
};
$("#trash-list").onclick = (event) => {
  const button = event.target.closest("[data-restore]");
  if (button) {
    button.disabled = true;
    restoreProject(button.dataset.restore).catch((e) => {
      notice(t(e.message), true);
      button.disabled = false;
    });
  }
};
$("#rename-button").onclick = () => {
  $("#rename-input").value = state.job.title;
  $("#rename-error").textContent = "";
  $("#rename-dialog").showModal();
  $("#rename-input").focus();
  $("#rename-input").select();
};
$("#rename-form").onsubmit = async (event) => {
  event.preventDefault();
  $("#rename-save").disabled = true;
  try {
    state.job = await patch(`/api/projects/${state.job.id}`, {
      title: $("#rename-input").value
    });
    await refreshProjects();
    renderStatus();
    $("#rename-dialog").close();
    toast(t("歌曲名称已保存"));
  } catch (e) {
    $("#rename-error").textContent = e.message;
  } finally {
    $("#rename-save").disabled = false;
  }
};
$("#lyrics-form").onsubmit = (event) => {
  event.preventDefault();
  saveLyric($("#lyrics-input").value);
};
$("#lyrics-restore").onclick = () => saveLyric(null);
$("#edit-listen").onclick = async () => {
  const line = state.project.lyrics.segments[state.editingLine.index];
  state.selectedLine = state.editingLine.index;
  state.loop = true;
  state.loopPadding = 0.8;
  $("#loop-button").setAttribute("aria-pressed", "true");
  await player.seek(Math.max(0, line.start - state.loopPadding));
  await player.play();
};
$("#retry-line-button").onclick = async () => {
  const edit = state.editingLine;
  if ($("#lyrics-input").value !== state.project.lyrics.segments[edit.index].text) {
    $("#lyrics-error").textContent = t("请先保存当前修改，再重新识别这一句。");
    return;
  }
  $("#retry-line-button").disabled = true;
  try {
    await startAnalysis({scope: "retry", line_id: edit.id, base_version: edit.version, candidate: true, quality: $("#retry-quality").value, lyrics_input: $("#retry-source").value, alignment: "anchors"});
    $("#lyrics-dialog").close();
    toast(t("正在生成候选，完成后可试听比较；原版本继续保留"));
  } catch (e) { $("#lyrics-error").textContent = e.message; }
  finally { $("#retry-line-button").disabled = false; }
};
$("#previous-line").onclick = () => navigateLine(-1);
$("#next-line").onclick = () => navigateLine(1);
document.querySelectorAll("[data-close]").forEach((button) => button.onclick = () => document.getElementById(button.dataset.close).close());

function modelLabel(settings = {}) {
  if (settings.precomputed_demo) return t("体验示例 · 预计算结果");
  if (settings.lyrics_text_source === "user_reference") return t("用户提供歌词");
  if (settings.lyrics_text_source === "user_corrected") return t("已纠正歌词");
  const model = settings.asr_backend === "qwen" ? "Qwen3-ASR 1.7B" : settings.asr_backend === "heart" ? "HeartTranscriptor" : settings.asr_model?.includes("turbo") ? "Whisper turbo" : `Whisper ${settings.asr_model || "small"}`;
  return settings.lyrics_text_source === "selective_retry" ? `${t("单句更新")} · ${model}` : model;
}
const scopeLabel = (scope) => ({full: t("整曲分析"), lyrics: t("歌词更新"), align: t("纠词后对齐"), reference: t("提供歌词对齐"), retry: t("单句重识别")}[scope] || scope);
function versionLabel(item) {
  const date = new Date(item.created_at * 1000).toLocaleString(MusicI18n.locale, {month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false});
  return `${item.candidate ? t("待确认候选 · ") : ""}${item.id === "original" ? t("首次分析") : scopeLabel(item.scope)} · ${modelLabel(item.settings)} · ${date}${item.edits_count ? ` · ${t("{count}句纠词", {count: item.edits_count})}` : ""}${item.status !== "complete" ? ` · ${t(statuses[item.status] || item.status)}` : ""}`;
}
function renderVersions() {
  $("#version-bar").hidden = !state.project;
  const settings = state.project?.settings || {};
  $("#result-model").textContent = modelLabel(settings);
  $("#result-model").title = `${settings.asr_model || "small"} @ ${settings.asr_revision || t("未记录修订版")}`;
  const method = state.project?.lyrics.timing_method || "";
  $("#result-alignment").textContent = (method.includes("anchor") || method.includes("forced_alignment") || method.includes("qwen") || method.includes("fallback")) ? (method.includes("anchor") ? `${method.includes('dual') ? t("双模型声学锚点") : t("声学锚点对齐")} · ${t("灰色字按句定位")}` : method.includes("fallback") ? t("独立时间对齐 · 部分句子需核对") : t("独立时间对齐")) : method.includes("coarse") ? t("分段时间 · 尚无可靠逐词时间") : t("模型自带时间 · 可重新对齐");
  $("#version-picker").innerHTML = state.versions.map(item => `<option value="${item.id}" ${item.status !== "complete" ? "disabled" : ""}>${escape(versionLabel(item))}</option>`).join("");
  $("#version-picker").value = state.version;
  updateControls();
}
$("#version-picker").onchange = async (event) => {
  const version = event.target.value, id = state.job.id;
  if (state.versions.find(item => item.id === version)?.candidate) {
    event.target.value = state.version;
    await showCandidate(version).catch(e => notice(t(e.message), true));
    return;
  }
  event.target.disabled = true;
  state.switchingVersion = true;
  updateControls();
  try {
    await post(`/api/projects/${id}/versions/select`, {version, expected_current: state.version});
    await selectProject(id);
    toast(t("已切换结果版本，歌词修改随版本恢复"));
  } catch (e) {
    notice(t(e.message), true);
    $("#version-picker").value = state.version;
  } finally { state.switchingVersion = false; updateControls(); }
};
$("#analysis-scope").onchange = updateControls;
$("#quality").onchange = () => {
  $("#alignment").value = $("#quality").value === "configured" ? state.defaultAlignment : ["qwen", "heart"].includes($("#quality").value) ? (state.defaultAlignment === "anchors_dual" ? "anchors_dual" : "anchors") : "native";
};
$("#reference-button").onclick = () => {
  state.referenceBase = {projectId: state.job.id, version: state.version, revision: state.edits.revision};
  $("#reference-input").value = state.project.lyrics.segments.map(line => line.text).join("\n");
  $("#reference-error").textContent = "";
  $("#reference-dialog").showModal();
  $("#reference-input").focus();
};
$("#reference-form").onsubmit = async (event) => {
  event.preventDefault();
  $("#reference-submit").disabled = true;
  try {
    if (state.job.id !== state.referenceBase.projectId) throw new Error(t("歌曲已切换，请重新打开歌词导入。"));
    await startAnalysis({scope: "reference", alignment: $("#alignment").value === "native" ? "anchors" : $("#alignment").value, base_version: state.referenceBase.version, edit_revision: state.referenceBase.revision, reference_text: $("#reference-input").value});
    $("#reference-dialog").close();
    toast(t("开始对齐提供的歌词，原结果已保留"));
  } catch (e) { $("#reference-error").textContent = e.message; }
  finally { $("#reference-submit").disabled = false; }
};
let compareGeneration = 0;
async function renderComparison() {
  const generation = ++compareGeneration;
  const left = $("#compare-left").value, right = $("#compare-right").value;
  $("#compare-summary").textContent = t("正在载入版本差异…");
  $("#compare-content").innerHTML = "";
  try {
    const data = await api(`/api/projects/${state.job.id}/compare?left=${left}&right=${right}`);
    if (generation !== compareGeneration) return;
    state.comparison = data;
    drawComparison(data);
  } catch (e) { $("#compare-summary").textContent = t(e.message); }
}
function drawComparison(data) {
    $("#compare-summary").textContent = data.changes.length ? t("{count}处文字变化 · 点击时间试听", {count: data.changes.length}) : t("两版文字相同；可分别试听核对时间位置。");
    const indices = [new Set(), new Set()];
    data.changes.forEach(change => [change.left, change.right].forEach((range, side) => {
      for (let i = range[0]; i < range[1]; i++) indices[side].add(i);
    }));
    $("#compare-content").innerHTML = [data.left, data.right].map((side, i) => `<section class="comparison-side"><h3>${i ? t("之后") : t("之前")} · ${escape(modelLabel(side.settings))}</h3>${side.segments.map((line, j) => `<article class="comparison-line ${indices[i].has(j) ? (i ? "added" : "removed") : ""}"><button class="compare-seek" data-compare-seek="${line.start}" aria-label="${t("试听{time}", {time: fmt(line.start)})}">${fmt(line.start, true)}</button><p>${escape(line.text)}</p></article>`).join("") || `<p class="editor-note">${t("此版本没有歌词")}</p>`}</section>`).join("");
}
$("#compare-button").onclick = async () => {
  try {
    const history = await api(`/api/projects/${state.job.id}/versions`);
    state.versions = history.versions;
    const completed = state.versions.filter(item => item.status === "complete");
    const options = completed.map(item => `<option value="${item.id}">${escape(versionLabel(item))}</option>`).join("");
    $("#compare-left").innerHTML = $("#compare-right").innerHTML = options;
    $("#compare-right").value = state.version;
    $("#compare-left").value = completed.find(item => item.id !== state.version)?.id || state.version;
    $("#compare-dialog").showModal();
    await renderComparison();
  } catch (e) { notice(t(e.message), true); }
};
$("#compare-left").onchange = $("#compare-right").onchange = renderComparison;
$("#compare-content").onclick = async (event) => {
  const button = event.target.closest("[data-compare-seek]");
  if (button && player.ready) { await player.seek(Number(button.dataset.compareSeek)); await player.play(); }
};

async function initialize() {
  resetResult();
  updateControls();
  try {
    const system = await api("/api/system");
    state.legacy = system.features?.workbench !== "v4" || !system.recognizers;
    state.system = system;
    if (["cpu-small", "cuda-small"].includes(system.distribution)) {
      $("#runtime-help").hidden = true;
      $("#alignment").querySelector('[value="anchors_dual"]').disabled = true;
    }
    $("#device").querySelector('[value="cuda"]').disabled = system.distribution === "cpu-small" || system.acceleration?.cuda_available === false;
    $("#build-version").textContent = `LOCAL · v${system.version}`;
    $("#runtime-help").hidden = system.inference_installed !== false;
    $("#hardware").textContent = system.distribution === "cpu-small" ? t("CPU · 已内置分析模型") : system.gpu ? system.gpu.replace("NVIDIA GeForce ", "").replace(/,\s*(\d+)/, (_, memory) => ` · ${Math.round(Number(memory) / 1024)}GB`) : t("CPU · 模型在本机运行");
    $("#offline").checked = system.defaults.offline;
    $("#device").value = system.defaults.device;
    $("#language").value = system.defaults.language || "";
    state.defaultQuality = ["qwen", "heart"].includes(system.defaults.asr_backend) ? system.defaults.asr_backend : system.defaults.asr_model === "small" ? "balanced" : "configured";
    state.defaultAlignment = system.defaults.lyrics_alignment || "native";
    if (state.defaultAlignment === "anchors" && system.defaults.anchor_model === "dual") state.defaultAlignment = "anchors_dual";
    state.defaultInput = system.defaults.lyrics_input || "vocals";
    $("#quality").value = state.defaultQuality;
    $("#alignment").value = state.defaultAlignment;
    $("#lyrics-source").value = state.defaultInput;
    renderRuntimeStatus();
    await refreshProjects();
    await refreshTrash();
    const requested = new URLSearchParams(location.search).get("project");
    const selection = state.jobs.find((job) => job.id === requested) || state.jobs[0];
    if (selection) await selectProject(selection.id);
    if (state.legacy) notice(t("页面已更新，后台服务需要重启。请在启动窗口按 Ctrl+C，再双击 Start-Music-Studio.cmd，使用新打开的页面。"), true);
  } catch (error) {
    notice(t(error.message), true);
  }
  setInterval(poll, 1400);
  requestAnimationFrame(animate);
}
function renderRuntimeStatus() {
  const modes = state.system?.recognizers;
  if (!modes) return;
  const labels = {whisper: "Whisper", qwen: "Qwen", heart: "HeartTranscriptor"};
  const backends = {balanced: "whisper", text: "whisper", qwen: "qwen", heart: "heart", configured: state.system.defaults.asr_backend};
  for (const id of ["#quality", "#retry-quality"]) {
    for (const option of $(id).options) {
      option.disabled = modes[backends[option.value]]?.available === false ||
        (["cpu-small", "cuda-small"].includes(state.system.distribution) && option.value === "text");
    }
  }
  const available = Object.keys(labels).filter(key => modes[key]?.available).map(key => labels[key]);
  const missing = Object.keys(labels).filter(key => modes[key]?.available === false).map(key => labels[key]);
  const node = $("#recognizer-status");
  node.hidden = !missing.length || !available.length;
  node.textContent = t("可用识别：{available}；{missing} 需单独安装后重启。", {available: available.join(" / "), missing: missing.join(" / ")});
  if (["cpu-small", "cuda-small"].includes(state.system.distribution)) {
    node.textContent = t("已内置 Whisper small。其他识别模型可通过源码方式配置。");
    const gpu = state.system.acceleration?.cuda_available && state.system.distribution !== "cpu-small";
    if (state.system.distribution === "cuda-small") {
      $("#hardware").textContent = gpu ? `GPU · ${state.system.acceleration.name.replace("NVIDIA GeForce ", "")}` : t("CPU · GPU 暂不可用");
    }
    $("#quality-note").textContent = t(gpu ? "已启用 NVIDIA GPU 加速，自动选择会使用显卡。歌词、音符和时间是自动估计，可试听并修改歌词。" : "本机 CPU 离线分析，整曲可能需要数分钟。歌词、音符和时间是自动估计，可试听并修改歌词。");
    if (!gpu && state.system.distribution === "cuda-small") {
      const reasons = {cpu_runtime: "当前为 CPU 运行环境，请重新安装 GPU 版。", driver_unavailable: "未找到可用的 NVIDIA GPU，请检查显卡驱动。", cuda_check_failed: "GPU 检查未通过，请更新 NVIDIA 驱动后重启软件，或选择 CPU。"};
      node.textContent += " " + t(reasons[state.system.acceleration?.reason] || reasons.cuda_check_failed);
      node.hidden = false;
      node.title = state.system.acceleration?.detail || "";
    }
  }
  if ($("#quality").selectedOptions[0]?.disabled && modes.whisper?.available) {
    $("#quality").value = "balanced";
    state.defaultQuality = "balanced";
  }
}
// A language change only redraws UI. It never selects a project, resets the player,
// fetches audio, changes model settings, or replaces an editor's current input.
function refreshLanguage() {
  renderRuntimeStatus();
  renderProjects();
  renderStatus();
  renderTrash();
  $("#analysis-options-label").textContent = t(state.job?.has_result ? "更新分析与歌词" : "分析设置");
  if (state.project) {
    renderVersions(); renderLyrics();
    $("#stat-lyrics").innerHTML = `${state.project.lyrics.segments.length}<small>${t("句")}</small>`;
    $("#stat-notes").innerHTML = `${state.project.melody.notes.length}<small>${t("个")}</small>`;
  }
  if (state.editingLine && $("#lyrics-dialog").open) {
    $("#lyrics-editor-title").textContent = t("修改第 {line} 句歌词", {line: state.editingLine.index + 1});
    $("#mark-reviewed").textContent = t(state.edits.review?.lines[state.editingLine.id]?.reviewed ? "取消已核对" : "✓ 已试听核对");
  }
  if (state.candidateView && $("#candidate-dialog").open) renderCandidate();
  if (state.comparison && $("#compare-dialog").open) drawComparison(state.comparison);
  for (const id of ["notice", "toast-text", "audio-status", "rename-error", "lyrics-error", "candidate-error", "reference-error"]) {
    const node = document.getElementById(id);
    node.textContent = MusicI18n.retranslate(node.textContent);
  }
  if (player.ready) $("#audio-status").textContent = t("试听：{track} · 空格播放 / 暂停", {track: t(trackNames[state.mode])});
  if (state.system && !state.system.gpu) $("#hardware").textContent = t("CPU · 模型在本机运行");
  if (state.system?.distribution === "cpu-small") $("#hardware").textContent = t("CPU · 已内置分析模型");
  state.singalongLine = -2;
  drawTimeline(); refreshPlayback(); updateControls();
}
$("#ui-language").onchange = event => MusicI18n.setLanguage(event.target.value);
window.addEventListener("music-language-change", refreshLanguage);
window.StudioDesktop = {
  async prepareClose() {
    if ($("#lyrics-dialog").open && state.editingLine) {
      if ($("#lyrics-save").disabled) throw new Error("Lyric save is still running");
      const line = state.project.lyrics.segments[state.editingLine.index];
      if ($("#lyrics-input").value !== line.text) {
        await saveLyric($("#lyrics-input").value);
        if ($("#lyrics-dialog").open) throw new Error("Lyric changes could not be saved");
      }
    }
    if ($("#reference-dialog").open || $("#rename-dialog").open) {
      throw new Error("Finish or cancel the open form before closing");
    }
  }
};
initialize();
