// ============ LEFT PANEL ============
// 左侧面板：语音输入、节点调色板、关系类型、数据导出
import { state, SCENARIOS, NODE_TYPES, EDGE_TYPES } from '../../state.js';
import { el } from '../components.js';
import { parseText } from '../../nlp/parse.js';
import { computeMetrics, computeHealth } from '../../graph/metrics.js';
import { addNode, getSelfNode } from '../../graph/model.js';
import { pushHistory, saveState, exportJSON, exportCSV, exportPNG } from '../interactions.js';
import { renderRightPanelOnly } from './rightPanel.js';
import { render } from '../render.js';
import { createTTSButton } from '../tts-button.js';
import { createVoiceEditor } from '../voice-editor.js';
import { withLoading } from '../loading.js';
import { showToast } from '../toast.js';
import { trapFocus } from '../interactions.js';
import { uploadAudio, isLoggedIn, exportBackup, importBackup, exportLogs, getRecoveryCode } from '../../api/client.js';

function getGraphApis() {
  return window.__graphApis || {
    startAnimation: function() {},
    stopAnimation: function() {},
    applyZoomPan: function() {},
    throttle: function(fn) { return fn; },
  };
}

// ============ 训练游戏模态框 ============
function openTrainingModal() {
  var existing = document.getElementById('game-modal-overlay');
  if (existing) existing.remove();

  var overlay = el('div', {
    id: 'game-modal-overlay',
    style: {
      position: 'fixed', inset: '0', zIndex: '200',
      background: 'rgba(31, 27, 22, 0.45)', backdropFilter: 'blur(3px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px',
    },
    onclick: function(e) {
      if (e.target === overlay) overlay.remove();
    },
  });

  var modal = el('div', {
    style: {
      background: 'var(--bg)', borderRadius: '16px', width: '100%', maxWidth: '480px',
      maxHeight: '85vh', display: 'flex', flexDirection: 'column',
      boxShadow: '0 20px 60px rgba(0,0,0,0.25)', overflow: 'hidden',
    },
  });

  var header = el('div', {
    style: {
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '18px 24px', borderBottom: '1px solid var(--rule)', flexShrink: '0',
    },
  }, [
    el('div', { style: { fontSize: '1.1rem', fontWeight: '800', color: 'var(--ink)' } }, '🧠 记忆训练'),
    el('button', {
      style: {
        background: 'none', border: 'none', fontSize: '1.3rem', color: 'var(--muted)',
        cursor: 'pointer', padding: '4px 8px', borderRadius: '6px', lineHeight: '1',
      },
      onclick: function() { overlay.remove(); },
    }, '✕'),
  ]);
  modal.appendChild(header);

  var body = el('div', {
    style: { padding: '20px 24px', overflowY: 'auto', flex: '1' },
  });

  // 游戏选择
  var gameMenu = el('div', { id: 'game-menu', style: { display: 'flex', flexDirection: 'column', gap: '12px' } });

  var memoryBtn = el('button', {
    className: 'btn-secondary',
    style: { textAlign: 'left', padding: '16px', display: 'flex', alignItems: 'center', gap: '12px' },
    onclick: function() {
      gameMenu.style.display = 'none';
      var gameContainer = el('div', { id: 'game-container' });
      body.appendChild(gameContainer);
      import('../../games/memory-challenge.js').then(function(mod) {
        mod.initMemoryChallenge(gameContainer);
      }).catch(function(err) {
        console.error('记忆挑战加载失败', err);
        gameContainer.innerHTML = '';
        gameContainer.appendChild(el('div', { style: { color: 'var(--danger)', textAlign: 'center', padding: '20px' } },
          '游戏加载失败，请刷新页面重试'));
      });
    },
  }, [
    el('span', { style: { fontSize: '1.5rem' } }, '🎯'),
    el('div', {}, [
      el('div', { style: { fontWeight: '700', fontSize: '0.95rem' } }, '记忆挑战'),
      el('div', { style: { fontSize: '0.75rem', color: 'var(--muted)' } }, '回忆节点出现的日期'),
    ]),
  ]);
  gameMenu.appendChild(memoryBtn);

  var numberBtn = el('button', {
    className: 'btn-secondary',
    style: { textAlign: 'left', padding: '16px', display: 'flex', alignItems: 'center', gap: '12px' },
    onclick: function() {
      gameMenu.style.display = 'none';
      var gameContainer = el('div', { id: 'game-container' });
      body.appendChild(gameContainer);
      import('../../games/number-link.js').then(function(mod) {
        mod.initNumberLink(gameContainer);
      }).catch(function(err) {
        console.error('数字连线加载失败', err);
        gameContainer.innerHTML = '';
        gameContainer.appendChild(el('div', { style: { color: 'var(--danger)', textAlign: 'center', padding: '20px' } },
          '游戏加载失败，请刷新页面重试'));
      });
    },
  }, [
    el('span', { style: { fontSize: '1.5rem' } }, '🔢'),
    el('div', {}, [
      el('div', { style: { fontWeight: '700', fontSize: '0.95rem' } }, '数字连线'),
      el('div', { style: { fontSize: '0.75rem', color: 'var(--muted)' } }, '按时间顺序连接记忆节点'),
    ]),
  ]);
  gameMenu.appendChild(numberBtn);

  body.appendChild(gameMenu);
  modal.appendChild(body);
  overlay.appendChild(modal);
  document.body.appendChild(overlay);

  // 焦点管理
  var restoreFocus = trapFocus(modal, document.activeElement);
  overlay._restoreFocus = restoreFocus;

  // ESC 关闭
  overlay.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
      overlay.remove();
      if (restoreFocus) restoreFocus();
    }
  });
}

// 语音输入卡片：textarea + 录音按钮 + 解析按钮 + 示例 + NLP结果
function renderVoiceCard() {
  var card = el('div', { className: 'voice-card' });
  var textarea = el('textarea', {
    className: 'voice-textarea',
    placeholder: '说出今天发生的事…例如：今天在公园碰见老张，我们一起打太极',
    id: 'voice-input',
    maxLength: 500,
    'aria-label': '语音叙述输入框，输入今天发生的事情',
    onkeydown: function(e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        var btn = document.getElementById('parse-btn');
        if (btn && !btn.disabled) btn.click();
      }
    }
  });
  card.appendChild(textarea);

  // 音频可视化区域（初始隐藏）
  var visualizerWrap = el('div', { className: 'audio-visualizer-wrap hidden', id: 'audio-visualizer-wrap' });
  var canvas = el('canvas', { className: 'audio-visualizer', id: 'audio-visualizer' });
  visualizerWrap.appendChild(canvas);

  // 录音状态指示
  var recordingIndicator = el('div', { className: 'recording-indicator hidden', id: 'recording-indicator' }, [
    el('span', { className: 'recording-dot' }),
    el('span', { className: 'recording-text' }, '正在聆听…')
  ]);
  visualizerWrap.appendChild(recordingIndicator);

  // 音量过低提示
  var volumeHint = el('div', { className: 'volume-hint hidden', id: 'volume-hint' }, '请靠近麦克风');
  visualizerWrap.appendChild(volumeHint);
  card.appendChild(visualizerWrap);

  var audioVisualizer = null;

  // 语音录入：优先用浏览器原生 SpeechRecognition，不支持时回退到 MediaRecorder
  var speechSupported = 'SpeechRecognition' in window || 'webkitSpeechRecognition' in window;
  var mediaRecorderSupported = 'MediaRecorder' in window && navigator.mediaDevices && navigator.mediaDevices.getUserMedia;
  if (speechSupported || mediaRecorderSupported) {
    var recBtn = el('button', {
      className: 'btn-secondary',
      id: 'voice-rec-btn',
      'aria-label': state.sttAvailable ? '语音录音，点击开始或停止' : '麦克风服务暂不可用，请直接输入文字',
      title: state.sttAvailable ? '' : '语音识别服务暂不可用，请直接输入文字',
      disabled: !state.sttAvailable,
      style: {
        marginBottom: '8px',
        display: 'flex',
        alignItems: 'center',
        gap: '6px',
        opacity: state.sttAvailable ? '1' : '0.6',
        cursor: state.sttAvailable ? 'pointer' : 'not-allowed',
      },
      onclick: function() {
        if (!state.sttAvailable) return;
        var btn = document.getElementById('voice-rec-btn');

        // --- 浏览器原生语音识别（Chrome / Edge）---
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
            showRecordingUI(true);
            if (btn) { btn.textContent = '🔴 录音中…（点击停止）'; btn.style.background = '#ffebee'; btn.style.color = '#c62828'; }
          };
          rec.onresult = function(e) {
            var transcript = '';
            for (var i = e.resultIndex; i < e.results.length; i++) {
              transcript += e.results[i][0].transcript;
            }
            document.getElementById('voice-input').value = transcript;
            window.__last_voice_result__ = { text: transcript, confidenceMap: null };
          };
          rec.onend = function() {
            rec.running = false;
            window.__speech_rec__ = null;
            showRecordingUI(false);
            stopVisualizer();
            if (btn) { btn.textContent = '🎤 按住说话'; btn.style.background = ''; btn.style.color = ''; }
          };
          rec.onerror = function(e) {
            rec.running = false;
            window.__speech_rec__ = null;
            showRecordingUI(false);
            stopVisualizer();
            if (btn) { btn.textContent = '🎤 按住说话'; btn.style.background = ''; btn.style.color = ''; }
            console.warn('Speech recognition error:', e.error);
          };

          // 请求麦克风以获取可视化
          if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
            navigator.mediaDevices.getUserMedia({ audio: true }).then(function(stream) {
              startVisualizer(stream);
              rec.start();
            }).catch(function() {
              rec.start();
            });
          } else {
            rec.start();
          }
          return;
        }

        // --- MediaRecorder 回退方案（Firefox / Safari）---
        import('../../audio/recorder.js').then(function(mod) {
          var recorder = new mod.VoiceRecorder({ maxDuration: 30000, silenceTimeout: 1500 });
          recorder.onStart = function() {
            showRecordingUI(true);
            if (btn) { btn.textContent = '🔴 录音中…（点击停止）'; btn.style.background = '#ffebee'; btn.style.color = '#c62828'; }
          };
          recorder.onStop = function(blob) {
            showRecordingUI(false);
            stopVisualizer();
            if (btn) { btn.textContent = '🎤 录音'; btn.style.background = ''; btn.style.color = ''; }
            // 上传到后端做 STT
            uploadAudio(blob).then(function(result) {
              document.getElementById('voice-input').value = result.text || '';
              window.__last_voice_result__ = {
                text: result.text || '',
                confidenceMap: result.confidence_map || result.words || null
              };
              if (result.audio_metrics) {
                state.lastAudioMetrics = result.audio_metrics;
              }
            }).catch(function(err) {
              console.error('STT upload failed:', err);
              var msg = err && err.message ? err.message : '语音识别服务暂不可用';
              alert('语音识别失败：' + msg + '，您可以手动输入文字。');
              state.sttAvailable = false;
              render();
            });
          };
          recorder.onError = function(msg) {
            showRecordingUI(false);
            stopVisualizer();
            if (btn) { btn.textContent = '🎤 录音'; btn.style.background = ''; btn.style.color = ''; }
            console.error('Recorder error:', msg);
          };
          if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
            navigator.mediaDevices.getUserMedia({ audio: true }).then(function(stream) {
              startVisualizer(stream);
              recorder.start();
            }).catch(function() {
              recorder.start();
            });
          } else {
            recorder.start();
          }
          btn._recorder = recorder;
        });
      }
    }, state.sttAvailable
        ? (speechSupported ? '🎤 按住说话' : '🎤 录音')
        : '麦克风服务暂不可用');
    card.appendChild(recBtn);
  }

  function showRecordingUI(show) {
    var wrap = document.getElementById('audio-visualizer-wrap');
    var indicator = document.getElementById('recording-indicator');
    var hint = document.getElementById('volume-hint');
    if (wrap) wrap.classList.toggle('hidden', !show);
    if (indicator) indicator.classList.toggle('hidden', !show);
    if (hint) hint.classList.add('hidden');
  }

  function startVisualizer(stream) {
    import('../../audio/visualizer.js').then(function(mod) {
      var canvas = document.getElementById('audio-visualizer');
      if (!canvas) return;
      audioVisualizer = mod.createAudioVisualizer(canvas);
      canvas.onVolumeLow = function() {
        var hint = document.getElementById('volume-hint');
        if (hint) hint.classList.remove('hidden');
      };
      canvas.onVolumeNormal = function() {
        var hint = document.getElementById('volume-hint');
        if (hint) hint.classList.add('hidden');
      };
      audioVisualizer.start(stream).catch(function() {});
    }).catch(function() {});
  }

  function stopVisualizer() {
    if (audioVisualizer) {
      audioVisualizer.stop();
      audioVisualizer = null;
    }
  }

  var actions = el('div', { className: 'voice-actions' });
  var parseBtn = el('button', {
    className: 'btn-primary',
    id: 'parse-btn',
    onclick: function() {
      var text = document.getElementById('voice-input').value;
      if (!text.trim()) return;

      // 语音输入：先显示 voice-editor 让用户确认/修正
      var isVoice = window.__last_voice_result__ && window.__last_voice_result__.text === text.trim();
      if (isVoice && !window.__skip_voice_editor__) {
        var existing = document.getElementById('voice-editor-panel');
        if (!existing) {
          var card = document.querySelector('.voice-card');
          if (card) {
            var editor = createVoiceEditor(window.__last_voice_result__.text, window.__last_voice_result__.confidenceMap);
            card.appendChild(editor);
            editor.confirmButton.onclick = function() {
              document.getElementById('voice-input').value = editor.getCorrectedText();
              window.__last_voice_result__ = null;
              editor.remove();
              parseBtn.click();
            };
            editor.directButton.onclick = function() {
              window.__skip_voice_editor__ = true;
              document.getElementById('voice-input').value = editor.getCorrectedText();
              window.__last_voice_result__ = null;
              editor.remove();
              parseBtn.click();
              window.__skip_voice_editor__ = false;
            };
            return;
          }
        }
      }

      withLoading(parseBtn, function() {
        return new Promise(function(resolve) { setTimeout(resolve, 200); })
          .then(function() { return parseText(text); })
          .then(function(result) {
            pushHistory();
            // 非引导模式下保存到会话历史
            if (!state.guidedMode) {
              var m = computeMetrics();
              var h = computeHealth(m);
              state.sessionHistory.push({
                date: new Date().toISOString(),
                dayNumber: state.sessionHistory.length + 1,
                healthScore: h,
                anomalies: state.anomalies.slice(),
                emotion: result.emotion || state.lastEmotion || null,
                graph: {
                  nodes: state.nodes.map(function(n) {
                    return { id: n.id, label: n.label, type: n.type, x: n.x, y: n.y,
                             isAnon: n.isAnon, matchedTo: n.matchedTo, matchConfidence: n.matchConfidence };
                  }),
                  edges: state.edges.slice(),
                  nodeIdCounter: state.nodeIdCounter,
                },
                metrics: m,
              });
            }
            saveState();
            var nlpDiv = document.getElementById('nlp-result');
            if (nlpDiv) {
              var entityStr = result.tokens.map(function(t) { return t.word; }).join('、');
              var entityCount = result.tokens.length;
              var relCount = result.relations.length;
              var speakText = '识别到' + entityCount + '个实体，' + relCount + '条关系';
              nlpDiv.innerHTML = '';
              nlpDiv.appendChild(el('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '8px', marginBottom: '4px' } }, [
                el('div', { className: 'nlp-result-title' }, 'FMM分词 + 依存匹配结果'),
                createTTSButton(speakText, { size: 'small' }),
              ]));
              var body = el('div', { style: { fontSize: '0.8rem', lineHeight: '1.6' } });
              body.appendChild(document.createTextNode('实体：' + entityStr));
              body.appendChild(document.createElement('br'));
              body.appendChild(document.createTextNode('关系：' + relCount + '条'));
              if (result.anonNode) {
                body.appendChild(document.createElement('br'));
                body.appendChild(document.createTextNode('匿名节点：?X → ' + result.anonNode.matchedTo + ' (' + result.anonNode.matchConfidence + '%)'));
              }
              nlpDiv.appendChild(body);
              nlpDiv.classList.add('show');
            }
            document.getElementById('voice-input').value = '';
            window.__last_voice_result__ = null;
            getGraphApis().startAnimation();
            renderRightPanelOnly();
          }).catch(function(err) {
            console.error('parseText error:', err);
            showToast('识别失败：' + (err && err.message ? err.message : '请重试'), 'error');
            throw err;
          });
      }, '识别中…');
    }
  }, '识别并织网');
  actions.appendChild(parseBtn);

  var directBtn = el('button', {
    className: 'btn-secondary',
    id: 'direct-submit-btn',
    onclick: function() {
      window.__skip_voice_editor__ = true;
      parseBtn.click();
      window.__skip_voice_editor__ = false;
    }
  }, '直接提交');
  actions.appendChild(directBtn);

  var exampleBtn = el('button', {
    className: 'btn-secondary',
    onclick: function() {
      document.getElementById('voice-input').value = SCENARIOS[state.currentDay].text;
    }
  }, '示例');
  actions.appendChild(exampleBtn);
  card.appendChild(actions);

  var nlpDiv = el('div', { className: 'nlp-result', id: 'nlp-result' });
  card.appendChild(nlpDiv);
  return card;
}

// 节点调色板：人物 / 地点 / 事件 / 物品
function renderNodePalette() {
  var palette = el('div', { className: 'palette-grid' });
  ['person','place','event','item'].forEach(function(type) {
    var info = NODE_TYPES[type];
    var btn = el('button', {
      className: 'palette-btn',
      tabindex: '0',
      'aria-label': '添加' + info.label + '节点',
      onclick: function() {
        var label = prompt('输入节点名称:');
        if (label) { addNode(label, type); pushHistory(); saveState(); getGraphApis().startAnimation(); }
      }
    }, [
      el('span', { className: 'palette-icon', style: { background: info.color } }, info.icon),
      info.label,
    ]);
    palette.appendChild(btn);
  });
  return palette;
}

// 关系类型选择列表
function renderEdgeList() {
  var edgeList = el('div', { className: 'edge-list' });
  Object.keys(EDGE_TYPES).forEach(function(type) {
    var info = EDGE_TYPES[type];
    var btn = el('button', {
      className: 'edge-btn' + (state.selectedEdgeType === type ? ' active' : ''),
      tabindex: '0',
      'aria-label': '选择关系类型: ' + info.label,
      onclick: function() { state.selectedEdgeType = type; render(); }
    }, [
      el('span', {
        className: 'edge-line',
        style: { borderTop: info.width + 'px ' + (info.dash === 'none' ? 'solid' : 'dashed') + ' ' + info.color }
      }),
      info.label,
    ]);
    edgeList.appendChild(btn);
  });
  return edgeList;
}

// 数据导出区域：JSON / CSV / PNG / 重置，以及登录用户的备份恢复
function renderExportSection(panel) {
  var exportGrid = el('div', { style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' } });
  exportGrid.appendChild(el('button', {
    className: 'btn-secondary',
    onclick: exportJSON,
  }, 'JSON'));
  exportGrid.appendChild(el('button', {
    className: 'btn-secondary',
    onclick: exportCSV,
  }, 'CSV'));
  exportGrid.appendChild(el('button', {
    className: 'btn-secondary',
    onclick: exportPNG,
  }, 'PNG'));
  exportGrid.appendChild(el('button', {
    className: 'btn-secondary',
    onclick: function() {
      if (confirm('清空所有数据？此操作不可撤销。')) {
        localStorage.removeItem('cognitive-garden-state');
        state.nodes = [getSelfNode()];
        state.edges = [];
        state.nodeIdCounter = 1;
        state.daySnapshots = {};
        state.baselineMetrics = null;
        render();
        getGraphApis().startAnimation();
      }
    },
  }, '重置'));

  // 账户与安全（登录用户可用备份恢复；未登录显示登录/注册）
  var backupSection = el('div', { className: 'panel-section' });
  backupSection.appendChild(el('div', { className: 'panel-title' }, '账户与安全'));
  if (isLoggedIn()) {
    var backupGrid = el('div', { style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' } });
    backupGrid.appendChild(el('button', {
      className: 'btn-secondary',
      id: 'export-backup-btn',
      onclick: function() {
        var btn = document.getElementById('export-backup-btn');
        withLoading(btn, function() {
          return exportBackup().catch(function(err) {
            showToast('导出备份失败：' + (err && err.message ? err.message : '请重试'), 'error');
            throw err;
          });
        }, '导出中…');
      },
    }, '导出备份'));
    var importInput = el('input', { type: 'file', accept: '.json', style: { display: 'none' }, onchange: function(e) {
      var file = e.target.files[0];
      if (!file) return;
      if (!confirm('导入备份将覆盖当前账号下的所有记忆数据、基准线和状态，此操作不可撤销。确定继续吗？')) return;
      var btn = document.getElementById('import-backup-btn');
      withLoading(btn, function() {
        return importBackup(file)
          .then(function(res) {
            showToast('导入成功：恢复 ' + (res.imported ? res.imported.sessions : 0) + ' 条记忆，页面即将刷新', 'success');
            setTimeout(function() { location.reload(); }, 1200);
          })
          .catch(function(err) {
            showToast('导入失败：' + (err && err.message ? err.message : '请重试'), 'error');
            throw err;
          });
      }, '导入中…');
    }});
    backupGrid.appendChild(el('button', {
      className: 'btn-secondary',
      id: 'import-backup-btn',
      onclick: function() { importInput.click(); },
    }, '导入恢复'));
    backupGrid.appendChild(el('button', {
      className: 'btn-secondary',
      id: 'export-logs-btn',
      onclick: function() {
        var btn = document.getElementById('export-logs-btn');
        withLoading(btn, function() {
          return exportLogs().catch(function(err) {
            showToast('导出日志失败：' + (err && err.message ? err.message : '请重试'), 'error');
            throw err;
          });
        }, '导出中…');
      },
    }, '导出日志'));
    backupGrid.appendChild(el('button', {
      className: 'btn-secondary',
      id: 'recovery-code-btn',
      onclick: function() {
        var btn = document.getElementById('recovery-code-btn');
        withLoading(btn, function() {
          return getRecoveryCode()
            .then(function(d) {
              showToast(d.has_recovery_code
                ? '已设置恢复码（注册时展示过一次，请妥善保管）'
                : '当前账户未设置恢复码', 'info', 4000);
            })
            .catch(function(err) {
              showToast('查询失败：' + (err && err.message ? err.message : '请重试'), 'error');
              throw err;
            });
        }, '查询中…');
      },
    }, '恢复码状态'));
    backupSection.appendChild(backupGrid);
    backupSection.appendChild(importInput);
  } else {
    var authBtn = el('button', {
      className: 'btn-secondary',
      style: { width: '100%', marginTop: '4px' },
      onclick: function() {
        import('../auth-modal.js').then(function(mod) { mod.showAuthModal(); });
      },
    }, '登录 / 注册');
    backupSection.appendChild(authBtn);
  }
  panel.appendChild(backupSection);

  return exportGrid;
}

function renderLeftPanel() {
  var panel = el('div', { className: 'panel-left' });

  // 家属端：本周记忆概览
  if (state.view === 'family') {
    var fm = computeMetrics();
    var fHealth = computeHealth(fm);
    var fDays = Object.keys(state.daySnapshots).length;
    var fEdges = fm ? fm.edgeCount : 0;
    var fAnon = fm ? fm.anonCount : 0;
    panel.appendChild(el('div', { className: 'panel-section' }, [
      el('div', { className: 'panel-title' }, '本周记忆概览'),
      el('div', { className: 'fam-hero' }, [
        el('div', { className: 'fam-hero-num' }, String(fHealth)),
        el('div', { className: 'fam-hero-label' }, '综合健康度'),
      ]),
      el('div', { className: 'fam-stats' }, [
        el('div', { className: 'fam-stat' }, [el('div', { className: 'fam-stat-num' }, String(fDays)), el('div', { className: 'fam-stat-label' }, '记录天数')]),
        el('div', { className: 'fam-stat' }, [el('div', { className: 'fam-stat-num' }, String(fEdges)), el('div', { className: 'fam-stat-label' }, '关系连接')]),
        el('div', { className: 'fam-stat' }, [el('div', { className: 'fam-stat-num' }, String(fAnon)), el('div', { className: 'fam-stat-label' }, '匿名节点')]),
      ]),
    ]));
    return panel;
  }

  // 医生端：实时拓扑指标 + 认知量表入口
  if (state.view === 'doctor') {
    var m = computeMetrics();
    var grid = el('div', { className: 'doc-metric-grid' });
    var metrics = [
      { name: '连通度', val: m ? Math.round(m.connectivity * 100) + '%' : '—' },
      { name: '聚类系数', val: m ? Math.round(m.clustering * 100) + '%' : '—' },
      { name: '自我中心度', val: m ? Math.round(m.centrality * 100) + '%' : '—' },
      { name: '时序熵', val: m ? Math.round(m.entropy * 100) + '%' : '—' },
      { name: '密度', val: m ? (m.density * 100).toFixed(1) + '%' : '—' },
      { name: '平均路径', val: m ? m.avgPathLen.toFixed(2) : '—' },
      { name: '全局效率', val: m ? Math.round(m.globalEff * 100) + '%' : '—' },
      { name: '小世界Σ', val: m ? m.smallWorld.toFixed(2) : '—' },
      { name: '节点数', val: m ? String(m.nodeCount) : '—' },
    ];
    metrics.forEach(function(mt) {
      grid.appendChild(el('div', { className: 'doc-metric' }, [
        el('div', { className: 'doc-metric-name' }, mt.name),
        el('div', { className: 'doc-metric-val' }, mt.val),
      ]));
    });
    panel.appendChild(el('div', { className: 'panel-section' }, [
      el('div', { className: 'panel-title' }, '实时拓扑指标'),
      grid,
    ]));
    // 认知量表评估入口
    panel.appendChild(el('div', { className: 'panel-section' }, [
      el('div', { className: 'panel-title' }, '认知量表评估'),
      el('button', {
        className: 'scale-entry-btn',
        onclick: function() {
          import('../scale.js').then(function(mod) { mod.openScalePanel(); });
        },
      }, '📋 开始认知量表评估（MMSE / AD8）'),
    ]));
    // 记忆衰退分析入口
    panel.appendChild(el('div', { className: 'panel-section' }, [
      el('div', { className: 'panel-title' }, '记忆衰退分析'),
      el('button', {
        className: 'decline-entry-btn',
        onclick: function() {
          import('../decline.js').then(function(mod) { mod.openDeclinePanel(); });
        },
      }, '🧠 查看记忆衰退分析（近 7 天对比）'),
    ]));
    return panel;
  }

  // 老人端：语音输入 + 节点调色板 + 关系类型 + 数据导出
  var section = el('div', { className: 'panel-section' });
  section.appendChild(el('div', { className: 'panel-title' }, '语音叙述今日'));
  section.appendChild(renderVoiceCard());

  section.appendChild(el('div', { className: 'panel-title', style: { marginTop: '16px' } }, '手动添加节点'));
  section.appendChild(renderNodePalette());

  section.appendChild(el('div', { className: 'panel-title', style: { marginTop: '16px' } }, '关系类型'));
  section.appendChild(renderEdgeList());

  section.appendChild(el('div', { className: 'panel-title', style: { marginTop: '16px' } }, '数据导出'));
  section.appendChild(renderExportSection(panel));

  // 自定义词典入口：让 NLP 适配每个家庭的专属实体
  section.appendChild(el('div', { className: 'panel-title', style: { marginTop: '16px' } }, '个性化'));
  section.appendChild(el('button', {
    className: 'scale-entry-btn',
    style: { background: 'var(--accent3-l)', color: 'var(--accent3)' },
    onclick: function() {
      import('../lexicon-manager.js').then(function(mod) { mod.openLexiconPanel(); });
    },
  }, '📖 我的词典（家人名字 / 常去地点）'));

  // 记忆训练游戏入口
  section.appendChild(el('div', { className: 'panel-title', style: { marginTop: '16px' } }, '记忆训练'));
  section.appendChild(el('button', {
    className: 'scale-entry-btn',
    style: { background: 'var(--accent2-l)', color: 'var(--accent2)' },
    onclick: function() {
      openTrainingModal();
    },
  }, '🧠 开始记忆训练'));

  section.appendChild(el('div', { className: 'keyboard-hint' }, '快捷键: Ctrl+Z 撤销 | Delete 删除节点 | Esc 取消选择'));
  panel.appendChild(section);
  return panel;
}

export { renderVoiceCard, renderNodePalette, renderEdgeList, renderExportSection, renderLeftPanel };
