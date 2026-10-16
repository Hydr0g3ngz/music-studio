(function (root) {
  "use strict";
  const defaults = () => ({
    bypass: false,
    eq: { enabled: false, low_db: 0, mid_db: 0, high_db: 0 },
    compressor: {
      enabled: false,
      threshold_db: -18,
      ratio: 3,
      attack_ms: 10,
      release_ms: 150,
      makeup_db: 0,
    },
    reverb: { enabled: false, mix: 0.15, decay: 1.2 },
  });
  const limiterDefaults = () => ({
    enabled: false,
    ceiling_db: -1,
    release_ms: 80,
  });
  function normalize(settings = {}) {
    const base = defaults();
    return {
      bypass: !!settings.bypass,
      eq: { ...base.eq, ...settings.eq },
      compressor: { ...base.compressor, ...settings.compressor },
      reverb: { ...base.reverb, ...settings.reverb },
    };
  }
  function tail(settings) {
    const s = normalize(settings);
    return s.bypass
      ? 0
      : Math.max(
          s.eq.enabled ? 0.15 : 0,
          s.reverb.enabled && s.reverb.mix > 0 ? s.reverb.decay + 0.1 : 0,
        );
  }
  function coefficients(kind, db, rate) {
    const a = 10 ** (db / 40),
      w = (2 * Math.PI * { low: 150, mid: 1000, high: 4000 }[kind]) / rate,
      c = Math.cos(w),
      alpha = Math.sin(w) / Math.SQRT2,
      beta = 2 * Math.sqrt(a) * alpha;
    let b, d;
    if (kind === "mid") {
      b = [1 + alpha * a, -2 * c, 1 - alpha * a];
      d = [1 + alpha / a, -2 * c, 1 - alpha / a];
    } else if (kind === "low") {
      b = [
        a * (a + 1 - (a - 1) * c + beta),
        2 * a * (a - 1 - (a + 1) * c),
        a * (a + 1 - (a - 1) * c - beta),
      ];
      d = [
        a + 1 + (a - 1) * c + beta,
        -2 * (a - 1 + (a + 1) * c),
        a + 1 + (a - 1) * c - beta,
      ];
    } else {
      b = [
        a * (a + 1 + (a - 1) * c + beta),
        -2 * a * (a - 1 + (a + 1) * c),
        a * (a + 1 + (a - 1) * c - beta),
      ];
      d = [
        a + 1 - (a - 1) * c + beta,
        2 * (a - 1 - (a + 1) * c),
        a + 1 - (a - 1) * c - beta,
      ];
    }
    return [...b, ...d].map((x) => x / d[0]);
  }
  class Delay {
    constructor(length) {
      this.data = new Float64Array(length);
      this.at = 0;
    }
    tick(x, feedback, allpass = false) {
      const old = this.data[this.at],
        y = allpass ? old - feedback * x : old;
      this.data[this.at] = x + feedback * (allpass ? y : old);
      this.at = (this.at + 1) % this.data.length;
      return y;
    }
  }
  class Rack {
    constructor(settings, rate = 44100) {
      this.rate = rate;
      this.state = Array.from({ length: 3 }, () => [
        new Float64Array(2),
        new Float64Array(2),
      ]);
      this.held = this.smooth = this.reduction = 0;
      this.combs = [0, 1].map((ch) =>
        [0.0297, 0.0371, 0.0411, 0.0437].map(
          (d) => new Delay(Math.round((d + ch * 0.0011) * rate)),
        ),
      );
      this.allpasses = [0, 1].map(() =>
        [0.005, 0.0017].map((d) => new Delay(Math.round(d * rate))),
      );
      this.configure(settings);
      this.wet = this.settings.bypass ? 0 : 1;
    }
    configure(settings) {
      this.settings = normalize(settings);
      this.sos = ["low", "mid", "high"].map((k) =>
        coefficients(k, this.settings.eq[k + "_db"], this.rate),
      );
      const c = this.settings.compressor;
      this.release = Math.exp(-1 / ((this.rate * c.release_ms) / 1000));
      this.attack = Math.exp(-1 / ((this.rate * c.attack_ms) / 1000));
      this.feedbacks = this.combs.map((combs) =>
        combs.map(
          (d) =>
            10 **
            ((-3 * d.data.length) / (this.rate * this.settings.reverb.decay)),
        ),
      );
    }
    process(left, right, outLeft, outRight) {
      const s = this.settings,
        c = s.compressor,
        r = s.reverb;
      this.reduction = 0;
      for (let i = 0; i < outLeft.length; i++) {
        let l = left?.[i] || 0,
          rr = right?.[i] ?? l;
        const dryL = l,
          dryR = rr;
        if (s.eq.enabled) {
          for (let band = 0; band < 3; band++) {
            const [b0, b1, b2, , a1, a2] = this.sos[band],
              [ls, rs] = this.state[band];
            const yl = b0 * l + ls[0],
              yr = b0 * rr + rs[0];
            ls[0] = b1 * l - a1 * yl + ls[1];
            ls[1] = b2 * l - a2 * yl;
            rs[0] = b1 * rr - a1 * yr + rs[1];
            rs[1] = b2 * rr - a2 * yr;
            l = yl;
            rr = yr;
          }
        }
        if (c.enabled) {
          this.held = Math.max(
            Math.abs(l),
            Math.abs(rr),
            this.held * this.release,
          );
          this.smooth =
            (1 - this.attack) * this.held + this.attack * this.smooth;
          const reduction =
            Math.max(
              0,
              20 * Math.log10(Math.max(this.smooth, 1e-12)) - c.threshold_db,
            ) *
            (1 - 1 / c.ratio);
          const g = 10 ** ((c.makeup_db - reduction) / 20);
          l *= g;
          rr *= g;
          if (!s.bypass) this.reduction = Math.max(this.reduction, reduction);
        }
        if (r.enabled && r.mix > 0) {
          let wetL = 0,
            wetR = 0;
          for (let k = 0; k < 4; k++) {
            wetL += this.combs[0][k].tick(l, this.feedbacks[0][k]) * 0.25;
            wetR += this.combs[1][k].tick(rr, this.feedbacks[1][k]) * 0.25;
          }
          for (let k = 0; k < 2; k++) {
            wetL = this.allpasses[0][k].tick(wetL, 0.5, true);
            wetR = this.allpasses[1][k].tick(wetR, 0.5, true);
          }
          l = l * (1 - r.mix) + wetL * r.mix;
          rr = rr * (1 - r.mix) + wetR * r.mix;
        }
        // A/B changes do not jump between unrelated waveforms in a single sample.
        const target = s.bypass ? 0 : 1,
          step = 1 / (this.rate * 0.015);
        this.wet += Math.max(-step, Math.min(step, target - this.wet));
        outLeft[i] = dryL + (l - dryL) * this.wet;
        outRight[i] = dryR + (rr - dryR) * this.wet;
      }
    }
  }
  class OutputLimiter {
    constructor(settings, rate = 44100) {
      this.rate = rate;
      this.held = this.reduction = 0;
      this.configure(settings);
    }
    configure(settings) {
      this.settings = { ...limiterDefaults(), ...settings };
      this.ceiling = 10 ** (this.settings.ceiling_db / 20);
      this.release = Math.exp(
        -1 / ((this.rate * this.settings.release_ms) / 1000),
      );
    }
    process(left, right, outLeft, outRight) {
      this.reduction = 0;
      this.peak = 0;
      for (let i = 0; i < outLeft.length; i++) {
        const l = left?.[i] || 0,
          r = right?.[i] ?? l;
        this.held = Math.max(
          Math.abs(l),
          Math.abs(r),
          this.held * this.release,
        );
        const g = this.settings.enabled
          ? Math.min(1, this.ceiling / Math.max(this.held, 1e-12))
          : 1;
        outLeft[i] = l * g;
        outRight[i] = r * g;
        this.peak = Math.max(
          this.peak,
          Math.abs(outLeft[i]),
          Math.abs(outRight[i]),
        );
        this.reduction = Math.max(this.reduction, -20 * Math.log10(g));
      }
    }
  }
  const presets = {
    clean: {
      title: ["清晰人声", "Clear voice"],
      settings: {
        eq: { enabled: true, low_db: -3, mid_db: 1, high_db: 2 },
        compressor: {
          enabled: true,
          threshold_db: -20,
          ratio: 3,
          makeup_db: 1,
        },
        reverb: { enabled: true, mix: 0.08, decay: 0.6 },
      },
    },
    warm: {
      title: ["温暖键盘", "Warm keys"],
      settings: {
        eq: { enabled: true, low_db: 2, mid_db: -1, high_db: -2 },
        compressor: { enabled: true, threshold_db: -18, ratio: 2 },
        reverb: { enabled: true, mix: 0.18, decay: 1.3 },
      },
    },
    drums: {
      title: ["紧实鼓组", "Tight drums"],
      settings: {
        eq: { enabled: true, low_db: 2, mid_db: -2, high_db: 1 },
        compressor: {
          enabled: true,
          threshold_db: -16,
          ratio: 4,
          attack_ms: 20,
          release_ms: 80,
          makeup_db: 1,
        },
      },
    },
    space: {
      title: ["氛围空间", "Ambient space"],
      settings: {
        eq: { enabled: true, low_db: -2, high_db: -1 },
        reverb: { enabled: true, mix: 0.32, decay: 2.5 },
      },
    },
  };
  const api = {
    defaults,
    limiterDefaults,
    normalize,
    tail,
    coefficients,
    Rack,
    OutputLimiter,
    presets,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.StationEffects = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
