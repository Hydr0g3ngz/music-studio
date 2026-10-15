"use strict";

const $ = (id) => document.getElementById(id);
const words = {
  import: ["＋ 导入音频", "＋ Import audio"],
  search: ["搜索项目", "Search projects"],
  projects: ["项目", "PROJECTS"],
  trash: ["♲ 回收站", "♲ Trash"],
  local: ["音频处理在本机完成", "Audio is processed locally"],
  workspace: ["工作区", "Workspace"],
  newProject: ["新项目", "New project"],
  classic: ["经典歌曲分析 ↗", "Classic song analysis ↗"],
  welcomeTitle: [
    "从一段声音，开始创作。",
    "Start with a sound. Make it yours.",
  ],
  welcomeCopy: [
    "剪一个片段，调整声音，或让 AI 帮你完成。每一步都可以试听、比较和撤销。",
    "Shape a clip, adjust your sound, or ask AI for help. Preview, compare and undo every step.",
  ],
  drop: ["把音频拖到这里", "Drop your audio here"],
  formats: ["MP3 · WAV · FLAC · M4A · OGG", "MP3 · WAV · FLAC · M4A · OGG"],
  choose: ["选择音频", "Choose audio"],
  demo: ["先用示例音频试一试 →", "Try it with the demo →"],
  principle1: ["原音始终保留", "Keep your original"],
  principle1Copy: [
    "修改先成为独立预览，由你决定是否采用。",
    "Every edit creates a separate preview. You choose what to keep.",
  ],
  principle2: ["不必从专业术语开始", "Start with a goal"],
  principle2Copy: [
    "选一个目标，再按需要展开参数。",
    "Choose a task and open the details when you need them.",
  ],
  principle3: ["界面与 Agent 同步", "One shared workspace"],
  principle3Copy: [
    "共用项目、操作记录和版本，方便接着编辑。",
    "The interface and agent share projects, versions and history.",
  ],
  rename: ["重命名", "Rename"],
  delete: ["删除", "Delete"],
  export: ["导出音频 ↗", "Export audio ↗"],
  timeline: ["声音时间轴", "Audio timeline"],
  timelineHelp: [
    "拖动波形选择片段；单击定位试听。",
    "Drag to select a range. Click to seek.",
  ],
  undo: ["撤销", "Undo"],
  redo: ["重做", "Redo"],
  fit: ["适应", "Fit"],
  loop: ["循环选区", "Loop selection"],
  selection: ["选区（秒）", "Selection (seconds)"],
  from: ["从", "From"],
  to: ["到", "To"],
  all: ["全选", "Select all"],
  previews: ["预览与版本", "Previews & versions"],
  previewsHelp: [
    "先听一听，再决定是否采用。",
    "Listen first. Keep the version you like.",
  ],
  activity: ["操作记录", "Activity"],
  shared: ["界面 · MCP · Codex", "UI · MCP · Codex"],
  whatNext: ["想对声音做些什么？", "What would you like to do?"],
  clip: ["做个短片段", "Make a short clip"],
  clipCopy: ["截取选区，自动淡入淡出", "Trim the selection, add gentle fades"],
  normalize: ["调整峰值电平", "Set the peak level"],
  normalizeCopy: [
    "将最高峰值调整到 −1 dBFS",
    "Bring the highest peak to −1 dBFS",
  ],
  gain: ["音量增益", "Gain"],
  add: ["加入操作", "Add to recipe"],
  fade: ["淡入 / 淡出", "Fade in / out"],
  fadeIn: ["淡入", "Fade in"],
  fadeOut: ["淡出", "Fade out"],
  advanced: ["更多操作", "More operations"],
  balance: ["左右平衡", "Stereo balance"],
  trim: ["裁剪到选区", "Trim to selection"],
  reverse: ["倒放音频", "Reverse audio"],
  mix: ["人声与伴奏混音", "Mix vocals & backing"],
  vocals: ["人声 dB", "Vocals dB"],
  instrumental: ["伴奏 dB", "Backing dB"],
  recipe: ["待预览操作", "Preview recipe"],
  clear: ["清空", "Clear"],
  render: ["生成试听预览", "Render preview"],
  renderHelp: [
    "预览不会替换当前版本。",
    "Rendering leaves your current version unchanged.",
  ],
  inspect: ["声音检查", "Audio inspection"],
  meterHelp: [
    "当前显示样本峰值与整段 RMS，不能代替感知响度或真峰值测量。",
    "Sample peak and full-file RMS. These are not perceptual loudness or true peak.",
  ],
  notConnected: ["未连接", "Disconnected"],
  agentCopy: [
    "通过共享音频工具操作项目。连接后，生成的预览会出现在左侧。",
    "Work through shared audio tools. Agent previews appear alongside yours.",
  ],
  connectAgent: ["连接本机 Codex", "Connect local Codex"],
  agentPrompt: ["告诉 Codex 你想做什么", "Tell Codex what you want to do"],
  send: ["发送", "Send"],
  stop: ["停止", "Stop"],
  agentPrivacy: [
    "音频处理仍在本机；连接 Codex 后，对话和必要的工具信息会发送给其服务。",
    "Audio processing stays local. Codex receives the conversation and necessary tool information.",
  ],
  source: ["原始音频", "Original audio"],
  current: ["当前版本", "Current version"],
  vocalAsset: ["人声", "Vocals"],
  backingAsset: ["伴奏", "Backing"],
  listen: ["试听", "Listen"],
  adopt: ["采用", "Keep"],
  adopted: ["已采用", "Current"],
  stale: ["基于旧版本", "Older base"],
  failed: ["失败", "Failed"],
  rendering: ["正在渲染…", "Rendering…"],
  noPreviews: [
    "还没有预览。先选一个右侧任务，试听它会怎样改变声音。",
    "No previews yet. Choose a task on the right to hear what it changes.",
  ],
  noEvents: ["操作记录会显示在这里。", "Your activity will appear here."],
  noRecipe: ["还没有操作", "No operations yet"],
  preparing: ["正在准备音频…", "Preparing audio…"],
  previewReady: [
    "预览已生成，试听后可采用。",
    "Your preview is ready. Listen before keeping it.",
  ],
  adoptReady: [
    "已采用预览，可随时撤销。",
    "Preview kept. You can undo this at any time.",
  ],
  busy: ["正在处理…", "Working…"],
  save: ["保存", "Save"],
  cancel: ["取消", "Cancel"],
  deleteTitle: ["移入回收站？", "Move to trash?"],
  deleteCopy: [
    "项目和原始音频会保留在回收站，可恢复。",
    "The project and its original audio can be restored from Trash.",
  ],
  restore: ["恢复", "Restore"],
  emptyTrash: ["回收站为空。", "Trash is empty."],
  exportTitle: ["导出正在试听的音频", "Export the audio you are listening to"],
  exportCopy: [
    "导出正在试听的原音、预览或已采用版本。整数 WAV 若超过满幅会提示先降低音量。",
    "Export the audio you are listening to. Integer WAV requires peaks within full scale.",
  ],
  download: ["下载 WAV", "Download WAV"],
  clipInvalid: [
    "选区需要有有效的起止时间。",
    "Choose a valid selection first.",
  ],
  chooseProject: ["先选择一个项目。", "Select a project first."],
  peak: ["样本峰值", "Sample peak"],
  rms: ["整段 RMS", "Full-file RMS"],
  clipping: ["达到或超过满幅的样本", "Samples at or above full scale"],
  channels: ["声道", "Channels"],
  frames: ["采样帧数", "Sample frames"],
  newRemote: [
    "项目出现新版本，当前试听保持不变。",
    "A new version is available. Your current playback is unchanged.",
  ],
  connected: ["已连接", "Connected"],
  connecting: ["正在连接…", "Connecting…"],
  agentRunning: ["正在处理", "Working"],
  agentDone: ["已完成", "Complete"],
  recipeDownload: ["配方", "Recipe"],
  errorPrefix: ["操作未完成：", "Could not complete: "],
  playbackError: [
    "音频暂时无法播放，请重新选择音轨。",
    "Audio could not play. Select the track again.",
  ],
  importing: ["正在导入…", "Importing…"],
  emptyLibrary: ["还没有项目", "No projects yet"],
  createdBy: ["来自", "By"],
  recipeApplied: [
    "已加入操作，可生成预览。",
    "Recipe added. Render a preview to listen.",
  ],
  selectionTip: [
    "已截取选区并添加淡入淡出，可生成预览。",
    "Selection and fades added. Render a preview to listen.",
  ],
  previewsChange: ["预览生成完成", "Preview rendered"],
  adoptChange: ["采用预览", "Preview kept"],
  undoChange: ["撤销修改", "Edit undone"],
  redoChange: ["重做修改", "Edit redone"],
  exportChange: ["导出 WAV", "WAV exported"],
  previewAsset: ["试听预览", "Preview"],
  manualTools: ["手动操作", "Manual tools"],
  agentTools: ["Codex 助手", "Codex assistant"],
  selectionChange: ["更新选区", "Selection updated"],
  demoCredit: ["示例：", "Demo: "],
  previewFail: ["预览失败", "Preview failed"],
  previewStart: ["开始渲染预览", "Preview rendering started"],
};
let language = localStorage.getItem("musicStudioNextLanguage") || "zh";
if (!["zh", "en"].includes(language)) language = "zh";
const t = (key) => words[key]?.[language === "en" ? 1 : 0] || key;
const S = {
  projects: [],
  project: null,
  session: null,
  asset: null,
  info: null,
  waveform: [],
  selection: [0, 0],
  zoom: 1,
  viewStart: 0,
  operations: [],
  events: [],
  cursor: 0,
  busy: false,
  assetToken: 0,
  agentThread: null,
  agentCursor: 0,
  agentBusy: false,
};
const audio = $("audio");
const transport = new window.AudioAssetTransport(audio);
audio.volume = 0.7;
const element = (tag, text, cls) => {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (cls) node.className = cls;
  return node;
};
function translate() {
  document.documentElement.lang = language === "en" ? "en" : "zh-CN";
  $("lang").value = language;
  document
    .querySelectorAll("[data-t]")
    .forEach((n) => (n.textContent = t(n.dataset.t)));
  document
    .querySelectorAll("[data-placeholder]")
    .forEach((n) => (n.placeholder = t(n.dataset.placeholder)));
  document
    .querySelectorAll("[data-title]")
    .forEach((n) => (n.title = t(n.dataset.title)));
  renderProjects();
  renderRecipe();
  if (S.session) {
    renderSession();
    renderCandidates();
    renderEvents();
  }
}
function notice(message, error = false) {
  const box = S.project ? $("notice") : $("global-notice");
  box.textContent = message;
  box.hidden = !message;
  box.classList.toggle("error", error);
}
async function api(path, method = "GET", body) {
  const options = { method };
  if (body !== undefined) {
    if (body instanceof FormData) options.body = body;
    else {
      options.headers = { "Content-Type": "application/json" };
      options.body = JSON.stringify(body);
    }
  }
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail;
    try {
      detail = (await response.json()).detail;
    } catch {
      detail = response.statusText;
    }
    const error = new Error(
      typeof detail === "string" ? detail : JSON.stringify(detail),
    );
    error.status = response.status;
    throw error;
  }
  return response.status === 204 ? null : response.json();
}
const base = () => `/api/projects/${S.project.id}/studio`;
function formatTime(value, precise = false) {
  value = Math.max(0, Number(value) || 0);
  const minutes = Math.floor(value / 60),
    seconds = Math.floor(value % 60);
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}${precise ? "." + String(Math.floor((value % 1) * 100)).padStart(2, "0") : ""}`;
}
async function task(action) {
  if (S.busy) return;
  S.busy = true;
  updateButtons();
  if (S.session) renderCandidates();
  try {
    await action();
  } catch (error) {
    notice(t("errorPrefix") + error.message, true);
  } finally {
    S.busy = false;
    updateButtons();
    if (S.session) renderCandidates();
  }
}
function updateButtons() {
  $("welcome-import").disabled = S.busy;
  document
    .querySelectorAll("#projects button")
    .forEach((button) => (button.disabled = S.busy));
  for (const id of [
    "render",
    "export",
    "undo",
    "redo",
    "delete",
    "rename",
    "import",
    "demo",
  ])
    $(id).disabled =
      S.busy ||
      (id === "export" && (!S.session || !S.info)) ||
      (id === "render" && !S.operations.length) ||
      (id === "undo" && !S.session?.can_undo) ||
      (id === "redo" && !S.session?.can_redo);
  $("render").textContent = t(S.busy ? "busy" : "render");
  $("play").disabled = !S.info;
  for (const id of [
    "start",
    "end",
    "quick-clip",
    "quick-normalize",
    "add-gain",
    "add-fade",
    "add-pan",
    "add-trim",
    "add-reverse",
    "add-mix",
    "clear-recipe",
    "clear-selection",
  ])
    $(id).disabled = S.busy || !S.info;
  $("connect-agent").disabled = S.busy || !S.session;
}
async function loadProjects() {
  S.projects = await api("/api/projects");
  renderProjects();
}
function renderProjects() {
  const search = $("search").value.trim().toLowerCase();
  $("count").textContent = S.projects.length;
  const list = $("projects");
  list.replaceChildren();
  for (const p of S.projects.filter((p) =>
    p.title.toLowerCase().includes(search),
  )) {
    const item = element(
      "button",
      undefined,
      "project" + (S.project?.id === p.id ? " active" : ""),
    );
    item.title = p.title;
    const text = element("span", undefined, "project-text");
    text.append(
      element("strong", p.title),
      element("small", p.duration ? formatTime(p.duration) : "AUDIO"),
    );
    item.append(element("span", "≋", "project-symbol"), text);
    item.onclick = () => task(() => openProject(p.id));
    list.append(item);
  }
  if (!S.projects.length)
    list.append(element("div", t("emptyLibrary"), "empty"));
}
async function openProject(id) {
  transport.clear();
  S.assetToken++;
  S.project =
    S.projects.find((p) => p.id === id) || (await api(`/api/projects/${id}`));
  S.session = null;
  S.asset = null;
  S.info = null;
  S.operations = [];
  S.events = [];
  S.cursor = 0;
  S.zoom = 1;
  S.viewStart = 0;
  S.agentThread = null;
  S.agentCursor = 0;
  S.agentBusy = false;
  $("file-info").textContent = t("preparing");
  $("attribution").hidden = true;
  $("assets").replaceChildren();
  $("waveform").hidden = true;
  $("ruler").replaceChildren();
  $("revision").textContent = "—";
  $("time").textContent = "00:00.00";
  $("duration").textContent = "/ —";
  $("start").value = "0";
  $("end").value = "0";
  $("selection-duration").textContent = "";
  $("loop").checked = false;
  $("candidate-count").textContent = "0";
  $("candidates").replaceChildren(element("div", t("preparing"), "empty"));
  $("events").replaceChildren();
  updateButtons();
  $("agent-messages").replaceChildren();
  $("agent-form").hidden = true;
  $("connect-agent").hidden = false;
  setAgentStatus("notConnected");
  $("welcome").hidden = true;
  $("editor").hidden = false;
  $("title").textContent = S.project.title;
  $("breadcrumb").textContent = S.project.title;
  $("classic").href = `/?project=${id}`;
  history.replaceState(null, "", `/next.html?project=${id}`);
  renderProjects();
  notice(t("preparing"));
  const session = await api(base());
  S.session = session;
  await selectAsset(session.active);
  renderSession();
  renderCandidates();
  renderRecipe();
  notice("");
  await pollEvents();
}
async function selectAsset(asset, play = false) {
  const token = ++S.assetToken;
  const key = `${S.project.id}:${asset}`;
  if (transport.key !== key || !S.info || audio.error) {
    S.asset = asset;
    S.info = null;
    updateButtons();
    const data =
      asset === S.session.active
        ? S.session
        : await api(base() + `/assets/${encodeURIComponent(asset)}/info`);
    if (token !== S.assetToken) return;
    S.info = data.audio;
    S.waveform = data.waveform;
    $("waveform").hidden = false;
    S.selection =
      S.session.selection?.asset === asset
        ? [S.session.selection.start, S.session.selection.end]
        : [0, S.info.duration];
    S.zoom = 1;
    S.viewStart = 0;
    transport.bind(key, base() + `/assets/${encodeURIComponent(asset)}`, {
      retry: Boolean(audio.error),
    });
  } else S.asset = asset;
  renderSession();
  drawWave();
  await saveSelection();
  if (play) await audio.play();
}
function renderSession() {
  if (!S.session) return;
  const info = S.info || S.session.audio;
  $("title").textContent = S.project.title;
  $("breadcrumb").textContent = S.project.title;
  const credit = S.project.attribution;
  $("attribution").hidden = !credit;
  $("attribution").replaceChildren();
  if (credit) {
    $("attribution").append(
      document.createTextNode(
        t("demoCredit") + credit.title + " · " + credit.artist + " · ",
      ),
    );
    const link = element("a", credit.license);
    try {
      const url = new URL(credit.license_url);
      if (["https:", "http:"].includes(url.protocol)) link.href = url.href;
    } catch {
      /* Invalid attribution URLs remain plain text. */
    }
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    $("attribution").append(link);
  }
  $("file-info").textContent =
    `${formatTime(info.duration)}  ·  ${(info.sample_rate / 1000).toFixed(1)} kHz  ·  ${info.channels} ${t("channels")}  ·  WAV`;
  $("revision").textContent = `v${S.session.revision}`;
  $("duration").textContent = "/ " + formatTime(info.duration, true);
  $("mix-panel").hidden = !(
    S.session.assets.includes("vocals") &&
    S.session.assets.includes("instrumental")
  );
  const assets = $("assets");
  assets.replaceChildren();
  const choices = [["source", t("source")]];
  if (S.session.active !== "source")
    choices.push([S.session.active, t("current")]);
  if (S.asset?.startsWith("candidate:") && S.asset !== S.session.active)
    choices.push([S.asset, t("previewAsset")]);
  for (const a of S.session.assets.filter((a) => a !== "source"))
    choices.push([a, t(a === "vocals" ? "vocalAsset" : "backingAsset")]);
  for (const [asset, label] of choices) {
    const button = element(
      "button",
      label,
      asset === S.asset ? "selected" : "",
    );
    button.onclick = () => task(() => selectAsset(asset));
    assets.append(button);
  }
  $("asset-label").textContent = assetName(S.asset);
  const peak = info.peak_dbfs;
  $("meter-fill").style.width =
    Math.max(0, Math.min(100, (((peak ?? -60) + 60) / 60) * 100)) + "%";
  $("meter-fill").style.background = info.peak > 1 ? "var(--danger)" : "";
  const dl = $("measurements");
  dl.replaceChildren();
  for (const [label, value] of [
    [t("peak"), peak === null ? "−∞ dBFS" : peak.toFixed(1) + " dBFS"],
    [
      t("rms"),
      info.rms_dbfs === null ? "−∞ dBFS" : info.rms_dbfs.toFixed(1) + " dBFS",
    ],
    [t("clipping"), info.samples_at_or_above_full_scale.toLocaleString()],
    [t("frames"), info.frames.toLocaleString()],
  ])
    dl.append(element("dt", label), element("dd", value));
  renderSelection();
  updateButtons();
}
function assetName(asset) {
  if (asset === "source") return t("source");
  if (asset === "vocals") return t("vocalAsset");
  if (asset === "instrumental") return t("backingAsset");
  return (
    t(asset === S.session.active ? "current" : "previewAsset") +
    " · " +
    (asset?.split(":")[1]?.slice(0, 6) || "")
  );
}
function opName(op) {
  switch (op.type) {
    case "trim":
      return `${t("trim")} · ${op.start.toFixed(2)}–${op.end.toFixed(2)} s`;
    case "gain":
      return `${t("gain")} ${op.db > 0 ? "+" : ""}${op.db} dB`;
    case "fade":
      return `${t("fade")} ${op.in_seconds || 0} / ${op.out_seconds || 0} s`;
    case "balance":
      return `${t("balance")} ${op.pan}`;
    case "normalize":
      return `${t("normalize")} ${op.peak_dbfs ?? -1} dBFS`;
    case "reverse":
      return t("reverse");
    case "mix":
      return (
        t("mix") +
        " · " +
        op.tracks.map((a) => `${a.asset} ${a.gain_db || 0} dB`).join(" / ")
      );
    default:
      return op.type;
  }
}
function renderRecipe() {
  const list = $("recipe");
  list.replaceChildren();
  S.operations.forEach((op, index) => {
    const row = element("li");
    const remove = element("button", "×");
    remove.type = "button";
    remove.setAttribute("aria-label", `${t("delete")} ${opName(op)}`);
    remove.onclick = () => {
      S.operations.splice(index, 1);
      renderRecipe();
    };
    row.append(element("span", `${index + 1}. ${opName(op)}`), remove);
    list.append(row);
  });
  if (!S.operations.length) list.append(element("li", t("noRecipe")));
  updateButtons();
}
function addOperation(op) {
  if (S.busy) return;
  if (S.operations.length >= 24) {
    notice("Maximum 24 operations per preview.", true);
    return;
  }
  S.operations.push(op);
  renderRecipe();
}
function selectedTrim() {
  const start = Number($("start").value),
    enteredEnd = Number($("end").value);
  const end =
    S.info && enteredEnd <= S.info.duration + 0.000501
      ? Math.min(enteredEnd, S.info.duration)
      : enteredEnd;
  if (!S.info || end <= start || start < 0 || end > S.info.duration + 0.00001)
    throw new Error(t("clipInvalid"));
  return { type: "trim", start, end };
}
function renderCandidates() {
  const list = $("candidates");
  list.replaceChildren();
  $("candidate-count").textContent = S.session.candidates.length;
  for (const c of S.session.candidates) {
    const active = S.session.active === `candidate:${c.id}`;
    const card = element(
      "div",
      undefined,
      "candidate" + (active ? " active" : ""),
    );
    const content = element("div");
    content.append(
      element("h3", c.operations.map(opName).join(" → ")),
      element(
        "p",
        `${c.audio ? formatTime(c.audio.duration) + " · " : ""}${t("createdBy")} ${c.actor.toUpperCase()} · v${c.base_revision} · ${new Date(c.created_at * 1000).toLocaleTimeString(language === "en" ? "en-US" : "zh-CN", { hour: "2-digit", minute: "2-digit" })}`,
      ),
    );
    const actions = element("div", undefined, "candidate-actions");
    if (c.status === "ready") {
      const listen = element("button", t("listen"), "quiet");
      listen.disabled = S.busy;
      listen.onclick = () => task(() => selectAsset(`candidate:${c.id}`, true));
      actions.append(listen);
      const keep = element(
        "button",
        t(active ? "adopted" : "adopt"),
        active ? "quiet" : "primary",
      );
      keep.disabled =
        active || c.base_revision !== S.session.revision || S.busy;
      keep.title =
        !active && c.base_revision !== S.session.revision ? t("stale") : "";
      keep.onclick = () =>
        task(async () => {
          const session = await api(base() + "/adopt", "POST", {
            revision: S.session.revision,
            candidate: c.id,
          });
          S.session = session;
          await selectAsset(session.active);
          renderCandidates();
          notice(t("adoptReady"));
          await pollEvents();
        });
      actions.append(keep);
      const recipe = element("a", t("recipeDownload"));
      recipe.href = base() + `/recipe/${c.id}`;
      recipe.download = `recipe-${c.id}.json`;
      actions.append(recipe);
    } else
      actions.append(
        element(
          "span",
          t(c.status === "failed" ? "failed" : "rendering"),
          "badge",
        ),
      );
    card.append(content, actions);
    if (c.error) content.append(element("p", c.error));
    list.append(card);
  }
  if (!S.session.candidates.length)
    list.append(element("div", t("noPreviews"), "empty"));
}
function renderEvents() {
  const list = $("events");
  list.replaceChildren();
  const names = {
    "preview.started": "previewStart",
    "preview.ready": "previewsChange",
    "preview.failed": "previewFail",
    "preview.adopted": "adoptChange",
    "history.undo": "undoChange",
    "history.redo": "redoChange",
    "audio.exported": "exportChange",
    "selection.changed": "selectionChange",
  };
  for (const e of [...S.events].reverse()) {
    const row = element("div", undefined, "event");
    row.append(
      element(
        "time",
        new Date(e.created * 1000).toLocaleTimeString(
          language === "en" ? "en-US" : "zh-CN",
          { hour: "2-digit", minute: "2-digit", second: "2-digit" },
        ),
      ),
      element("strong", e.actor.toUpperCase()),
      element("span", t(names[e.kind] || e.kind)),
    );
    list.append(row);
  }
  if (!S.events.length) list.append(element("div", t("noEvents"), "empty"));
}
async function pollEvents() {
  if (!S.project || !S.session || S.busy) return;
  const project = S.project.id;
  const events = await api(base() + `/events?after=${S.cursor}`);
  if (S.project?.id !== project || !events.length) return;
  S.cursor = events.at(-1).seq;
  S.events.push(...events);
  S.events = S.events.slice(-150);
  renderEvents();
  const selected = events
    .filter((e) => e.kind === "selection.changed" && e.actor !== "ui")
    .at(-1);
  if (selected && selected.data.asset === S.asset) {
    S.selection = [selected.data.start, selected.data.end];
    renderSelection();
    drawWave();
  }
  if (
    events.some((e) =>
      [
        "preview.ready",
        "preview.failed",
        "preview.adopted",
        "history.undo",
        "history.redo",
      ].includes(e.kind),
    )
  ) {
    const previous = S.session;
    const session = await api(base());
    if (S.project?.id !== project) return;
    S.session = session;
    if (previous.active !== session.active) {
      if (audio.paused && S.asset === previous.active)
        await selectAsset(session.active);
      else notice(t("newRemote"));
    }
    renderSession();
    renderCandidates();
  }
}
async function saveSelection() {
  if (!S.session || !S.info) return;
  const session = S.session,
    project = S.project.id,
    asset = S.asset;
  try {
    const selected = await api(
      `/api/projects/${project}/studio/selection`,
      "POST",
      {
        revision: session.revision,
        asset,
        start: S.selection[0],
        end: S.selection[1],
      },
    );
    if (S.session === session && S.asset === asset)
      session.selection = selected;
  } catch (e) {
    if (S.project?.id === project) notice(e.message, true);
  }
}
function renderSelection() {
  $("start").value = S.selection[0].toFixed(3);
  $("end").value = S.selection[1].toFixed(3);
  $("selection-duration").textContent =
    (S.selection[1] - S.selection[0]).toFixed(3) + " s";
}
function drawWave() {
  if (!S.info) return;
  const canvas = $("waveform"),
    ratio = window.devicePixelRatio || 1,
    rect = canvas.getBoundingClientRect();
  canvas.width = Math.round(rect.width * ratio);
  canvas.height = Math.round(rect.height * ratio);
  const ctx = canvas.getContext("2d");
  ctx.scale(ratio, ratio);
  const w = rect.width,
    h = rect.height,
    duration = S.info.duration,
    span = duration / S.zoom;
  S.viewStart = Math.max(0, Math.min(duration - span, S.viewStart));
  const x = (time) => ((time - S.viewStart) / span) * w;
  ctx.fillStyle = "#141a21";
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = "#26313b";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 6; i++) {
    const gx = (w * i) / 6;
    ctx.beginPath();
    ctx.moveTo(gx, 0);
    ctx.lineTo(gx, h);
    ctx.stroke();
  }
  const sx = x(S.selection[0]),
    ex = x(S.selection[1]);
  ctx.fillStyle = "#a8d8c812";
  ctx.fillRect(Math.max(0, sx), 0, Math.min(w, ex) - Math.max(0, sx), h);
  const n = S.waveform.length,
    step = 3;
  for (let px = 0; px < w; px += step) {
    const time = S.viewStart + (px / w) * span;
    const a = Math.max(0, Math.floor((time / duration) * n)),
      b = Math.min(
        n,
        Math.max(a + 1, Math.ceil(((time + (step / w) * span) / duration) * n)),
      );
    let peak = 0;
    for (let i = a; i < b; i++) peak = Math.max(peak, S.waveform[i]);
    const height = Math.max(1, Math.min(h * 0.84, peak * h * 0.85));
    ctx.fillStyle =
      time >= S.selection[0] && time <= S.selection[1] ? "#a0cbbc" : "#4a645d";
    ctx.fillRect(px, h / 2 - height / 2, 1.7, height);
  }
  ctx.strokeStyle = "#91c9b8";
  for (const edge of [sx, ex]) {
    if (edge >= 0 && edge <= w) {
      ctx.beginPath();
      ctx.moveTo(edge, 0);
      ctx.lineTo(edge, h);
      ctx.stroke();
    }
  }
  const cursor = x(audio.currentTime);
  if (cursor >= 0 && cursor <= w) {
    ctx.strokeStyle = "#efd8b5";
    ctx.beginPath();
    ctx.moveTo(cursor, 0);
    ctx.lineTo(cursor, h);
    ctx.stroke();
    ctx.fillStyle = "#efd8b5";
    ctx.fillRect(cursor - 3, 0, 6, 5);
  }
  const ruler = $("ruler");
  ruler.replaceChildren();
  for (let i = 0; i <= 6; i++)
    ruler.append(element("span", formatTime(S.viewStart + (span * i) / 6)));
}
let drag = null;
function pointerTime(event) {
  const rect = $("waveform").getBoundingClientRect();
  return Math.max(
    0,
    Math.min(
      S.info.duration,
      S.viewStart +
        (((event.clientX - rect.left) / rect.width) * S.info.duration) / S.zoom,
    ),
  );
}
$("waveform").addEventListener("pointerdown", (e) => {
  if (!S.info || S.busy) return;
  drag = { time: pointerTime(e), x: e.clientX, selection: [...S.selection] };
  $("waveform").setPointerCapture(e.pointerId);
});
$("waveform").addEventListener("pointermove", (e) => {
  if (!drag) return;
  const now = pointerTime(e);
  S.selection = [Math.min(drag.time, now), Math.max(drag.time, now)];
  renderSelection();
  drawWave();
});
$("waveform").addEventListener("pointerup", (e) => {
  if (!drag) return;
  const now = pointerTime(e);
  if (Math.abs(e.clientX - drag.x) < 4) {
    S.selection = drag.selection;
    audio.currentTime = now;
  } else {
    S.selection = [Math.min(drag.time, now), Math.max(drag.time, now)];
    audio.currentTime = S.selection[0];
  }
  drag = null;
  renderSelection();
  drawWave();
  saveSelection();
});
$("waveform").addEventListener("pointercancel", () => {
  if (drag) S.selection = drag.selection;
  drag = null;
  renderSelection();
  drawWave();
});
let selectionTimer;
function inputSelection(showError = false) {
  if (!S.info) return;
  const start = Number($("start").value),
    enteredEnd = Number($("end").value);
  const end =
    enteredEnd <= S.info.duration + 0.000501
      ? Math.min(enteredEnd, S.info.duration)
      : enteredEnd;
  if (
    !Number.isFinite(start) ||
    !Number.isFinite(end) ||
    start < 0 ||
    end > S.info.duration ||
    end <= start
  ) {
    if (showError) notice(t("clipInvalid"), true);
    return;
  }
  S.selection = [start, end];
  $("selection-duration").textContent = (end - start).toFixed(3) + " s";
  drawWave();
  clearTimeout(selectionTimer);
  selectionTimer = setTimeout(saveSelection, 150);
}
for (const id of ["start", "end"]) {
  $(id).oninput = () => inputSelection();
  $(id).onchange = () => inputSelection(true);
}
$("clear-selection").onclick = () => {
  if (!S.info) return;
  S.selection = [0, S.info.duration];
  renderSelection();
  drawWave();
  saveSelection();
};
$("zoom-in").onclick = () => {
  if (!S.info) return;
  S.zoom = Math.min(32, S.zoom * 2);
  S.viewStart = Math.max(0, audio.currentTime - S.info.duration / S.zoom / 2);
  drawWave();
};
$("zoom-out").onclick = () => {
  S.zoom = Math.max(1, S.zoom / 2);
  drawWave();
};
$("fit").onclick = () => {
  S.zoom = 1;
  S.viewStart = 0;
  drawWave();
};
async function togglePlay() {
  if (!S.info) return;
  if (!audio.paused) audio.pause();
  else {
    if (
      audio.currentTime >= S.selection[1] ||
      audio.currentTime < S.selection[0]
    )
      audio.currentTime = S.selection[0];
    try {
      await audio.play();
    } catch (e) {
      notice(t("playbackError") + " " + e.message, true);
    }
  }
}
$("play").onclick = togglePlay;
audio.addEventListener("play", () => {
  $("play").textContent = "Ⅱ";
});
audio.addEventListener("pause", () => {
  $("play").textContent = "▶";
});
audio.addEventListener("timeupdate", () => {
  if (
    $("loop").checked &&
    S.selection[1] > S.selection[0] &&
    audio.currentTime >= S.selection[1]
  )
    audio.currentTime = S.selection[0];
  $("time").textContent = formatTime(audio.currentTime, true);
  drawWave();
});
audio.addEventListener("error", () => {
  if (audio.src) notice(t("playbackError"), true);
});
audio.addEventListener("ended", () => {
  if ($("loop").checked && S.selection[1] > S.selection[0]) {
    audio.currentTime = S.selection[0];
    audio
      .play()
      .catch((error) => notice(t("playbackError") + " " + error.message, true));
  }
});
$("volume").oninput = () => {
  audio.volume = Number($("volume").value);
};
document.addEventListener("keydown", (e) => {
  if (
    e.code === "Space" &&
    !["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(e.target.tagName) &&
    !$("modal").open
  ) {
    e.preventDefault();
    togglePlay();
  }
});
window.addEventListener("resize", drawWave);
$("gain").oninput = () => {
  $("gain-value").textContent = Number($("gain").value) + " dB";
};
$("pan").oninput = () => {
  $("pan-value").textContent = $("pan").value;
};
$("add-gain").onclick = () =>
  addOperation({ type: "gain", db: Number($("gain").value) });
$("add-pan").onclick = () =>
  addOperation({ type: "balance", pan: Number($("pan").value) });
$("add-fade").onclick = () =>
  addOperation({
    type: "fade",
    in_seconds: Number($("fade-in").value),
    out_seconds: Number($("fade-out").value),
  });
$("add-reverse").onclick = () => addOperation({ type: "reverse" });
$("add-trim").onclick = () => {
  try {
    addOperation(selectedTrim());
  } catch (e) {
    notice(e.message, true);
  }
};
$("quick-normalize").onclick = () =>
  addOperation({ type: "normalize", peak_dbfs: -1 });
$("quick-clip").onclick = () => {
  try {
    const trim = selectedTrim();
    if (trim.end - trim.start === S.info.duration)
      trim.end = Math.min(trim.end, trim.start + 30);
    S.operations = [
      trim,
      {
        type: "fade",
        in_seconds: Math.min(0.3, (trim.end - trim.start) / 4),
        out_seconds: Math.min(1, (trim.end - trim.start) / 4),
      },
    ];
    renderRecipe();
    notice(t("selectionTip"));
  } catch (e) {
    notice(e.message, true);
  }
};
$("add-mix").onclick = () => {
  if (S.operations.length) {
    notice(
      language === "zh"
        ? "混音将成为新配方的第一步。"
        : "Mixing starts a new recipe.",
    );
    S.operations = [];
  }
  addOperation({
    type: "mix",
    tracks: [
      { asset: "vocals", gain_db: Number($("vocal-gain").value), pan: 0 },
      {
        asset: "instrumental",
        gain_db: Number($("instrumental-gain").value),
        pan: 0,
      },
    ],
  });
};
$("clear-recipe").onclick = () => {
  S.operations = [];
  renderRecipe();
};
$("render").onclick = () =>
  task(async () => {
    const result = await api(base() + "/preview", "POST", {
      revision: S.session.revision,
      asset: S.asset,
      operations: S.operations,
    });
    S.session = await api(base());
    renderCandidates();
    await selectAsset(`candidate:${result.id}`);
    S.operations = [];
    renderRecipe();
    notice(t("previewReady"));
  });
for (const direction of ["undo", "redo"])
  $(direction).onclick = () =>
    task(async () => {
      S.session = await api(base() + `/history/${direction}`, "POST", {
        revision: S.session.revision,
      });
      await selectAsset(S.session.active);
      renderCandidates();
    });
function modal(title, body, actions = []) {
  $("modal-title").textContent = title;
  $("modal-body").replaceChildren(...body);
  $("modal-actions").replaceChildren();
  for (const [label, action, primary] of actions) {
    const button = element("button", label, primary ? "primary" : "quiet");
    button.type = "button";
    button.onclick = action;
    $("modal-actions").append(button);
  }
  $("modal").showModal();
}
$("rename").onclick = () => {
  const input = element("input");
  input.value = S.project.title;
  input.maxLength = 120;
  input.setAttribute("aria-label", t("rename"));
  modal(
    t("rename"),
    [input],
    [
      [
        t("save"),
        () =>
          task(async () => {
            S.project = await api(`/api/projects/${S.project.id}`, "PATCH", {
              title: input.value,
            });
            await loadProjects();
            renderSession();
            $("modal").close();
          }),
        true,
      ],
    ],
  );
  input.focus();
  input.select();
};
$("delete").onclick = () =>
  modal(
    t("deleteTitle"),
    [element("p", t("deleteCopy"))],
    [
      [t("cancel"), () => $("modal").close()],
      [
        t("delete"),
        () =>
          task(async () => {
            audio.pause();
            await api(`/api/projects/${S.project.id}`, "DELETE");
            S.project = null;
            S.session = null;
            S.info = null;
            transport.clear();
            $("modal").close();
            await loadProjects();
            if (S.projects.length) await openProject(S.projects[0].id);
            else {
              $("editor").hidden = true;
              $("welcome").hidden = false;
              history.replaceState(null, "", "/next.html");
            }
          }),
        true,
      ],
    ],
  );
$("trash").onclick = () =>
  task(async () => {
    const items = await api("/api/trash"),
      body = [];
    for (const item of items) {
      const row = element("div", undefined, "trash-item"),
        restore = element("button", t("restore"), "quiet");
      restore.type = "button";
      restore.onclick = () =>
        task(async () => {
          await api(`/api/trash/${item.id}/restore`, "POST");
          await loadProjects();
          $("modal").close();
          await openProject(item.id);
        });
      row.append(element("span", item.title), restore);
      body.push(row);
    }
    if (!body.length) body.push(element("p", t("emptyTrash")));
    modal(t("trash"), body);
  });
$("export").onclick = () => {
  const select = element("select");
  select.setAttribute("aria-label", "WAV encoding");
  for (const [value, label] of [
    ["PCM_24", "WAV · 24-bit PCM"],
    ["PCM_16", "WAV · 16-bit PCM"],
    ["FLOAT", "WAV · 32-bit float"],
  ]) {
    const option = element("option", label);
    option.value = value;
    select.append(option);
  }
  modal(
    t("exportTitle"),
    [element("p", t("exportCopy")), select],
    [
      [
        t("download"),
        () =>
          task(async () => {
            const result = await api(base() + "/export", "POST", {
              revision: S.session.revision,
              asset: S.asset,
              subtype: select.value,
            });
            const a = element("a");
            a.href = result.url;
            a.download = `${S.project.title}.wav`;
            document.body.append(a);
            a.click();
            a.remove();
            $("modal").close();
            notice(
              `${t("exportChange")} · ${formatTime(result.audio.duration)} · ${select.value}`,
            );
          }),
        true,
      ],
    ],
  );
};
async function importFile(file) {
  if (!file) return;
  await task(async () => {
    notice(t("importing"));
    const body = new FormData();
    body.append("file", file);
    const record = await api("/api/projects", "POST", body);
    await loadProjects();
    await openProject(record.id);
  });
  $("file").value = "";
}
$("import").onclick = $("welcome-import").onclick = () => $("file").click();
$("file").onchange = () => importFile($("file").files[0]);
$("demo").onclick = () =>
  task(async () => {
    const record = await api("/api/demo", "POST");
    await loadProjects();
    await openProject(record.id);
  });
document.addEventListener("dragover", (e) => {
  if (e.dataTransfer.types.includes("Files")) {
    e.preventDefault();
    $("drop").classList.add("dragging");
  }
});
document.addEventListener("dragleave", (e) => {
  if (!e.relatedTarget) $("drop").classList.remove("dragging");
});
document.addEventListener("drop", (e) => {
  e.preventDefault();
  $("drop").classList.remove("dragging");
  if (e.dataTransfer.files.length) importFile(e.dataTransfer.files[0]);
});
$("search").oninput = renderProjects;
$("lang").onchange = () => {
  language = $("lang").value;
  localStorage.setItem("musicStudioNextLanguage", language);
  translate();
};
// The Codex transport is implemented by the local backend, not by an intent parser.
function inspectorMode(mode) {
  const agent = mode === "agent";
  $("tools-content").hidden = agent;
  $("meter-panel").hidden = agent;
  $("agent-content").hidden = !agent;
  $("tab-tools").setAttribute("aria-selected", String(!agent));
  $("tab-agent").setAttribute("aria-selected", String(agent));
  localStorage.setItem("musicStudioNextPanel", mode);
}
$("tab-tools").onclick = () => inspectorMode("tools");
$("tab-agent").onclick = () => inspectorMode("agent");
inspectorMode(localStorage.getItem("musicStudioNextPanel") || "tools");
function setAgentStatus(key) {
  $("agent-status").dataset.t = key;
  $("agent-status").textContent = t(key);
}
function disconnectAgent(message) {
  S.agentThread = null;
  S.agentBusy = false;
  $("connect-agent").hidden = false;
  $("agent-form").hidden = true;
  setAgentStatus("notConnected");
  if (message)
    $("agent-messages").append(element("div", message, "tool-event"));
}
$("connect-agent").onclick = () =>
  task(async () => {
    if (!S.project) return;
    setAgentStatus("connecting");
    let result;
    try {
      result = await api("/api/studio/agent/connect", "POST", {
        project: S.project.id,
      });
    } catch (error) {
      disconnectAgent(error.message);
      throw error;
    }
    S.agentThread = result.thread;
    S.agentCursor = 0;
    S.agentBusy = result.busy;
    $("agent-messages").replaceChildren();
    $("connect-agent").hidden = true;
    $("agent-form").hidden = false;
    $("agent-send").disabled = result.busy;
    $("agent-stop").hidden = !result.busy;
    setAgentStatus(result.busy ? "agentRunning" : "connected");
    notice("");
  });
$("agent-form").onsubmit = async (e) => {
  e.preventDefault();
  if (S.agentBusy || !S.agentThread) return;
  const prompt = $("agent-input").value.trim();
  if (!prompt) return;
  try {
    await api("/api/studio/agent/message", "POST", {
      thread: S.agentThread,
      message: prompt,
    });
    $("agent-input").value = "";
    S.agentBusy = true;
    $("agent-send").disabled = true;
    $("agent-stop").hidden = false;
    setAgentStatus("agentRunning");
  } catch (error) {
    notice(error.message, true);
  }
};
$("agent-stop").onclick = async () => {
  try {
    await api("/api/studio/agent/stop", "POST", { thread: S.agentThread });
  } catch (error) {
    notice(error.message, true);
  }
};
async function pollAgent() {
  if (!S.agentThread) return;
  const thread = S.agentThread;
  let result;
  try {
    result = await api(
      `/api/studio/agent/events?thread=${encodeURIComponent(thread)}&after=${S.agentCursor}`,
    );
  } catch (error) {
    if ([404, 503].includes(error.status)) disconnectAgent(error.message);
    throw error;
  }
  if (thread !== S.agentThread) return;
  if (result.connected === false) {
    disconnectAgent(t("notConnected"));
    return;
  }
  for (const event of result.events) {
    S.agentCursor = event.seq;
    const list = $("agent-messages");
    if (event.kind === "user") {
      list.append(element("div", event.text, "user"));
    } else if (event.kind === "text") {
      let target = list.lastElementChild;
      if (!target || !target.classList.contains("assistant")) {
        target = element("div", "", "assistant");
        list.append(target);
      }
      target.textContent += event.text;
    } else if (event.kind === "tool") {
      const toolNames = {
        audio_get_session: t("inspect"),
        audio_render_preview: t("render"),
        audio_set_selection: t("selectionChange"),
        audio_adopt_preview: t("adopt"),
        audio_export_wav: t("export"),
        audio_history: t("activity"),
      };
      list.append(
        element(
          "div",
          (toolNames[event.tool] || event.tool) +
            " · " +
            t(event.status === "completed" ? "agentDone" : "agentRunning"),
          "tool-event",
        ),
      );
    } else if (event.kind === "error")
      list.append(element("div", event.message, "tool-event"));
    else if (event.kind === "done") {
      S.agentBusy = false;
      $("agent-send").disabled = false;
      $("agent-stop").hidden = true;
      setAgentStatus("agentDone");
    }
    list.scrollTop = list.scrollHeight;
  }
}
let polling = false;
setInterval(async () => {
  if (polling || document.hidden) return;
  polling = true;
  try {
    await pollEvents();
    await pollAgent();
  } catch {
    /* A transient polling error must never reload audio. */
  } finally {
    polling = false;
  }
}, 1600);
translate();
(async () => {
  try {
    await loadProjects();
    const id = new URL(location.href).searchParams.get("project");
    if (id) await task(() => openProject(id));
  } catch (e) {
    notice(e.message, true);
  }
})();
