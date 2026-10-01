class NanviPcmCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.frameSize = 2048;
    this.frame = new Float32Array(this.frameSize);
    this.offset = 0;
  }

  process(inputs) {
    const channel = inputs[0]?.[0];
    if (!channel) return true;

    let readOffset = 0;
    while (readOffset < channel.length) {
      const count = Math.min(this.frameSize - this.offset, channel.length - readOffset);
      this.frame.set(channel.subarray(readOffset, readOffset + count), this.offset);
      this.offset += count;
      readOffset += count;

      if (this.offset === this.frameSize) {
        const completeFrame = this.frame;
        this.frame = new Float32Array(this.frameSize);
        this.offset = 0;
        this.port.postMessage(completeFrame, [completeFrame.buffer]);
      }
    }

    return true;
  }
}

registerProcessor("nanvi-pcm-capture", NanviPcmCaptureProcessor);
