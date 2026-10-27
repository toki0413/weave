// ============ ELDERLY MODE ============
// 老人端极简模式：只保留核心交互——讲述今日 + 家属留言
import { el } from '../ui/components.js';
import { listSessions, uploadAudio, sendWebSocketReadReceipt, isLoggedIn, createSession } from '../api/client.js';
import { createVoiceEditor } from '../ui/voice-editor.js';
import { planRecording } from '../audio/transcript-source.js';
import { state } from '../state.js';
import { connect as wsConnect, send as wsSend, isConnected } from '../services/websocket.js';
import { getToken } from '../api/client.js';
import { cacheMessages, getCachedMessages } from '../db/offline.js';
import { savePendingAudio, getPendingAudioList, countPendingAudio, deletePendingAudio } from '../db/offline.js';
import * as vs from '../3d/view-switcher.js';

// story-7 主路径契约（PRD pilot-p0-repair）：
// 浏览器 SpeechRecognition 只做实时预览；最终入库文本一律来自后端
// provider 链（百炼→火山→vosk）转写结果，随会话写入 0018 溯源列。
// 后端转写失败 → 重试卡（内存保底 blob），绝不静默用预览文本入库；
// story-1 会把保底升级为 IndexedDB 离线补传。
var _pendingBlob = null;   // 待补传的录音（内存保底）
var _pendingStoreId = null; // story-1：该录音在 IndexedDB pendingAudio 里的 id
var _recording = false;    // SR / recorder 任一活动中

export function renderElderlyMode(container) {
  container.innerHTML = '';
  document.documentElement.classList.remove('family-mode', 'doctor-mode');
  document.documentElement.classList.add('elderly-mode');
  document.body.className = 'mode-elderly';

  // 老人端不支持 3D：只退出当前 3D 视图，不再写共享的 viewMode。
  // 旧实现这里 setItem('viewMode','2d') 有两个问题：一是静默清掉家属在同一
  // 设备上存的 3D 偏好；二是它其实在掩盖 main.js 的启动恢复行为（那里在
  // getMe() 之前就用 setTimeout 读旧的全局键进 3D），而不是在防护。
  // 现在由 main.js 侧按模式判定，老人端永远拿不到 '3d'。
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

  // story-1：打开即检查待存档录音；网络恢复时自动补传（监听器只挂一次）
  autoRetryPending();
  if (!window.__pendingAudioOnlineHooked) {
    window.__pendingAudioOnlineHooked = true;
    window.addEventListener('online', function() { autoRetryPending(); });
  }

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

  // SR 实时预览（仅预览，不是最终文本；后端转写结果到达后由编辑器取代）
  var preview = el('div', {
    id: 'elderly-voice-preview',
    style: {
      marginTop: '12px', minHeight: '1.5em', fontSize: '1.1rem',
      color: 'var(--muted)', textAlign: 'left', lineHeight: '1.6',
      display: 'none',
    }
  });
  wrap.appendChild(preview);

  // story-1：待存档入口——转写失败的录音留在手机上，可补传/重听/删除
  var pendingArea = el('div', { id: 'elderly-pending-area', style: { marginTop: '12px' } });
  wrap.appendChild(pendingArea);

  // 语音编辑器容器
  var editorContainer = el('div', {
    id: 'elderly-voice-editor',
    style: { marginTop: '16px', textAlign: 'left' }
  });
  wrap.appendChild(editorContainer);

  return wrap;
}

function _setBtnIdle(btn) {
  btn.textContent = '🎤 按住说话';
  btn.style.background = '';
  btn.style.color = '';
  btn.disabled = false;
  btn.style.opacity = '1';
  btn.style.cursor = 'pointer';
}

function _setBtnRecording(btn) {
  btn.textContent = '🔴 录音中…（点击停止）';
  btn.style.background = '#ffebee';
  btn.style.color = '#c62828';
}

function _setBtnUploading(btn) {
  btn.textContent = '正在转写，请稍候…';
  btn.disabled = true;
  btn.style.background = '';
  btn.style.color = '';
  btn.style.opacity = '0.7';
  btn.style.cursor = 'wait';
}

function handleRecord() {
  var btn = document.getElementById('elderly-rec-btn');
  if (!btn) return;

  var speechSupported = 'SpeechRecognition' in window || 'webkitSpeechRecognition' in window;
  var recorderSupported = 'MediaRecorder' in window && navigator.mediaDevices && navigator.mediaDevices.getUserMedia;
  var plan = planRecording(speechSupported, recorderSupported);

  if (plan === 'manual') {
    // SR-only 设备录不了音频：不伪装成"识别成功"。诚实降级为手动输入，
    // 会话不带任何 ASR 溯源（0018 列 NULL = 未知）。
    alert('当前浏览器录不了音频。可以直接打字告诉我，或换用 Chrome 浏览器。');
    showManualInput();
    return;
  }

  if (_recording) {
    stopRecording(btn, plan);
    return;
  }
  startRecording(btn, plan);
}

function startRecording(btn, plan) {
  _recording = true;
  _setBtnRecording(btn);
  var preview = document.getElementById('elderly-voice-preview');
  if (preview) {
    preview.style.display = 'block';
    preview.textContent = '听着呢…（说出来的字会显示在这里）';
  }

  var sr = null;
  if (plan === 'dual') {
    var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    sr = new SpeechRecognition();
    sr.lang = 'zh-CN';
    sr.continuous = true;
    sr.interimResults = true;
    // SR 只做预览：onresult 只更新预览区文本，不重建编辑器
    // （旧实现每个 interim 结果重建整个 voice-editor，会把老人改了一半的字清掉）
    sr.onresult = function(e) {
      var p = document.getElementById('elderly-voice-preview');
      if (!p) return;
      var transcript = '';
      for (var i = e.resultIndex; i < e.results.length; i++) {
        transcript += e.results[i][0].transcript;
      }
      p.textContent = transcript || '听着呢…';
    };
    sr.onerror = function() {
      // 预览死了不影响录音：MediaRecorder 仍在采集，后端转写仍是最终来源
      var p = document.getElementById('elderly-voice-preview');
      if (p && _recording) p.textContent = '（实时字幕暂不可用，仍在录音）';
    };
    sr.onend = function() {
      sr = null;
    };
    try { sr.start(); } catch (e) { sr = null; }
  }

  import('../audio/recorder.js').then(function(mod) {
    // 时长上限维持现状（30s/静默 1.5s 的对齐是 story-6，不在本批）
    var recorder = new mod.VoiceRecorder({ maxDuration: 30000, silenceTimeout: 1500 });
    recorder.onStart = function() {
      if (btn) _setBtnRecording(btn);
    };
    recorder.onStop = function(blob) {
      // 唯一的上传触发点：录音真正结束才进入转写，SR 仅为预览
      _recording = false;
      try { if (sr) { sr.onend = function() {}; sr.stop(); } } catch (e) {}
      if (btn) _setBtnUploading(btn);
      beginUpload(blob);
    };
    recorder.onError = function() {
      _recording = false;
      if (btn) _setBtnIdle(btn);
      var p = document.getElementById('elderly-voice-preview');
      if (p) { p.style.display = 'none'; }
    };
    recorder.start();
    btn._recorder = recorder;
    btn._sr = sr;
  });
}

function stopRecording(btn, plan) {
  _recording = false;
  var rec = btn._recorder;
  var sr = btn._sr;
  try { if (sr) { sr.onend = function() {}; sr.stop(); } } catch (e) {}
  if (rec) {
    // recorder.onStop 回调里进入转写态（含按钮状态与上传）
    try { rec.stop(); } catch (e) {
      _setBtnIdle(btn);
      var p = document.getElementById('elderly-voice-preview');
      if (p) p.style.display = 'none';
    }
  } else {
    // recorder 尚未就绪（点击太快）：无音频可传，回空闲态
    _setBtnIdle(btn);
    var p = document.getElementById('elderly-voice-preview');
    if (p) p.style.display = 'none';
  }
  btn._recorder = null;
  btn._sr = null;
}

function beginUpload(blob, storeId) {
  var btn = document.getElementById('elderly-rec-btn');
  var preview = document.getElementById('elderly-voice-preview');
  if (preview) preview.style.display = 'none';
  _pendingBlob = blob;              // 内存保底；真实留底在 IndexedDB（下方失败路径）
  _pendingStoreId = storeId || null;
  uploadAudio(blob).then(function(result) {
    _pendingBlob = null;
    if (_pendingStoreId != null) {
      // 补传成功：清除 IndexedDB 里的留底
      deletePendingAudio(_pendingStoreId).catch(function() {});
      _pendingStoreId = null;
    }
    if (btn) _setBtnIdle(btn);
    if (result.audio_metrics) {
      state.lastAudioMetrics = result.audio_metrics;
    }
    renderPendingArea();
    // 最终文本 = 后端转写结果（含词典热词与置信度），绝不是浏览器预览
    showVoiceEditor(result.text || '', result.confidence_map || result.words || null, {
      provider: result.source,
      confidence: result.confidence,
      audioMetrics: result.audio_metrics || null,
    });
  }).catch(function(err) {
    console.error('STT upload failed:', err);
    if (btn) _setBtnIdle(btn);
    // story-1：失败先落 IndexedDB（内存只是过渡），再出重试卡；
    // 从留底发起的重试失败不重复入库
    if (_pendingStoreId != null) {
      showRetryCard(blob);
    } else {
      savePendingAudio(blob).then(function(id) {
        _pendingStoreId = id;
        showRetryCard(blob);
        renderPendingArea();
      }).catch(function() {
        // 存储配额等异常：退化为内存保底，仍出重试卡
        showRetryCard(blob);
      });
    }
  });
}

function showRetryCard(blob) {
  var container = document.getElementById('elderly-voice-editor');
  if (!container) return;
  container.innerHTML = '';
  var card = el('div', {
    style: {
      background: 'var(--bg2)', borderRadius: '12px', padding: '16px',
      border: '2px solid var(--danger)',
    }
  });
  card.appendChild(el('div', {
    style: { fontSize: '1.15rem', color: 'var(--ink)', marginBottom: '12px', fontWeight: '700' }
  }, '没听清，请再试一次'));
  card.appendChild(el('div', {
    style: { fontSize: '0.95rem', color: 'var(--muted)', marginBottom: '12px' }
  }, '刚才说的话已经帮你留下了，不会丢。'));
  var btnRow = el('div', { style: { display: 'flex', gap: '10px' } });
  btnRow.appendChild(el('button', {
    className: 'cg-btn btn-primary',
    style: { fontSize: '1.05rem', padding: '0.7rem 1.2rem' },
    onclick: function() {
      container.innerHTML = '';
      beginUpload(blob, _pendingStoreId);
    }
  }, '再试一次'));
  btnRow.appendChild(el('button', {
    className: 'cg-btn',
    style: { fontSize: '1.05rem', padding: '0.7rem 1.2rem' },
    onclick: function() {
      container.innerHTML = '';
      _pendingBlob = null;
      showManualInput();
    }
  }, '改用打字'));
  card.appendChild(btnRow);
  container.appendChild(card);
}

// ---------- story-1：待存档录音（IndexedDB 保底 + 自动补传） ----------

function autoRetryPending() {
  renderPendingArea();
  // 未登录时不自动补传（/stt 需要认证），入口卡会提示"登录后才能补传"
  if (!isLoggedIn()) return;
  countPendingAudio().then(function(n) {
    if (n > 0 && navigator.onLine) retryAllPending(true);
  }).catch(function() {});
}

function renderPendingArea() {
  var area = document.getElementById('elderly-pending-area');
  if (!area) return;
  countPendingAudio().then(function(n) {
    area.innerHTML = '';
    if (!n) { area.style.display = 'none'; return; }
    area.style.display = 'block';
    var card = el('div', {
      style: {
        background: 'var(--bg2)', borderRadius: '12px', padding: '14px',
        border: '2px solid var(--warn, #c69214)',
      }
    });
    var msg = '你有 ' + n + ' 条回忆待存档' + (isLoggedIn() ? '' : '（登录后才能补传）');
    if (area.__resultMsg) { msg = area.__resultMsg; area.__resultMsg = null; }
    card.appendChild(el('div', {
      style: { fontSize: '1.05rem', color: 'var(--ink)', fontWeight: '700' }
    }, msg));
    var row = el('div', {
      style: { display: 'flex', gap: '10px', marginTop: '10px', flexWrap: 'wrap' }
    });
    if (isLoggedIn()) {
      row.appendChild(el('button', {
        className: 'cg-btn btn-primary',
        style: { fontSize: '1rem', padding: '0.6rem 1rem' },
        onclick: function() { retryAllPending(false); }
      }, '全部补传'));
    }
    row.appendChild(el('button', {
      className: 'cg-btn',
      style: { fontSize: '1rem', padding: '0.6rem 1rem' },
      onclick: playLatestPending
    }, '重听最新一条'));
    row.appendChild(el('button', {
      className: 'cg-btn',
      style: { fontSize: '1rem', padding: '0.6rem 1rem' },
      onclick: deleteAllPending
    }, '删除'));
    card.appendChild(row);
    area.appendChild(card);
  }).catch(function() { area.innerHTML = ''; });
}

function retryAllPending(silent) {
  var area = document.getElementById('elderly-pending-area');
  getPendingAudioList().then(function(items) {
    if (!items.length) { renderPendingArea(); return; }
    var success = 0;
    var chain = Promise.resolve();
    items.forEach(function(item) {
      chain = chain.then(function() {
        return uploadAudio(item.blob).then(function(result) {
          // 补传成功 = 后端转写文本直接入库（老人已口头确认过要保存）
          return submitSession(result.text || '', result.audio_metrics || null, {
            asr_provider: result.source,
            asr_confidence: result.confidence,
          }, { silent: true }).then(function() {
            success++;
            return deletePendingAudio(item.id);
          });
        }).catch(function(err) {
          // 该条保留在 IndexedDB，下一轮（打开应用/网络恢复）再试
          console.warn('pending audio retry failed:', err);
        });
      });
    });
    return chain.then(function() {
      if (area) {
        if (success > 0) {
          area.__resultMsg = '上次的回忆已经存好啦' +
            (items.length - success > 0 ? '；还有 ' + (items.length - success) + ' 条没成功，下次再试' : '');
        } else if (!silent) {
          area.__resultMsg = '这次没成功，等网络好了再试试';
        }
      }
      renderPendingArea();
    });
  }).catch(function() { renderPendingArea(); });
}

function playLatestPending() {
  getPendingAudioList().then(function(items) {
    if (!items.length) return;
    var last = items[items.length - 1];
    var url = URL.createObjectURL(last.blob);
    var audio = new Audio(url);
    audio.play().catch(function() {});
    audio.addEventListener('ended', function() { URL.revokeObjectURL(url); });
  }).catch(function() {});
}

function deleteAllPending() {
  countPendingAudio().then(function(n) {
    if (!n) return;
    if (!window.confirm('确定删掉这 ' + n + ' 条没存上的录音吗？删了就找不回来了。')) return;
    getPendingAudioList().then(function(items) {
      var chain = Promise.resolve();
      items.forEach(function(item) {
        chain = chain.then(function() { return deletePendingAudio(item.id); });
      });
      return chain;
    }).then(function() {
      _pendingBlob = null;
      _pendingStoreId = null;
      renderPendingArea();
    }).catch(function() { renderPendingArea(); });
  }).catch(function() {});
}

function showManualInput() {
  var container = document.getElementById('elderly-voice-editor');
  if (!container) return;
  container.innerHTML = '';
  var ta = el('textarea', {
    style: {
      width: '100%', minHeight: '110px', fontSize: '1.15rem', lineHeight: '1.7',
      padding: '12px', borderRadius: '10px', border: '2px solid var(--border, #ccc)',
      resize: 'vertical',
    },
    placeholder: '在这里把刚才想说的话打出来…'
  });
  container.appendChild(ta);
  container.appendChild(el('div', { style: { marginTop: '10px' } }, [
    el('button', {
      className: 'cg-btn btn-primary',
      style: { fontSize: '1.1rem', padding: '0.7rem 1.4rem' },
      onclick: function() {
        var text = (ta.value || '').trim();
        if (!text) { ta.focus(); return; }
        var target = document.getElementById('elderly-voice-editor');
        if (target) target.innerHTML = '';
        // 手动输入：无音频无 ASR —— 溯源列保持 NULL（未知），不编造
        submitSession(text, null, null, { statusEl: target });
      }
    }, '保存这条回忆'),
  ]));
  ta.focus();
}

function submitSession(text, audioMetrics, asrInfo, opts) {
  opts = opts || {};

  if (opts.silent) {
    // 自动补传路径：无状态 UI，错误原样抛给调用链统计
    return createSession(0, text, 'mandarin', audioMetrics, asrInfo);
  }

  var statusEl = opts.statusEl || document.getElementById('elderly-voice-editor');

  if (!isLoggedIn()) {
    // story-2：未登录绝不假装"已保存"——明示未保存 + 登录入口 + 草稿不丢
    showNotLoggedInDraft(statusEl, text);
    return Promise.resolve(false);
  }

  _setStatus(statusEl, '正在保存…', 'busy');
  return createSession(0, text, 'mandarin', audioMetrics, asrInfo).then(function() {
    var content = document.getElementById('elderly-memory-content');
    if (content) content.textContent = text;
    _setStatus(statusEl, '✓ 今天的回忆已存好', 'ok');
    return true;
  }).catch(function() {
    _setStatusFailed(statusEl, text, audioMetrics, asrInfo, opts);
    return false;
  });
}

function _setStatus(container, msg, kind) {
  if (!container) return;
  container.innerHTML = '';
  var color = kind === 'ok' ? '#2e7d32' : (kind === 'fail' ? 'var(--danger)' : 'var(--muted)');
  container.appendChild(el('div', {
    style: {
      fontSize: '1.2rem', fontWeight: '700', color: color,
      textAlign: 'center', padding: '14px 8px',
    }
  }, msg));
}

function _setStatusFailed(container, text, audioMetrics, asrInfo, opts) {
  if (!container) return;
  container.innerHTML = '';
  var box = el('div', {
    style: {
      border: '2px solid var(--danger)', borderRadius: '12px',
      padding: '14px', textAlign: 'center',
    }
  });
  box.appendChild(el('div', {
    style: { fontSize: '1.15rem', fontWeight: '700', color: 'var(--danger)', marginBottom: '6px' }
  }, '没存上，请再试一次'));
  box.appendChild(el('div', {
    style: { fontSize: '0.95rem', color: 'var(--muted)', marginBottom: '12px' }
  }, '这段文字给您留着呢，不会丢。'));
  var row = el('div', { style: { display: 'flex', gap: '10px', justifyContent: 'center' } });
  row.appendChild(el('button', {
    className: 'cg-btn btn-primary',
    style: { fontSize: '1.05rem', padding: '0.7rem 1.2rem' },
    onclick: function() {
      // 重试走同一条路径：成功后才更新今日回忆（不再有先显示后保存）
      submitSession(text, audioMetrics, asrInfo, { statusEl: container, story: opts && opts.story });
    }
  }, '再试一次'));
  box.appendChild(row);
  container.appendChild(box);
}

function showNotLoggedInDraft(container, text) {
  if (!container) return;
  container.innerHTML = '';
  var box = el('div', {
    style: {
      border: '2px solid var(--warn, #c69214)', borderRadius: '12px',
      padding: '14px',
    }
  });
  box.appendChild(el('div', {
    style: { fontSize: '1.1rem', fontWeight: '700', color: 'var(--ink)', marginBottom: '8px' }
  }, '还没有保存——登录后才会存到服务器上'));
  var ta = el('textarea', {
    style: {
      width: '100%', minHeight: '90px', fontSize: '1.1rem', lineHeight: '1.6',
      padding: '10px', borderRadius: '10px', border: '2px solid var(--border, #ccc)',
    }
  });
  ta.value = text;   // 草稿保留在屏上，不假装已保存
  box.appendChild(ta);
  box.appendChild(el('div', { style: { marginTop: '10px', display: 'flex', gap: '10px' } }, [
    el('button', {
      className: 'cg-btn btn-primary',
      style: { fontSize: '1.05rem', padding: '0.7rem 1.2rem' },
      onclick: function() {
        import('../ui/auth-modal.js').then(function(mod) { mod.showAuthModal(); });
      }
    }, '去登录'),
    el('span', {
      style: { fontSize: '0.95rem', color: 'var(--muted)', alignSelf: 'center' }
    }, '登录后再点保存'),
  ]));
  container.appendChild(box);
}

function showVoiceEditor(transcript, confidenceMap, asrInfo) {
  var container = document.getElementById('elderly-voice-editor');
  if (!container) return;
  container.innerHTML = '';

  // 置信度标注：后端启发式置信度低于阈值时，提示可修改（标量无词级映射，
  // 词级高亮等 provider 支持后再加）
  if (asrInfo && asrInfo.confidence != null && asrInfo.confidence < 0.5) {
    container.appendChild(el('div', {
      style: { fontSize: '0.95rem', color: 'var(--muted)', marginBottom: '8px' }
    }, '有些字可能没听准，下面的文字可以改一改。'));
  }

  var editor = createVoiceEditor(transcript, confidenceMap);
  container.appendChild(editor);

  function submitFromEditor() {
    var text = editor.getCorrectedText();
    container.innerHTML = '';
    // story-2：不在保存前预写今日回忆——只有 createSession 成功才更新
    submitSession(text,
      asrInfo ? asrInfo.audioMetrics : null,
      asrInfo ? { asr_provider: asrInfo.provider, asr_confidence: asrInfo.confidence } : null,
      { statusEl: container });
  }

  // 两按钮行为暂同（合并/差异化归后续 story），但都走同一条诚实保存路径
  editor.confirmButton.onclick = submitFromEditor;
  editor.directButton.onclick = submitFromEditor;
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
