// ============ VOICE RECORDER ============
// Web Audio API + MediaRecorder + VAD

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
      silenceTimeout: options.silenceTimeout || 2000,   // 沉默 2 秒自动停止
      sampleRate: options.sampleRate || 16000,
    };
    this.onStart = null;
    this.onStop = null;
    this.onData = null;
    this.onError = null;
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
        if (this.onError) this.onError(e.message);
      };

      this.audioChunks = [];
      this._startTime = Date.now();
      this.mediaRecorder.start(100); // 每 100ms 收集一次
      this.isRecording = true;

      // VAD loop
      this._vadLoop();

      // Max duration timeout
      this.maxTimeout = setTimeout(() => {
        if (this.isRecording) this.stop();
      }, this.options.maxDuration);

      if (this.onStart) this.onStart();

    } catch (err) {
      if (this.onError) this.onError(err.message);
    }
  }

  stop() {
    if (!this.isRecording) return;
    this.isRecording = false;
    if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
      this.mediaRecorder.stop();
    }
    if (this.maxTimeout) clearTimeout(this.maxTimeout);
  }

  _vadLoop() {
    if (!this.isRecording) return;

    const dataArray = new Uint8Array(this.analyser.frequencyBinCount);
    this.analyser.getByteFrequencyData(dataArray);

    // Calculate RMS energy
    let sum = 0;
    for (let i = 0; i < dataArray.length; i++) {
      sum += (dataArray[i] / 255) ** 2;
    }
    const rms = Math.sqrt(sum / dataArray.length);

    // Silence detection (RMS < 0.02)
    if (rms < 0.02) {
      if (!this.silenceStart) {
        this.silenceStart = Date.now();
      } else if (Date.now() - this.silenceStart > this.options.silenceTimeout) {
        // Silence timeout exceeded
        if (this.mediaRecorder.state === 'recording' && this._getRecordingDuration() >= this.options.minDuration) {
          this.stop();
          return;
        }
      }
    } else {
      this.silenceStart = null;
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
