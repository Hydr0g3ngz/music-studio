/* UI messages only. Song titles, user lyrics and model output are never translated. */
(function (root) {
  "use strict";
  const en = {
    "Music Studio · 本地扒歌工作台": "Music Studio · Local song workbench",
    "Music Studio 首页": "Music Studio home",
    "听见音乐的每一层": "Hear every layer",
    "导入歌曲": "Import song", "我的项目": "My songs", "搜索歌曲…": "Search songs…",
    "搜索歌曲": "Search songs", "歌曲项目": "Song projects", "回收站": "Trash",
    "本地运行": "Running locally", "正在检查运行环境": "Checking environment",
    "工作区": "Workspace", "歌曲分析": "Song analysis", "切换歌曲项目": "Switch song",
    "导入新的歌曲": "Import a new song", "＋ 导入": "+ Import", "打开回收站": "Open Trash",
    "♫ 加载示例歌曲": "♫ Try the demo", "把歌曲，展开来看": "Unfold a song",
    "导入音频，在同一条时间轴上探索歌词、旋律与伴奏。": "Explore lyrics, melody and stems on one timeline.",
    "等待导入": "Ready to import", "重命名当前歌曲": "Rename this song",
    "重命名": "Rename", "删除当前歌曲": "Delete this song", "删除": "Delete",
    "移入回收站，可恢复": "Move to Trash; you can restore it",
    "拖入一首歌，或点击选择文件": "Drop a song here, or choose a file",
    "音频仅保存在本机": "Your audio stays on this computer", "选择音频": "Choose audio",
    "分析设置": "Analysis settings", "选择模式后即可开始": "Choose a mode to get started",
    "分析选项": "Analysis options", "更新范围": "Update", "整曲分析": "Full analysis",
    "仅更新歌词": "Lyrics only", "对齐已修改歌词": "Align corrected lyrics",
    "分析模式": "Recognition mode", "轻量 · Whisper small": "Light · Whisper small",
    "通用 · Whisper turbo": "General · Whisper turbo", "文字优先 · Qwen": "Text first · Qwen",
    "实验 · HeartTranscriptor": "Experimental · HeartTranscriptor", "使用启动配置": "Launch configuration",
    "歌词语言": "Song language", "自动识别": "Detect automatically", "中文": "Chinese",
    "✦ 开始分析": "✦ Analyze song", "高级设置": "Advanced settings",
    "设备、音源与实验对齐": "Device, audio source and experimental alignment",
    "计算设备": "Compute device", "自动选择": "Automatic", "识别音源": "Recognition audio",
    "分离人声": "Isolated vocals", "原曲": "Original", "歌词时间": "Lyric timing",
    "模型自带时间": "Native model timing", "声学锚点 · 轻量": "Acoustic guides · light",
    "声学锚点 · 更完整（需 turbo）": "Dual guides · more coverage (turbo required)",
    "Qwen 独立对齐 · 实验": "Qwen forced alignment · experimental",
    "Whisper 文字对齐 · 实验": "Whisper text alignment · experimental",
    "使用已下载模型": "Use downloaded models only",
    "Qwen 适合优先减少错词；声学锚点会标出尚未逐词定位的文字。已有结果和手动修改均保留，可比较、切回。": "Qwen prioritizes lyric text. Acoustic guides mark text without reliable word timing. Previous results and corrections stay available for comparison.",
    "分析结果版本": "Analysis versions", "当前结果": "Current result",
    "查看待确认候选": "Review candidate", "结果版本": "Result version",
    "切换分析结果版本": "Switch result version", "比较版本": "Compare versions",
    "查看诊断信息": "Show diagnostics", "分析进度": "Analysis progress",
    "准备分析": "Preparing analysis", "停止分析": "Stop analysis", "分析概览": "Analysis overview",
    "歌曲时长": "Duration", "估计速度": "Estimated tempo", "歌词段落": "Lyric lines",
    "主旋律音符": "Melody notes", "句": "lines", "个": "notes",
    "同步时间轴": "Synced timeline", "和弦 · 歌词 · 旋律 · 音轨": "Chords · lyrics · melody · stems",
    "视图": "View", "时间轴显示范围": "Timeline range", "15 秒": "15 sec", "30 秒": "30 sec", "整首": "Full song",
    "同步时间轴，分析完成后显示和弦、音符与真实音轨波形": "Timeline showing chords, notes and real audio waveforms after analysis",
    "每一层，都在同一个时间里": "Every layer, in the same moment",
    "分析完成后，点击波形或音符即可定位试听。": "After analysis, click a waveform or note to listen from that point.",
    "时间轴视窗起点": "Timeline window start", "歌词": "Lyrics",
    "点击定位 · 点击铅笔纠错": "Seek · ✎ correct", "粘贴歌词": "Paste lyrics", "跟随": "Follow",
    "筛选歌词": "Filter lyrics", "全部歌词": "All lyrics", "文字疑点": "Text hints",
    "待定位": "Missing timing", "已核对": "Reviewed", "先听，再修正": "Listen, then correct",
    "快捷键 N": "Shortcut: N", "下一处核对 ↗": "Next to review ↗",
    "歌词会出现在这里": "Your lyrics will appear here", "自动识别后可逐句试听核对": "Listen and review each line after recognition",
    "上一句歌词": "Previous lyric line", "↑ 上一句": "↑ Previous", "下一句歌词": "Next lyric line", "↓ 下一句": "↓ Next",
    "播放控制": "Playback controls", "回到开头": "Back to start", "播放": "Play", "暂停": "Pause",
    "播放位置": "Playback position", "试听音轨": "Audio tracks", "人声": "Vocals",
    "伴奏": "Backing", "旋律 MIDI": "Melody MIDI", "快捷键 K": "Shortcut: K", "⛶ 跟唱": "⛶ Sing along",
    "↻ 单句循环": "↻ Loop line", "音量": "Volume", "播放音量": "Playback volume",
    "导出分析结果": "Export results", "导出结果 ↓": "Export ↓", "主旋律 MIDI": "Melody MIDI",
    "人声 WAV": "Vocals audio", "伴奏 WAV": "Backing audio", "歌词 LRC": "Lyrics LRC", "字幕 SRT": "Captions SRT",
    "和弦 CSV": "Chords CSV", "完整项目 JSON": "Project JSON",
    "选择歌曲后开始分析": "Choose a song to begin", "自动分析结果可通过试听核对": "Listen to verify machine estimates",
    "撤销删除": "Undo delete", "关闭提示": "Dismiss", "重命名歌曲": "Rename song",
    "关闭重命名": "Close rename dialog", "歌曲名称": "Song name", "取消": "Cancel", "保存名称": "Save name",
    "修改歌词": "Edit lyrics", "关闭歌词编辑": "Close lyric editor", "♫ 循环试听上下文": "♫ Loop with context",
    "歌词文字": "Lyric text", "修改文字会保留整句时间，导出同步更新。Ctrl + Enter 保存。": "Text corrections keep line timing and update exports. Ctrl + Enter to save.",
    "识别原文：": "Original recognition: ", "尝试另一种识别方式": "Try another recognizer",
    "模型": "Model", "音源": "Audio source", "生成候选": "Generate candidate",
    "原歌词保留，试听比较后再决定是否采用。": "Keep the current lyrics and listen before accepting a candidate.",
    "✓ 已试听核对": "✓ Mark as reviewed", "恢复原文": "Restore original", "保存修改": "Save changes",
    "识别候选": "Recognition candidate", "关闭识别候选": "Close candidate dialog",
    "原版本仍在使用。模型输出可能相同，也可能引入新错误，请试听比较。": "The original version is still active. A new prediction can be unchanged or introduce errors; listen to compare.",
    "保留原版本": "Keep original", "采用候选版本": "Accept candidate", "SING ALONG · 本地伴奏": "SING ALONG · LOCAL AUDIO",
    "退出跟唱": "Exit sing along", "跟唱音轨": "Sing-along tracks", "伴奏中的原唱": "Guide vocals",
    "伴奏中的原唱音量": "Guide vocal volume over backing", "跟唱播放": "Play sing along", "跟唱暂停": "Pause sing along",
    "跟唱播放位置": "Sing-along position", "空格 播放 / 暂停 · ↑ ↓ 切句 · 灰色文字按句定位": "Space: play / pause · ↑ ↓: change line · gray text seeks to the line",
    "删除的歌曲和分析结果保存在本机，可随时恢复。": "Deleted songs and results stay on this computer and can be restored.",
    "关闭回收站": "Close Trash", "粘贴歌词并对齐": "Paste and align lyrics", "关闭粘贴歌词": "Close lyric import",
    "每行一句，保留实际演唱的重复副歌。请选择正确的歌词语言；现场版请核对增删句。": "Use one line per phrase and keep repeated choruses. Choose the song language and check live-version differences.",
    "完整歌词": "Full lyrics", "在这里粘贴正确歌词，每行一句…": "Paste the correct lyrics, one phrase per line…",
    "生成新的结果版本，原识别与手动修改均保留。": "Creates a new version while keeping existing recognition and corrections.",
    "开始对齐": "Start alignment", "比较歌词版本": "Compare lyric versions",
    "文字变化不等于准确率提升，请试听核对。": "Changed text does not prove improved accuracy. Listen to verify.",
    "关闭版本比较": "Close version comparison", "之前": "Before", "之后": "After",
    "待分析": "Ready", "正在分析": "Analyzing", "正在停止": "Stopping", "分析完成": "Complete",
    "已停止": "Stopped", "已中断": "Interrupted", "分析失败": "Failed",
    "准备音频": "Prepare audio", "分离音轨": "Separate stems", "分离人声与伴奏": "Separate vocals and backing",
    "识别歌词": "Recognize lyrics", "提取旋律": "Extract melody", "提取主旋律": "Extract vocal melody",
    "检测节拍": "Detect beats", "分析和弦": "Estimate chords", "分析中…": "Analyzing…",
    "✦ 重新分析": "✦ Reanalyze", "✦ 重新对齐": "✦ Realign", "✦ 更新歌词": "✦ Update lyrics", "✦ 继续分析": "✦ Resume analysis",
    "没有匹配的歌曲": "No songs match", "导入的歌曲会保存在这里，<br>随时回来继续探索。": "Imported songs stay here.<br>Come back whenever you like.",
    "公开授权示例": "Licensed demo", "正在停止，已完成的阶段会保留…": "Stopping; completed stages will be kept…",
    "段": "chunks", "已用时": "Elapsed", "更新歌词与时间": "Update lyrics and timing", "分析": "Analysis",
    "本次更新未完成，之前的结果仍可试听。可展开诊断信息，调整设置后重试。": "The update failed. Previous results still play. Check diagnostics, adjust settings and retry.",
    "请重新导入有效音频。": "Import a valid audio file again.", "自动估计": "Machine estimates",
    "更新分析与歌词": "Update analysis and lyrics", "设置语言与设备，然后开始分析": "Choose song language and device, then analyze",
    "正在载入试听音轨…": "Loading audio…", "试听：原曲 · 空格播放 / 暂停": "Listening: Original · Space to play / pause",
    "音轨载入失败，可重新选择项目": "Audio could not load. Select the song again.",
    "尚无可靠词级时间，按句定位": "No reliable word timing; seeks to the line", "（空白歌词）": "(empty line)",
    "提示用于安排试听": "Hints help prioritize listening",
    "未标记的歌词也可能有误；时间缺失与文字错误分别处理。": "Unmarked lyrics can also be wrong. Missing timing and text errors are separate.",
    "✓ 已核对": "✓ Reviewed", "文字仍完整保留；部分词只有句级定位，不代表文字识别错误": "All text is retained. Some words only have line timing; this does not imply incorrect text.",
    "已修改": "Edited", "修改歌词文字": "Edit lyric text", "当前筛选下没有待处理的歌词": "No lines to review in this filter",
    "没有识别到可用歌词": "No usable lyrics recognized", "核对标记不代表模型正确率。": "Review markers do not measure model accuracy.",
    "正在导入音频…": "Importing audio…", "音频已就绪，点击「开始分析」。": "Audio is ready. Choose Analyze song.",
    "和弦": "Chords", "旋律": "Melody", "移入回收站": "Move to Trash", "恢复": "Restore",
    "回收站是空的": "Trash is empty", "删除的歌曲可以从这里找回。": "Restore deleted songs from here.",
    "当前筛选下没有尚待核对的歌词。核对记录不会改变实际词时间。": "No pending lines in this filter. Review markers do not change word timing.",
    "请先保存修改，再标记已核对。": "Save your changes before marking this line as reviewed.",
    "已记录试听核对，实际词时间保持原样": "Review saved; word timing is unchanged", "已取消核对标记": "Review marker removed",
    "该候选已经处理，可在结果版本中查看": "This candidate was already processed. Check result versions.",
    "原版本已切换，请切回原版本查看候选，或重新生成": "The base version changed. Switch back to review this candidate, or generate another.",
    "正在使用": "Currently active", "候选": "Candidate", "♫ 试听原音频": "♫ Listen to original audio",
    "间奏 · 等待下一句": "Instrumental break · waiting for the next line",
    "点击歌词可定位 · 灰色文字只有句级时间": "Click lyrics to seek · gray text has line timing only",
    "已采用候选版本，原版本可随时切回": "Candidate accepted. You can switch back at any time.",
    "当前结果已更新，请重新打开歌曲后再编辑。": "Results changed. Reopen this song before editing.",
    "取消已核对": "Remove review marker", "已恢复识别原文": "Original recognition restored",
    "歌词已保存，导出文件已同步更新": "Lyrics saved and exports updated", "歌曲名称已保存": "Song name saved",
    "请先保存当前修改，再重新识别这一句。": "Save your changes before recognizing this line again.",
    "正在生成候选，完成后可试听比较；原版本继续保留": "Generating a candidate for comparison. The original version is kept.",
    "用户提供歌词": "User-provided lyrics", "已纠正歌词": "Corrected lyrics", "单句更新": "Line retry",
    "歌词更新": "Lyrics update", "纠词后对齐": "Align corrections", "提供歌词对齐": "Align supplied lyrics",
    "单句重识别": "Line recognition", "待确认候选 · ": "Pending candidate · ", "首次分析": "Initial analysis",
    "未记录修订版": "revision not recorded", "双模型声学锚点": "Dual acoustic guides", "声学锚点对齐": "Acoustic guides",
    "灰色字按句定位": "gray text has line timing", "独立时间对齐 · 部分句子需核对": "Forced alignment · some lines need review",
    "独立时间对齐": "Forced alignment", "分段时间 · 尚无可靠逐词时间": "Phrase timing · no reliable word timing",
    "模型自带时间 · 可重新对齐": "Native timing · can be realigned",
    "已切换结果版本，歌词修改随版本恢复": "Version switched with its saved lyric corrections",
    "歌曲已切换，请重新打开歌词导入。": "The song changed. Reopen lyric import.",
    "开始对齐提供的歌词，原结果已保留": "Aligning supplied lyrics. Previous results are kept.",
    "正在载入版本差异…": "Loading differences…", "两版文字相同；可分别试听核对时间位置。": "The text is identical. Listen to check timing in each version.",
    "此版本没有歌词": "This version has no lyrics", "CPU · 模型在本机运行": "CPU · models run locally",
    "当前本地服务仍是旧版。更新代码后需重启服务，才能使用重新分析与版本管理。": "The local server is outdated. Restart it to use reanalysis and version history.",
    "音轨载入失败，请再次点击音轨重试": "Audio could not load. Click the track to retry.",
    "请求失败（{status}）": "Request failed ({status})", "删除歌曲 {title}": "Delete song {title}",
    "「{stage}」未完成。检查模型与设备后可继续分析。": "{stage} failed. Check your models and device, then resume.",
    "{count} 句已修改": "{count} lines edited", "文字提示 {text} · 待定位 {timing} · 已核对 {reviewed}": "Text {text} · untimed {timing} · reviewed {reviewed}",
    "跳转到第 {line} 句歌词，{time}": "Seek to lyric line {line}, {time}", "编辑第 {line} 句歌词": "Edit lyric line {line}",
    "正在载入{track}，当前播放继续…": "Loading {track}; playback continues…",
    "试听：{track} · 空格播放 / 暂停": "Listening: {track} · Space to play / pause",
    "{track}载入失败，点击音轨可重试 · 当前试听：{current}": "Could not load {track}; click to retry · listening: {current}",
    "「{title}」已移入回收站": "Moved “{title}” to Trash", "「{title}」已恢复": "Restored “{title}”",
    "修改第 {line} 句歌词": "Edit lyric line {line}", "{count}句纠词": "{count} lines edited",
    "{count}处文字变化 · 点击时间试听": "{count} text changes · click a time to listen", "试听{time}": "Listen at {time}",
    "正在载入授权示例…": "Loading the licensed demo…",
    "示例已就绪，无需模型即可试听、纠词和导出。分析自己的歌曲需安装推理依赖与模型。": "Demo ready. Listen, correct lyrics and export without models. Analyzing your own songs requires inference dependencies and model weights.",
    "示例音频已就绪，请开始分析。免模型示例需要重启更新后的服务。": "Demo audio is ready for analysis. Restart the updated server to use the no-model demo.",
    "项目不存在": "Song project not found", "歌曲名称不能为空，也不能包含换行或控制字符": "Enter a song name without newlines or control characters",
    "请先停止当前分析，再删除歌曲": "Stop analysis before deleting this song", "回收站路径无效": "Invalid Trash path",
    "回收站中已有相同项目": "This song is already in Trash", "工作区已有相同项目": "This song is already in the workspace",
    "请选择 WAV、MP3、FLAC、M4A 或 OGG 等音频文件": "Choose an audio file such as WAV, MP3, FLAC, M4A or OGG",
    "服务正在关闭": "The server is shutting down", "已有歌曲正在分析，请完成或停止后再试": "Another song is being analyzed. Wait or stop it first.",
    "当前分析版本已切换，请刷新后再试": "The result version changed. Refresh and retry.",
    "请先完成整曲分析，再更新歌词": "Complete full analysis before updating lyrics", "识别候选只适用于单句重识别": "Candidates are available for single-line recognition only",
    "对齐任务必须指定歌词所属的版本": "Alignment requires the lyric version", "歌词已更新，请刷新后再对齐": "Lyrics changed. Refresh before aligning.",
    "要重新识别的歌词句不存在": "The lyric line to recognize no longer exists", "仅接受本地界面的请求": "Only local UI requests are accepted",
    "单个音频文件最大 512MB": "Audio files must be 512MB or smaller", "音频文件为空": "The audio file is empty",
    "文件导入失败，请重新选择音频": "Import failed. Choose the audio file again.", "分析完成后可查看结果": "Results are available after analysis",
    "请等待分析完成或先停止，再切换版本": "Finish or stop analysis before switching versions",
    "版本已在其他窗口切换，请刷新后再试": "The version changed in another window. Refresh and retry.",
    "原歌词或版本已改变，请重新生成候选，避免覆盖新修改": "The base lyrics or version changed. Generate a new candidate to preserve recent edits.",
    "当前版本已改变，请重新打开歌词后核对": "The version changed. Reopen the lyrics before reviewing.",
    "歌词已在其他窗口更新，请刷新后核对": "Lyrics changed in another window. Refresh before reviewing.",
    "歌词句不存在": "Lyric line not found", "当前版本已改变，修改未写入其他版本，请重新打开歌词编辑": "The version changed. Your edit was not applied to another version. Reopen the editor.",
    "歌词已在其他窗口更新，请重新打开后再编辑": "Lyrics changed in another window. Reopen the editor.",
    "每句最多 1000 字，请勿包含换行或控制字符": "Each line allows up to 1000 characters without newlines or control characters",
    "文件不存在": "File not found", "分析版本不存在": "Result version not found",
    "上次分析已中断，可以继续分析。": "The previous analysis was interrupted. You can resume it.",
    "未安装推理依赖，请先运行 scripts/setup.ps1 -Mode full，或参阅 README。": "Inference dependencies are missing. Run scripts/setup.ps1 -Mode full, or see the README.",
    "体验示例 · 预计算结果": "Demo · precomputed estimates",
    "体验模式：分析自己的歌曲需要安装模型": "Preview runtime: install models to analyze your own songs",
    "内置示例可直接使用。完整分析需安装推理组件并下载模型；GPU 与 CPU 可选。": "The bundled demo is ready. Full analysis requires inference dependencies and model downloads. GPU and CPU setups are available.",
    "没有 NVIDIA 显卡时，将 cuda 改为 cpu。安装后重启软件。": "Without an NVIDIA GPU, replace cuda with cpu. Restart the app after installation.",
    "当前歌曲没有可循环的歌词句，可以拖动进度条试听。": "There are no lyric lines to loop. Use the seek bar to listen.",
    "部分字词的识别分数偏低，建议试听核对": "Some words have low recognition scores. Listen to check them.",
    "识别歌词片段": "Recognizing lyric chunks", "歌词识别完成，准备校准时间": "Lyrics recognized; preparing alignment",
    "秒": "sec", "人声音轨": "Vocals audio", "伴奏音轨": "Backing audio",
    "识别声学时间锚点": "Recognizing acoustic timing guides", "补充声学时间锚点": "Adding acoustic timing guides",
    "校准歌词时间": "Aligning lyric timing",
    "{mode} · 无需账号，本地处理": "{mode} · no account, local processing"
  };

  function normalize(value) { return String(value || "").toLowerCase().startsWith("zh") ? "zh" : "en"; }
  function create({storage, browserLanguage = "en", onChange = () => {}} = {}) {
    let saved;
    try { saved = storage?.getItem("music-studio.ui-language"); } catch (_) {}
    let language = saved === "zh" || saved === "en" ? saved : normalize(browserLanguage);
    const rendered = new Map();
    const t = (key, values = {}) => {
      const text = (language === "en" ? en[key] ?? key : key)
        .replace(/\{(\w+)\}/g, (match, name) => Object.hasOwn(values, name) ? String(values[name]) : match);
      if (Object.hasOwn(en, key)) {
        if (rendered.size > 512) rendered.delete(rendered.keys().next().value);
        rendered.set(text, {key, values});
      }
      return text;
    };
    return {
      t, retranslate(text) { const item = rendered.get(text); return item ? t(item.key, item.values) : t(text); },
      get language() { return language; }, get locale() { return language === "zh" ? "zh-CN" : "en-US"; },
      setLanguage(value) {
        const next = normalize(value);
        if (next === language) return;
        language = next;
        try { storage?.setItem("music-studio.ui-language", language); } catch (_) {}
        onChange(language);
      }
    };
  }

  // Capture only the trusted HTML shell, before app.js renders any song or lyrics.
  // Disconnected nodes are ignored; dynamic UI uses t() explicitly.
  function bindShell(doc, i18n) {
    const bindings = [], walker = doc.createTreeWalker(doc.documentElement, 4);
    let node;
    while ((node = walker.nextNode())) {
      const key = node.nodeValue.trim();
      if (Object.hasOwn(en, key) && !node.parentElement.closest("script,style,#ui-language")) {
        const leading = node.nodeValue.match(/^\s*/)[0], trailing = node.nodeValue.match(/\s*$/)[0];
        bindings.push(() => { if (nodeRef.isConnected) nodeRef.nodeValue = leading + i18n.t(key) + trailing; });
        const nodeRef = node;
      }
    }
    for (const element of doc.querySelectorAll("[aria-label],[title],[placeholder]")) {
      for (const attr of ["aria-label", "title", "placeholder"]) {
        const key = element.getAttribute(attr);
        if (Object.hasOwn(en, key)) bindings.push(() => { if (element.isConnected) element.setAttribute(attr, i18n.t(key)); });
      }
    }
    return () => {
      doc.documentElement.lang = i18n.locale;
      bindings.forEach(apply => apply());
      const picker = doc.querySelector("#ui-language");
      if (picker) picker.value = i18n.language;
    };
  }
  if (typeof module === "object" && module.exports) module.exports = {en, normalize, create, bindShell};
  else {
    let storage;
    try { storage = root.localStorage; } catch (_) {}
    const i18n = create({storage, browserLanguage: root.navigator.language,
      onChange() { applyShell(); root.dispatchEvent(new Event("music-language-change")); }});
    const applyShell = bindShell(root.document, i18n);
    applyShell();
    root.MusicI18n = i18n;
  }
})(typeof window === "object" ? window : globalThis);
