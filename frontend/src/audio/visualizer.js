// ============ AUDIO VISUALIZER ============
// 使用 Web Audio API 绘制实时语音波形

function createAudioVisualizer(canvas) {
  var ctx = canvas.getContext('2d');
  var audioCtx = null;
  var analyser = null;
  var source = null;
  var animId = null;
  var dataArray = null;
  var running = false;

  function resize() {
    var dpr = window.devicePixelRatio || 1;
    var rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);
  }

  function draw() {
    if (!analyser || !running) return;
    animId = requestAnimationFrame(draw);
    analyser.getByteFrequencyData(dataArray);

    var rect = canvas.getBoundingClientRect();
    var w = rect.width;
    var h = rect.height;
    var barCount = 64;
    var barWidth = w / barCount;

    ctx.clearRect(0, 0, w, h);

    var sum = 0;
    for (var i = 0; i < dataArray.length; i++) {
      sum += dataArray[i];
    }
    var avg = sum / dataArray.length;

    // 绿色主题波形
    for (var i = 0; i < barCount; i++) {
      var idx = Math.floor(i * dataArray.length / barCount);
      var val = dataArray[idx] || 0;
      var barHeight = (val / 255) * h * 0.9;
      var x = i * barWidth + barWidth * 0.1;
      var bw = barWidth * 0.8;
      var y = (h - barHeight) / 2;

      var intensity = val / 255;
      var r = Math.floor(74 + intensity * 50);
      var g = Math.floor(124 + intensity * 80);
      var b = Math.floor(74 + intensity * 50);
      ctx.fillStyle = 'rgb(' + r + ',' + g + ',' + b + ')';
      ctx.fillRect(x, y, bw, barHeight);
    }

    // 触发音量过低事件
    if (avg < 15 && canvas.onVolumeLow) {
      canvas.onVolumeLow();
    } else if (canvas.onVolumeNormal) {
      canvas.onVolumeNormal();
    }
  }

  function start(stream) {
    if (running) return Promise.resolve();
    return new Promise(function(resolve, reject) {
      try {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        analyser = audioCtx.createAnalyser();
        analyser.fftSize = 256;
        analyser.smoothingTimeConstant = 0.8;
        source = audioCtx.createMediaStreamSource(stream);
        source.connect(analyser);
        var bufferLength = analyser.frequencyBinCount;
        dataArray = new Uint8Array(bufferLength);
        running = true;
        resize();
        draw();
        resolve();
      } catch (e) {
        reject(e);
      }
    });
  }

  function stop() {
    running = false;
    if (animId) {
      cancelAnimationFrame(animId);
      animId = null;
    }
    if (source) {
      try { source.disconnect(); } catch (e) {}
      source = null;
    }
    if (audioCtx) {
      try { audioCtx.close(); } catch (e) {}
      audioCtx = null;
    }
    if (ctx && canvas) {
      var rect = canvas.getBoundingClientRect();
      ctx.clearRect(0, 0, rect.width, rect.height);
    }
    analyser = null;
    dataArray = null;
  }

  return {
    start: start,
    stop: stop,
    canvas: canvas
  };
}

export { createAudioVisualizer };
