// ============ TTS (文本转语音) ============
// 基于浏览器原生 Web Speech API，给老人端做语音播报
// 不支持的环境下静默降级，调用方应先用 isSupported() 判断

var synth = (typeof window !== 'undefined') ? window.speechSynthesis : null;
var cachedVoices = [];

// Chrome 加载语音列表是异步的，需要监听 voiceschanged 事件
function loadVoices() {
  if (!synth) return;
  var v = synth.getVoices();
  if (v && v.length) cachedVoices = v;
}
if (synth) {
  loadVoices();
  if (typeof synth.onvoiceschanged !== 'undefined') {
    synth.onvoiceschanged = loadVoices;
  }
}

export function isSupported() {
  return !!(synth && typeof SpeechSynthesisUtterance !== 'undefined');
}

// 挑一个中文语音引擎，优先 zh-CN，其次任意 zh 开头的
function pickVoice() {
  if (!cachedVoices.length) loadVoices();
  var fallback = null;
  for (var i = 0; i < cachedVoices.length; i++) {
    var lang = (cachedVoices[i].lang || '').toLowerCase();
    if (lang === 'zh-cn') return cachedVoices[i];
    if (!fallback && lang.indexOf('zh') === 0) fallback = cachedVoices[i];
  }
  return fallback;
}

// 播报一段文本
// options: { rate, pitch, volume, onStart, onEnd }
export function speak(text, options) {
  if (!isSupported() || !text) return;
  options = options || {};
  // 打断已有播报，避免队列堆积
  synth.cancel();
  var u = new SpeechSynthesisUtterance(String(text));
  u.lang = 'zh-CN';
  // 语速稍慢，适合老人收听
  u.rate = options.rate != null ? options.rate : 0.9;
  u.pitch = options.pitch != null ? options.pitch : 1.0;
  u.volume = options.volume != null ? options.volume : 1.0;
  var voice = pickVoice();
  if (voice) u.voice = voice;
  if (typeof options.onStart === 'function') u.onstart = options.onStart;
  // 结束或出错都要回调，方便 UI 复位
  if (typeof options.onEnd === 'function') {
    u.onend = options.onEnd;
    u.onerror = options.onEnd;
  }
  synth.speak(u);
}

export function stopSpeak() {
  if (!isSupported()) return;
  synth.cancel();
}

export function isSpeaking() {
  return !!(synth && synth.speaking);
}
