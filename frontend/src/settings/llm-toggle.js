// ============ LLM 设置开关：启用 AI 助手 + 隐私协议确认 ============
import { el } from '../ui/components.js';

var PRIVACY_NOTICE = (
  '开启 AI 助手后，脱敏后的记忆片段将被发送到外部大模型服务（如 OpenAI、DeepSeek 等）进行处理，' +
  '以生成记忆总结、情感分析和智能问答。我们不会在请求中传输您的真实姓名、电话号码等敏感信息。' +
  '是否确认开启？'
);

export function renderLLMSettings(container) {
  if (!container) return;
  container.innerHTML = '';

  var isEnabled = localStorage.getItem('llmEnabled') === 'true';

  var wrap = el('div', { style: { padding: '16px' } });

  // 标题
  wrap.appendChild(el('h3', { style: { fontSize: '1rem', fontWeight: '700', marginBottom: '12px' } }, 'AI 助手设置'));

  // 开关行
  var row = el('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' } });
  row.appendChild(el('div', { style: { fontSize: '0.9rem' } }, '启用 AI 助手'));

  // 自定义开关样式
  var toggleBtn = el('button', {
    style: {
      width: '44px', height: '24px', borderRadius: '12px', border: 'none',
      background: isEnabled ? 'var(--accent)' : 'var(--muted)',
      cursor: 'pointer', position: 'relative', transition: 'background 0.2s',
    },
  });

  var knob = el('span', {
    style: {
      position: 'absolute', top: '2px', left: isEnabled ? '22px' : '2px',
      width: '20px', height: '20px', borderRadius: '50%', background: '#fff',
      transition: 'left 0.2s', boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
    },
  });
  toggleBtn.appendChild(knob);

  function updateToggleState(enabled) {
    toggleBtn.style.background = enabled ? 'var(--accent)' : 'var(--muted)';
    knob.style.left = enabled ? '22px' : '2px';
  }

  toggleBtn.onclick = function() {
    var next = !isEnabled;
    if (next) {
      // 开启：弹出隐私确认
      if (!window.confirm(PRIVACY_NOTICE)) {
        return; // 用户取消
      }
      localStorage.setItem('llmEnabled', 'true');
      isEnabled = true;
      updateToggleState(true);
      // 触发刷新，让 UI 上的 AI 按钮出现
      window.dispatchEvent(new CustomEvent('cg-features-changed'));
    } else {
      // 关闭：直接关闭
      localStorage.setItem('llmEnabled', 'false');
      isEnabled = false;
      updateToggleState(false);
      window.dispatchEvent(new CustomEvent('cg-features-changed'));
    }
  };

  row.appendChild(toggleBtn);
  wrap.appendChild(row);

  // 说明文字
  wrap.appendChild(el('div', { style: { fontSize: '0.75rem', color: 'var(--ink2)', lineHeight: '1.5' } }, [
    '启用后，您可以使用以下功能：',
    el('ul', { style: { margin: '6px 0 0 16px', padding: 0 } }, [
      el('li', {}, 'AI 记忆总结：将一周的记忆片段编织成连贯故事'),
      el('li', {}, 'AI 情感分析：更精准地识别文本情绪'),
      el('li', {}, '智能问答：基于记忆记录回答您的问题'),
    ]),
  ]));

  container.appendChild(wrap);
}
