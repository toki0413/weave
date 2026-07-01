// ============ TTS 播报按钮 ============
// 可复用的小喇叭按钮，点击切换播报/停止
import { el } from './components.js';
import { state } from '../state.js';
import { speak, stopSpeak, isSpeaking, isSupported } from '../audio/tts.js';

var SIZE_CLASS = {
  small: 'tts-btn tts-btn-small',
  normal: 'tts-btn',
  large: 'tts-btn tts-btn-large',
};

// 创建一个播报按钮，返回 DOM 元素
// 不支持 TTS 或用户关闭了语音反馈时返回 null，调用方直接 append 即可
export function createTTSButton(text, options) {
  options = options || {};
  // 浏览器不支持或用户关了语音反馈，就不渲染按钮
  if (!isSupported()) return null;
  if (state.voiceFeedback === false) return null;

  var size = options.size || 'normal';
  var cls = SIZE_CLASS[size] || SIZE_CLASS.normal;

  var btn = el('button', {
    className: cls,
    type: 'button',
    'aria-label': '语音播报',
    title: '点击播报',
    onclick: function() {
      if (isSpeaking()) {
        stopSpeak();
        btn.classList.remove('speaking');
      } else {
        // 先给视觉反馈，onstart 在某些浏览器里来得慢
        btn.classList.add('speaking');
        speak(text, {
          onStart: function() { btn.classList.add('speaking'); },
          onEnd: function() { btn.classList.remove('speaking'); },
        });
      }
    },
  }, '🔊');

  // 带文字标签时，横向排成一组
  if (options.label) {
    return el('span', { style: { display: 'inline-flex', alignItems: 'center', gap: '6px' } }, [
      btn,
      el('span', { className: 'tts-btn-label' }, options.label),
    ]);
  }
  return btn;
}
