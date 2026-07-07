// ============ ELDERLY MODE ============
// 老人端极简模式：只保留核心交互——讲述今日 + 家属留言
import { el } from '../ui/components.js';
import { listSessions, uploadAudio, sendWebSocketReadReceipt, isLoggedIn, createSession } from '../api/client.js';
import { createVoiceEditor } from '../ui/voice-editor.js';
import { state } from '../state.js';
import { connect as wsConnect, send as wsSend, isConnected } from '../services/websocket.js';
import { getToken } from '../api/client.js';
import { cacheMessages, getCachedMessages } from '../db/offline.js';
import * as vs from '../3d/view-switcher.js';

export function renderElderlyMode(container) {
  container.innerHTML = '';
  document.documentElement.classList.remove('family-mode', 'doctor-mode');
  document.documentElement.classList.add('elderly-mode');
  document.body.className = 'mode-elderly';

  // 老人端：明确禁用 3D 模式，确保只显示 2D 界面（简单直观）
  localStorage.setItem('viewMode', '2d');
  if (vs.exit3DMode) vs.exit3DMode();

  var app = el('div', {
    className: 'elderly-app',
    style: {
      display: 'flex',
      flexDirection: 'column',
      height: '100vh',
      padding: '24px',
      gap: '20px',
      overflowY: 'auto',
    }
  });

  // 大标题
  app.appendChild(el('h1', {
    style: { fontSize: '2rem', textAlign: 'center', margin: '16px 0', color: 'var(--ink)' }
  }, '今天发生了什么？'));

  // 语音输入区域
  app.appendChild(renderVoiceArea());

  // 家属留言区域
  app.appendChild(renderFamilyMessages());

  // 今日回忆卡片
  app.appendChild(renderTodayMemory());

  container.appendChild(app);

  // 加载今日回忆和家属留言
  loadTodayMemory();
  loadFamilyMessages();

  // 启动 WebSocket
  var token = getToken();
  if (token) {
    wsConnect(token, function(msg) {
      if (msg.type === 'family_care') {
        // 收到家属关怀
        try {
          var audio = new Audio('/gentle-notification.mp3');
          audio.volume = 0.2;
          audio.play().catch(function() {});
        } catch (e) {}
        // 刷新留言列表
        loadFamilyMessages();
      }
      if (msg.type === 'doctor_advice') {
        // 收到医生建议
        try {
          var audio = new Audio('/gentle-notification.mp3');
          audio.volume = 0.2;
          audio.play().catch(function() {});
        } catch (e) {}
      }
    });
  }
}

function renderFamilyMessages() {
  var section = el('div', {
    style: {
      background: 'var(--bg2)',
      borderRadius: '16px',
      padding: '16px',
    }
  });
  section.appendChild(el('div', {
    style: { fontSize: '1.1rem', fontWeight: '700', marginBottom: '12px', color: 'var(--ink)', display: 'flex', alignItems: 'center', gap: '8px' }
  }, [
    el('span', {}, '家属留言'),
    el('span', {
      id: 'elderly-msg-badge',
      style: {
        display: 'none',
        background: 'var(--danger)',
        color: '#fff',
        borderRadius: '10px',
        padding: '2px 8px',
        fontSize: '0.75rem',
      }
    }, '新')
  ]));

  var list = el('div', {
    id: 'elderly-msg-list',
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: '10px',
      maxHeight: '200px',
      overflowY: 'auto',
    }
  });
  list.appendChild(el('div', {
    style: { color: 'var(--muted)', fontSize: '0.9rem' }
  }, '加载中…'));
  section.appendChild(list);
  return section;
}

function loadFamilyMessages() {
  getCachedMessages().then(function(messages) {
    var list = document.getElementById('elderly-msg-list');
    var badge = document.getElementById('elderly-msg-badge');
    if (!list) return;
    list.innerHTML = '';

    var unread = 0;
    var items = (messages || []).slice(-20).reverse();
    if (items.length === 0) {
      list.appendChild(el('div', {
        style: { color: 'var(--muted)', fontSize: '0.9rem' }
      }, '暂无家属留言'));
    } else {
      items.forEach(function(msg) {
        var isUnread = !msg.is_read;
        if (isUnread) unread++;
        var card = el('div', {
          style: {
            background: isUnread ? 'rgba(199,91,91,0.08)' : 'var(--bg3)',
            borderRadius: '10px',
            padding: '12px',
            borderLeft: isUnread ? '3px solid var(--danger)' : '3px solid transparent',
            cursor: 'pointer',
          },
          onclick: function() {
            if (!msg.is_read) {
              msg.is_read = true;
              cacheMessages([msg]);
              // 通过 WebSocket 回传已读
              wsSend(sendWebSocketReadReceipt(msg.from || msg.sender_id, msg.id));
              loadFamilyMessages();
            }
          }
        });
        var typeLabel = msg.type === 'family_care' ? '家属' : (msg.type === 'doctor_advice' ? '医生' : '未知');
        card.appendChild(el('div', {
          style: { fontSize: '0.8rem', color: 'var(--muted)', marginBottom: '4px' }
        }, typeLabel + ' · ' + (msg.timestamp ? new Date(msg.timestamp).toLocaleString('zh-CN') : '刚刚')));
        card.appendChild(el('div', {
          style: { fontSize: '0.95rem', lineHeight: '1.5', color: 'var(--ink)' }
        }, msg.payload && msg.payload.text ? msg.payload.text : JSON.stringify(msg.payload)));
        list.appendChild(card);
      });
    }
    if (badge) {
      badge.style.display = unread > 0 ? 'block' : 'none';
      badge.textContent = unread > 9 ? '9+' : String(unread);
    }
  }).catch(function() {
    var list = document.getElementById('elderly-msg-list');
    if (list) {
      list.innerHTML = '';
      list.appendChild(el('div', {
        style: { color: 'var(--muted)', fontSize: '0.9rem' }
      }, '暂无留言'));
    }
  });
}

function renderVoiceArea() {
  var wrap = el('div', { style: { textAlign: 'center', padding: '20px' } });

  var recBtn = el('button', {
    className: 'cg-btn btn-primary',
    id: 'elderly-rec-btn',
    style: {
      fontSize: '1.5rem',
      padding: '1rem 2rem',
      borderRadius: '12px',
      display: 'inline-flex',
      alignItems: 'center',
      gap: '8px',
    },
    onclick: handleRecord
  }, '🎤 按住说话');
  wrap.appendChild(recBtn);

  // 语音编辑器容器
  var editorContainer = el('div', {
    id: 'elderly-voice-editor',
    style: { marginTop: '16px', textAlign: 'left' }
  });
  wrap.appendChild(editorContainer);

  return wrap;
}

function handleRecord() {
  var btn = document.getElementById('elderly-rec-btn');
  if (!btn) return;

  var speechSupported = 'SpeechRecognition' in window || 'webkitSpeechRecognition' in window;
  var mediaRecorderSupported = 'MediaRecorder' in window && navigator.mediaDevices && navigator.mediaDevices.getUserMedia;
  if (!speechSupported && !mediaRecorderSupported) {
    alert('您的浏览器不支持语音输入');
    return;
  }

  // 浏览器原生语音识别
  if (speechSupported) {
    if (window.__speech_rec__ && window.__speech_rec__.running) {
      window.__speech_rec__.stop();
      return;
    }
    var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    var rec = new SpeechRecognition();
    rec.lang = 'zh-CN';
    rec.continuous = true;
    rec.interimResults = true;
    rec.running = false;
    rec.onstart = function() {
      rec.running = true;
      window.__speech_rec__ = rec;
      if (btn) { btn.textContent = '🔴 录音中…（点击停止）'; btn.style.background = '#ffebee'; btn.style.color = '#c62828'; }
    };
    rec.onresult = function(e) {
      var transcript = '';
      for (var i = e.resultIndex; i < e.results.length; i++) {
        transcript += e.results[i][0].transcript;
      }
      showVoiceEditor(transcript, null);
    };
    rec.onend = function() {
      rec.running = false;
      window.__speech_rec__ = null;
      if (btn) { btn.textContent = '🎤 按住说话'; btn.style.background = ''; btn.style.color = ''; }
    };
    rec.onerror = function() {
      rec.running = false;
      window.__speech_rec__ = null;
      if (btn) { btn.textContent = '🎤 按住说话'; btn.style.background = ''; btn.style.color = ''; }
    };
    rec.start();
    return;
  }

  // MediaRecorder 回退
  import('../audio/recorder.js').then(function(mod) {
    var recorder = new mod.VoiceRecorder({ maxDuration: 30000, silenceTimeout: 1500 });
    recorder.onStart = function() {
      if (btn) { btn.textContent = '🔴 录音中…（点击停止）'; btn.style.background = '#ffebee'; btn.style.color = '#c62828'; }
    };
    recorder.onStop = function(blob) {
      if (btn) { btn.textContent = '🎤 按住说话'; btn.style.background = ''; btn.style.color = ''; }
      uploadAudio(blob).then(function(result) {
        var text = result.text || '';
        var confidenceMap = result.confidence_map || result.words || null;
        showVoiceEditor(text, confidenceMap);
        if (result.audio_metrics) {
          state.lastAudioMetrics = result.audio_metrics;
        }
      }).catch(function(err) {
        console.error('STT upload failed:', err);
        alert('语音识别失败，您可以手动输入文字。');
      });
    };
    recorder.onError = function() {
      if (btn) { btn.textContent = '🎤 按住说话'; btn.style.background = ''; btn.style.color = ''; }
    };
    recorder.start();
    btn._recorder = recorder;
  });
}

function showVoiceEditor(transcript, confidenceMap) {
  var container = document.getElementById('elderly-voice-editor');
  if (!container) return;
  container.innerHTML = '';

  var editor = createVoiceEditor(transcript, confidenceMap);
  container.appendChild(editor);

  editor.confirmButton.onclick = function() {
    var text = editor.getCorrectedText();
    container.innerHTML = '';
    // 将修正后的文本直接显示为今日回忆
    var content = document.getElementById('elderly-memory-content');
    if (content) content.textContent = text;
    // 提交到后端（如果有登录）
    if (isLoggedIn()) {
      createSession(0, text).catch(function() {});
    }
  };

  editor.directButton.onclick = function() {
    var text = editor.getCorrectedText();
    container.innerHTML = '';
    var content = document.getElementById('elderly-memory-content');
    if (content) content.textContent = text;
    if (isLoggedIn()) {
      createSession(0, text).catch(function() {});
    }
  };
}

function renderTodayMemory() {
  var card = el('div', {
    className: 'memory-card',
    style: {
      background: 'var(--bg2)',
      borderRadius: '16px',
      padding: '20px',
      flex: 1,
    }
  });
  card.appendChild(el('div', {
    style: { fontSize: '1.1rem', fontWeight: '700', marginBottom: '12px', color: 'var(--ink)' }
  }, '今日回忆'));
  var content = el('div', {
    id: 'elderly-memory-content',
    style: { fontSize: '1.05rem', lineHeight: '1.7', color: 'var(--ink2)' }
  }, '加载中…');
  card.appendChild(content);
  return card;
}

function loadTodayMemory() {
  listSessions(1).then(function(sessions) {
    var content = document.getElementById('elderly-memory-content');
    if (!content) return;
    if (sessions && sessions.length > 0) {
      var s = sessions[0];
      content.textContent = s.narrative_text || s.text || '暂无今日记录';
    } else {
      content.textContent = '暂无今日记录，点击上方按钮讲述今天的故事吧。';
    }
  }).catch(function() {
    var content = document.getElementById('elderly-memory-content');
    if (content) content.textContent = '暂无今日记录';
  });
}
