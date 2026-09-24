/**
 * Live microphone playback for one camera.
 *
 * Browsers refuse to decode an open-ended streaming WAV through an <audio>
 * element (the demuxer waits forever for a real file length), so we read the
 * PCM ourselves and schedule it through Web Audio instead. That also gives us
 * exact control: stopping is instant, and only one camera is ever audible.
 */

const WAV_HEADER_BYTES = 44;
/** how far ahead of the clock we schedule; small = low latency, big = safer */
const LEAD_SECONDS = 0.25;
/** if we drift more than this behind/ahead, resync rather than accumulate lag */
const MAX_DRIFT_SECONDS = 1.0;

export class LiveAudioPlayer {
  private ctx: AudioContext | null = null;
  private abort: AbortController | null = null;
  private nextTime = 0;
  private stopped = false;

  constructor(private readonly url: string) {}

  /** Begins playback. Must be called from a user gesture (button click). */
  async start(onError?: (message: string) => void): Promise<void> {
    this.stopped = false;
    this.abort = new AbortController();

    try {
      const AudioCtor: typeof AudioContext =
        window.AudioContext || (window as any).webkitAudioContext;
      this.ctx = new AudioCtor();
      // browsers start contexts suspended until a gesture resumes them
      if (this.ctx.state === 'suspended') await this.ctx.resume();

      const resp = await fetch(this.url, { signal: this.abort.signal, mode: 'cors' });
      if (!resp.ok || !resp.body) {
        throw new Error(resp.status === 404
          ? 'This camera has no microphone mapped'
          : `Audio stream returned ${resp.status}`);
      }

      const reader = resp.body.getReader();
      let pending = new Uint8Array(0);
      let sampleRate = 44100;
      let headerParsed = false;

      this.nextTime = this.ctx.currentTime + LEAD_SECONDS;

      while (!this.stopped) {
        const { done, value } = await reader.read();
        if (done) break;
        if (!value?.length) continue;

        pending = concat(pending, value);

        if (!headerParsed) {
          if (pending.length < WAV_HEADER_BYTES) continue;
          const view = new DataView(pending.buffer, pending.byteOffset);
          sampleRate = view.getUint32(24, true) || 44100;
          pending = pending.slice(WAV_HEADER_BYTES);
          headerParsed = true;
        }

        // int16 samples: keep any trailing odd byte for the next chunk
        const usable = pending.length - (pending.length % 2);
        if (usable <= 0) continue;
        const samples = new Int16Array(pending.buffer.slice(pending.byteOffset, pending.byteOffset + usable));
        pending = pending.slice(usable);

        this.schedule(samples, sampleRate);
      }
    } catch (e: any) {
      if (e?.name !== 'AbortError' && !this.stopped) {
        onError?.(e?.message || 'Audio stream failed');
      }
    } finally {
      this.stop();
    }
  }

  private schedule(samples: Int16Array, sampleRate: number): void {
    const ctx = this.ctx;
    if (!ctx || this.stopped || samples.length === 0) return;

    const float = new Float32Array(samples.length);
    for (let i = 0; i < samples.length; i++) float[i] = samples[i] / 32768;

    // Web Audio resamples buffers whose rate differs from the context's.
    const buffer = ctx.createBuffer(1, float.length, sampleRate);
    buffer.copyToChannel(float, 0);

    const src = ctx.createBufferSource();
    src.buffer = buffer;
    src.connect(ctx.destination);

    const now = ctx.currentTime;
    // resync if we've fallen behind (tab throttling) or run too far ahead
    if (this.nextTime < now || this.nextTime - now > MAX_DRIFT_SECONDS) {
      this.nextTime = now + LEAD_SECONDS;
    }
    src.start(this.nextTime);
    this.nextTime += buffer.duration;
  }

  /** Stops playback and closes the network stream immediately. */
  stop(): void {
    if (this.stopped) return;
    this.stopped = true;
    try { this.abort?.abort(); } catch { /* already gone */ }
    this.abort = null;
    const ctx = this.ctx;
    this.ctx = null;
    if (ctx && ctx.state !== 'closed') {
      ctx.close().catch(() => { /* nothing to do */ });
    }
  }
}

function concat(a: Uint8Array, b: Uint8Array): Uint8Array {
  if (a.length === 0) return b;
  const out = new Uint8Array(a.length + b.length);
  out.set(a, 0);
  out.set(b, a.length);
  return out;
}
