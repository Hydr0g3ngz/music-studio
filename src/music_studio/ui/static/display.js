/* Fullscreen changes only the window; project, playback and editors stay alive. */
(function (root) {
  "use strict";
  function create({doc, host, translate, onError = () => {}}) {
    let fullscreen = false;
    const button = doc.getElementById("fullscreen-button");
    const label = doc.getElementById("fullscreen-label");
    function render() {
      doc.documentElement.classList.toggle("is-fullscreen", fullscreen);
      button.setAttribute("aria-pressed", String(fullscreen));
      button.setAttribute("aria-label", translate(fullscreen ? "退出全屏" : "全屏"));
      button.title = translate(fullscreen ? "退出全屏（Esc / F11）" : "全屏（F11）");
      label.textContent = translate(fullscreen ? "退出全屏" : "全屏");
    }
    async function toggle() {
      try {
        if (host) host.postMessage({type: "studio-fullscreen", action: "toggle"});
        else if (doc.fullscreenElement) await doc.exitFullscreen();
        else await doc.documentElement.requestFullscreen();
      } catch (_) { onError(translate("暂时无法进入全屏，请重试或使用 F11。")); }
    }
    function browserChanged() { fullscreen = !!doc.fullscreenElement; render(); }
    function hostChanged(event) {
      if (event.data?.type !== "studio-window-state") return;
      fullscreen = event.data.fullscreen === true;
      render();
    }
    button.onclick = toggle;
    doc.addEventListener("fullscreenchange", browserChanged);
    if (host) {
      host.addEventListener("message", hostChanged);
      host.postMessage({type: "studio-window-state"});
    }
    render();
    return {toggle, render};
  }
  if (typeof module === "object" && module.exports) module.exports = {create};
  if (root.document) {
    const controller = create({doc: root.document,
      host: root.__MusicStudioDesktop?.windowControls ? root.chrome?.webview : null,
      translate: text => root.MusicI18n.t(text),
      onError: text => { const node = root.document.getElementById("notice");
        node.textContent = text; node.hidden = false; }
    });
    root.addEventListener("music-language-change", controller.render);
  }
})(typeof window !== "undefined" ? window : globalThis);
