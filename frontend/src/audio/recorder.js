// ============ VOICE RECORDER ============
// Web Audio API + MediaRecorder + VAD
//
// story-6 行为约定（改动前必读）：
// - 上限用 deadline（可 extend），到限触发 onLimitReached 由 UI 询问
//   "继续/结束"——不再静默截断；调用方未提供 onLimitReached 时回退为自动停止
//   （leftPanel 等旧调用保持原行为）。
// - 静默只提醒不截断：越过 silenceTimeout 调一次 onSilence（每次静默段仅一次），
//   老人停顿思考不会被打断（60 秒日课的停顿是常态，不是结束信号）。
// - onError 回调参数是 Error 对象（调用方按 err.name 区分 NotAllowedError 等），
//   不再是字符串。

export class VoiceRecorder {
  constructor(options = {}) {
    this.mediaRecorder = null;
    this.audioChunks = [];
    this.stream = null;
    this.analyser = null;
    this.audioContext = null;
    this.isRecording = false;
    this.silenceStart = null;
    this.options = {
      minDuration: options.minDuration || 3000,     // 最少 3 秒
      maxDuration: options.maxDuration || 120000,     // 最多 2 分钟
      silenceTimeout: options.silenceTimeout || 3000,   // 静默提醒阈值（不再自动停）
      sampleRate: options.sampleRate || 16000,
    };
    this.onStart = null;
    this.onStop = null;
    this.onData = null;
    this.onError = null;
    this.onTick = null;          // (remainingMs) 每秒一次，驱动计时显示
    this.onSilence = null;       // 静默超过阈值时一次（每次静默段）
    this.onLimitReached = null;  // 到达上限：询问用户，不自动停
    this._deadline = null;
    this._limitAsked = false;
    this._lastTickSec = null;
    this._inSilence = false;
  }

  async start() {
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: this.options.sampleRate,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        }
      });

      // AudioContext for VAD
      this.audioContext = new AudioContext({ sampleRate: this.options.sampleRate });
      const source = this.audioContext.createMediaStreamSource(this.stream);
      this.analyser = this.audioContext.createAnalyser();
      this.analyser.fftSize = 256;
      source.connect(this.analyser);

      // MediaRecorder
      this.mediaRecorder = new MediaRecorder(this.stream, {
        mimeType: MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : 'audio/mp4',
      });

      this.mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) this.audioChunks.push(e.data);
      };

      this.mediaRecorder.onstop = () => {
        this._cleanup();
        const blob = new Blob(this.audioChunks, { type: this.mediaRecorder.mimeType });
        if (this.onStop) this.onStop(blob);
      };

      this.mediaRecorder.onerror = (e) => {
        this._cleanup();
        if (this.onError) this.onError(e && e.error ? e.error : e);
      };

      this.audioChunks = [];
      this._startTime = Date.now();
      this._deadline = Date.now() + this.options.maxDuration;
      this._limitAsked = false;
      this.mediaRecorder.start(100); // 每 100ms 收集一次
      this.isRecording = true;

      // VAD loop（同时驱动 tick / silence / limit 检查）
      this._vadLoop();

      if (this.onStart) this.onStart();

    } catch (err) {
      if (this.onError) this.onError(err);
    }
  }

  stop() {
    if (!this.isRecording) return;
    this.isRecording = false;
    if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
      this.mediaRecorder.stop();
    }
  }

  // 用户选择"再说一会儿"：延长截止时间，重置到限询问标记
  extend(ms) {
    if (this._deadline) this._deadline += ms;
    this._limitAsked = false;
  }

  _vadLoop() {
    if (!this.isRecording) return;

    const now = Date.now();
    const remaining = this._deadline ? this._deadline - now : Infinity;

    // 每秒回调一次计时
    if (this.onTick) {
      const sec = Math.max(0, Math.ceil(remaining / 1000));
      if (sec !== this._lastTickSec) {
        this._lastTickSec = sec;
        this.onTick(remaining > 0 ? remaining : 0, now - this._startTime);
      }
    }

    // 到达上限：交给 UI 询问；无询问处理器才自动停（兼容旧调用方）
    if (remaining <= 0 && !this._limitAsked) {
      if (this.onLimitReached) {
        this._limitAsked = true;
        this.onLimitReached();
      } else {
        this.stop();
        return;
      }
    }

    const dataArray = new Uint8Array(this.analyser.frequencyBinCount);
    this.analyser.getByteFrequencyData(dataArray);

    // Calculate RMS energy
    let sum = 0;
    for (let i = 0; i < dataArray.length; i++) {
      sum += (dataArray[i] / 255) ** 2;
    }
    const rms = Math.sqrt(sum / dataArray.length);

    // Silence detection (RMS < 0.02)：只提醒，不截断
    if (rms < 0.02) {
      if (!this.silenceStart) {
        this.silenceStart = Date.now();
      } else if (!this._inSilence &&
                 Date.now() - this.silenceStart > this.options.silenceTimeout &&
                 this._getRecordingDuration() >= this.options.minDuration) {
        this._inSilence = true;
        if (this.onSilence) this.onSilence();
      }
    } else {
      this.silenceStart = null;
      this._inSilence = false;
    }

    requestAnimationFrame(() => this._vadLoop());
  }

  _getRecordingDuration() {
    if (!this._startTime) return 0;
    return Date.now() - this._startTime;
  }

  _cleanup() {
    if (this.stream) {
      this.stream.getTracks().forEach(track => track.stop());
    }
    if (this.audioContext) {
      this.audioContext.close().catch(() => {});
    }
    this.isRecording = false;
  }

  // Convert to WAV for API upload
  async toWavBlob() {
    // Placeholder: in production, use ffmpeg.js or server-side conversion
    return new Blob(this.audioChunks, { type: 'audio/webm' });
  }
}

// Audio feedback helper
export function playBeep(type = 'start') {
  const ctx = new AudioContext();
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.connect(gain);
  gain.connect(ctx.destination);

  if (type === 'start') {
    osc.frequency.value = 880; // A5
    gain.gain.value = 0.1;
    osc.start();
    osc.stop(ctx.currentTime + 0.1);
  } else {
    osc.frequency.value = 440; // A4
    gain.gain.value = 0.1;
    osc.start();
    osc.stop(ctx.currentTime + 0.1);
  }

  setTimeout(function() {
    ctx.close().catch(function() {});
  }, 200);
}
