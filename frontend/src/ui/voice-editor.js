// ============ VOICE EDITOR ============
// 语音输入渐进增强：低置信度词高亮 + 人工修正
import { el } from './components.js';

export function createVoiceEditor(transcript, confidenceMap) {
  var wrapper = el('div', {
    className: 'voice-editor',
    id: 'voice-editor-panel',
    style: {
      marginTop: '12px',
      padding: '12px',
      border: '1px solid var(--rule)',
      borderRadius: '8px',
      background: 'var(--bg)',
    }
  });

  var title = el('div', {
    style: {
      fontWeight: '700',
      marginBottom: '8px',
      fontSize: '0.9rem',
      color: 'var(--muted)',
    }
  }, '请确认识别内容（点击红色下划线文字可修正）');
  wrapper.appendChild(title);

  var editor = el('div', {
    className: 'voice-editor-content',
    contenteditable: 'true',
    style: {
      minHeight: '80px',
      padding: '10px',
      lineHeight: '1.6',
      border: '1px solid var(--rule2)',
      borderRadius: '6px',
      background: '#fff',
      color: 'var(--ink)',
      fontSize: '1rem',
      outline: 'none',
      whiteSpace: 'pre-wrap',
    }
  });

  // 构建高亮文本
  if (confidenceMap && typeof confidenceMap === 'object' && !Array.isArray(confidenceMap)) {
    var text = transcript;
    var keys = Object.keys(confidenceMap).sort(function(a, b) { return b.length - a.length; });
    keys.forEach(function(word) {
      var confidence = confidenceMap[word];
      if (confidence < 0.7) {
        var escaped = word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        text = text.replace(new RegExp(escaped, 'g'), function(match) {
          return '<span class="low-confidence" title="置信度: ' + Math.round(confidence * 100) + '%">' + match + '</span>';
        });
      }
    });
    editor.innerHTML = text;
  } else if (Array.isArray(confidenceMap)) {
    var html = '';
    confidenceMap.forEach(function(item) {
      var word = item.word || item.text || '';
      var confidence = item.confidence || 0;
      if (confidence < 0.7) {
        html += '<span class="low-confidence" title="置信度: ' + Math.round(confidence * 100) + '%">' + word + '</span>';
      } else {
        html += word;
      }
    });
    editor.innerHTML = html;
  } else {
    editor.textContent = transcript;
  }

  // 点击低置信度词弹出修正
  editor.addEventListener('click', function(e) {
    var target = e.target;
    if (target && target.classList && target.classList.contains('low-confidence')) {
      var correction = prompt('修正识别文字:', target.textContent);
      if (correction !== null && correction !== '') {
        target.textContent = correction;
        target.classList.remove('low-confidence');
        target.removeAttribute('title');
      }
    }
  });

  wrapper.appendChild(editor);

  // 按钮栏
  var btnBar = el('div', {
    style: {
      marginTop: '10px',
      display: 'flex',
      gap: '8px',
      justifyContent: 'flex-end',
    }
  });

  var confirmBtn = el('button', { className: 'btn-primary' }, '确认提交');
  var directBtn = el('button', { className: 'btn-secondary' }, '直接提交');

  btnBar.appendChild(directBtn);
  btnBar.appendChild(confirmBtn);
  wrapper.appendChild(btnBar);

  wrapper.getCorrectedText = function() {
    return editor.innerText || editor.textContent || '';
  };

  wrapper.confirmButton = confirmBtn;
  wrapper.directButton = directBtn;

  return wrapper;
}
