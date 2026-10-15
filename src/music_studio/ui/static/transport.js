/* Immutable asset identity controls media loading. Rendering UI must not reset playback. */
(function (root) {
  "use strict";
  class AudioAssetTransport {
    constructor(audio) {
      this.audio = audio;
      this.key = null;
    }
    bind(key, url, { retry = false } = {}) {
      if (key === this.key && !retry) return false;
      this.audio.pause();
      this.audio.src = url;
      this.audio.load();
      this.key = key;
      return true;
    }
    clear() {
      this.audio.pause();
      this.audio.removeAttribute("src");
      this.audio.load();
      this.key = null;
    }
  }
  if (typeof module !== "undefined" && module.exports)
    module.exports = { AudioAssetTransport };
  else root.AudioAssetTransport = AudioAssetTransport;
})(typeof window !== "undefined" ? window : globalThis);
