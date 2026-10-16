import "./effects-dsp.js";

class StudioEffects extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const { settings, master } = options.processorOptions;
    this.processor = master
      ? new StationEffects.OutputLimiter(settings, sampleRate)
      : new StationEffects.Rack(settings, sampleRate);
    this.count = 0;
    this.port.onmessage = (event) => {
      if (event.data.dispose) {
        this.disposed = true;
        this.port.close();
      } else this.processor.configure(event.data);
    };
  }
  process(inputs, outputs) {
    if (this.disposed) return false;
    const output = outputs[0];
    this.processor.process(
      inputs[0]?.[0],
      inputs[0]?.[1],
      output[0],
      output[1],
    );
    if (++this.count % 16 === 0)
      this.port.postMessage({
        reduction: this.processor.reduction,
        peak: this.processor.peak || 0,
      });
    return true;
  }
}
registerProcessor("studio-effects", StudioEffects);
