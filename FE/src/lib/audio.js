// Capture PCM rather than MediaRecorder WebM: BE accepts WAV PCM16 or raw PCM16.
export async function captureAudio(stream) {
  const AudioContext = window.AudioContext || window.webkitAudioContext;
  if (!AudioContext) throw new Error("Trình duyệt không hỗ trợ thu âm WAV.");
  const context = new AudioContext();
  await context.resume();
  const source = context.createMediaStreamSource(stream);
  const processor = context.createScriptProcessor(4096, 1, 1);
  const chunks = [];
  let length = 0;
  processor.onaudioprocess = ({ inputBuffer }) => {
    const chunk = new Float32Array(inputBuffer.getChannelData(0));
    chunks.push(chunk);
    length += chunk.length;
  };
  source.connect(processor);
  processor.connect(context.destination);
  return () => {
    processor.disconnect();
    source.disconnect();
    void context.close();
    const data = new DataView(new ArrayBuffer(44 + length * 2));
    const text = (offset, value) =>
      [...value].forEach((c, i) => data.setUint8(offset + i, c.charCodeAt(0)));
    text(0, "RIFF");
    data.setUint32(4, 36 + length * 2, true);
    text(8, "WAVE");
    text(12, "fmt ");
    data.setUint32(16, 16, true);
    data.setUint16(20, 1, true);
    data.setUint16(22, 1, true);
    data.setUint32(24, context.sampleRate, true);
    data.setUint32(28, context.sampleRate * 2, true);
    data.setUint16(32, 2, true);
    data.setUint16(34, 16, true);
    text(36, "data");
    data.setUint32(40, length * 2, true);
    let offset = 44;
    for (const chunk of chunks)
      for (const sample of chunk) {
        const value = Math.max(-1, Math.min(1, sample));
        data.setInt16(offset, value * (value < 0 ? 32768 : 32767), true);
        offset += 2;
      }
    return new Blob([data.buffer], { type: "audio/wav" });
  };
}
