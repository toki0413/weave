// ============ FAMILY MODE (3D Nebula Immersive) ============
// 家属端：默认 3D 星云浏览，飞行漫游，时间筛选，情感色彩
import { el } from '../ui/components.js';
import { listSessions, getHealthTrend, getNotifications, getLatestGraph, sendWebSocketCare } from '../api/client.js';
import { connect as wsConnect, send as wsSend, isConnected, isUsingSSE } from '../services/websocket.js';
import { getToken } from '../api/client.js';

export function renderFamilyMode(container, elderlyData) {
  container.innerHTML = '';
  document.documentElement.classList.remove('elderly-mode', 'doctor-mode');
  document.documentElement.classList.add('family-mode');
  document.body.className = 'mode-family';

  var data = elderlyData || {};
  var healthScore = data.healthScore != null ? data.healthScore : 85;
  var anomalies = data.anomalies || [];
  var memories = data.memories || [];
  var unreadCount = data.unreadCount || 0;
  var graphNodes = data.graphNodes || [];
  var graphEdges = data.graphEdges || [];

  var color = healthScore >= 80 ? '#4A7C4A' : healthScore >= 60 ? '#B8860B' : '#C75B5B';
  var bg = healthScore >= 80 ? 'rgba(74,124,74,0.15)' : healthScore >= 60 ? 'rgba(184,134,11,0.15)' : 'rgba(199,91,91,0.15)';

  var app = el('div', {
    className: 'family-app',
    style: {
      display: 'flex',
      flexDirection: 'column',
      height: '100vh',
      padding: '20px',
      gap: '12px',
      overflow: 'hidden',
    }
  });

  // 顶部栏：实时同步指示器 + 未读徽章
  var headerBar = el('div', {
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingBottom: '8px',
      borderBottom: '1px solid var(--rule)',
      flexShrink: 0,
    }
  });
  var syncIndicator = el('div', {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: '8px',
      fontSize: '0.85rem',
      color: 'var(--muted)',
    }
  });
  var syncDot = el('span', {
    style: {
      display: 'inline-block',
      width: '10px',
      height: '10px',
      borderRadius: '50%',
      background: '#ccc',
    }
  });
  syncIndicator.appendChild(syncDot);
  syncIndicator.appendChild(document.createTextNode('同步中…'));
  headerBar.appendChild(syncIndicator);

  var badge = el('div', {
    style: {
      background: 'var(--danger)',
      color: '#fff',
      borderRadius: '12px',
      padding: '2px 10px',
      fontSize: '0.8rem',
      fontWeight: '700',
      display: unreadCount > 0 ? 'block' : 'none',
    }
  }, String(unreadCount));
  headerBar.appendChild(badge);
  app.appendChild(headerBar);

  // 首屏：健康分大数字（紧凑）
  var hero = el('div', {
    style: {
      background: bg,
      borderRadius: '12px',
      padding: '12px 16px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      flexShrink: 0,
    }
  });
  hero.appendChild(el('div', {
    style: { fontSize: '0.85rem', color: 'var(--muted)' }
  }, '今日健康分'));
  hero.appendChild(el('div', {
    style: { fontSize: '2rem', fontWeight: '800', color: color }
  }, String(healthScore)));
  app.appendChild(hero);

  // 今日异常提醒（紧凑）
  if (anomalies.length > 0) {
    var alertBox = el('div', {
      style: {
        background: 'var(--danger-l)',
        borderRadius: '10px',
        padding: '10px 14px',
        color: 'var(--danger)',
        fontSize: '0.85rem',
        flexShrink: 0,
      }
    });
    alertBox.appendChild(el('span', { style: { fontWeight: '700' } }, '⚠️ '));
    alertBox.appendChild(document.createTextNode(anomalies.map(function(a) { return a.message || String(a); }).join(' · ')));
    app.appendChild(alertBox);
  }

  // 3D 星云视口
  var nebulaWrap = el('div', {
    style: {
      flex: 1,
      position: 'relative',
      borderRadius: '12px',
      overflow: 'hidden',
      background: '#0a0908',
      minHeight: '0',
    }
  });

  // 浮动控制面板
  var controls = el('div', {
    style: {
      position: 'absolute',
      top: '10px',
      left: '10px',
      zIndex: 20,
      display: 'flex',
      flexDirection: 'column',
      gap: '8px',
      background: 'rgba(15,14,12,0.75)',
      backdropFilter: 'blur(8px)',
      borderRadius: '12px',
      padding: '10px',
      border: '1px solid rgba(255,255,255,0.08)',
    }
  });

  // 飞行漫游按钮
  var flyBtn = el('button', {
    style: {
      padding: '8px 14px',
      borderRadius: '8px',
      border: '1px solid rgba(255,255,255,0.15)',
      background: 'rgba(74,124,74,0.25)',
      color: '#fff',
      fontSize: '0.8rem',
      fontWeight: '600',
      cursor: 'pointer',
      transition: 'all 0.2s',
      whiteSpace: 'nowrap',
    },
    onclick: function() {
      if (_nebulaController) {
        _nebulaController.startFly();
        flyBtn.textContent = '✈️ 漫游中…';
        flyBtn.style.background = 'rgba(184,134,11,0.3)';
        setTimeout(function() {
          flyBtn.textContent = '✈️ 飞行漫游';
          flyBtn.style.background = 'rgba(74,124,74,0.25)';
        }, 5000);
      }
    }
  }, '✈️ 飞行漫游');
  controls.appendChild(flyBtn);

  // 时间筛选
  var timeFilterWrap = el('div', {
    style: { display: 'flex', flexDirection: 'column', gap: '4px' }
  });
  timeFilterWrap.appendChild(el('div', {
    style: { fontSize: '0.7rem', color: 'rgba(255,255,255,0.5)' }
  }, '时间筛选'));
  var timeSlider = el('input', {
    type: 'range',
    min: '0',
    max: '2',
    value: '2',
    step: '1',
    style: {
      width: '100px',
      accentColor: '#4A7C4A',
    },
    oninput: function() {
      var val = parseInt(this.value, 10);
      var filter = val === 0 ? '7' : val === 1 ? '30' : 'all';
      if (_nebulaController) _nebulaController.setTimeFilter(filter);
    }
  });
  timeFilterWrap.appendChild(timeSlider);
  var timeLabel = el('div', {
    style: { fontSize: '0.7rem', color: 'rgba(255,255,255,0.6)', textAlign: 'center' }
  }, '全部');
  timeFilterWrap.appendChild(timeLabel);
  timeSlider.oninput = function() {
    var val = parseInt(this.value, 10);
    var filter = val === 0 ? '7' : val === 1 ? '30' : 'all';
    var label = val === 0 ? '近 7 天' : val === 1 ? '近 30 天' : '全部';
    timeLabel.textContent = label;
    if (_nebulaController) _nebulaController.setTimeFilter(filter);
  };
  controls.appendChild(timeFilterWrap);

  // 情感色彩开关
  var emotionToggleWrap = el('div', {
    style: { display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }
  });
  var emotionToggle = el('input', {
    type: 'checkbox',
    id: 'family-emotion-toggle',
    style: { accentColor: '#4A7C4A', cursor: 'pointer' },
    onchange: function() {
      if (_nebulaController) _nebulaController.setEmotionMode(this.checked);
    }
  });
  emotionToggleWrap.appendChild(emotionToggle);
  emotionToggleWrap.appendChild(el('label', {
    htmlFor: 'family-emotion-toggle',
    style: { fontSize: '0.75rem', color: 'rgba(255,255,255,0.7)', cursor: 'pointer' }
  }, '情感色彩'));
  controls.appendChild(emotionToggleWrap);

  nebulaWrap.appendChild(controls);

  // 叙事片段弹出面板（右侧）
  var narrativePanel = el('div', {
    id: 'family-narrative-panel',
    style: {
      position: 'absolute',
      top: '10px',
      right: '10px',
      bottom: '10px',
      width: '260px',
      background: 'rgba(15,14,12,0.85)',
      backdropFilter: 'blur(12px)',
      borderRadius: '12px',
      padding: '16px',
      border: '1px solid rgba(255,255,255,0.08)',
      color: '#fff',
      zIndex: 20,
      display: 'none',
      flexDirection: 'column',
      gap: '10px',
      overflowY: 'auto',
    }
  });

  var narrativeHeader = el('div', {
    style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid rgba(255,255,255,0.1)', paddingBottom: '8px' }
  });
  var narrativeTitle = el('div', { style: { fontWeight: '700', fontSize: '0.95rem' } }, '记忆片段');
  narrativeHeader.appendChild(narrativeTitle);
  var closeNarrative = el('button', {
    style: {
      background: 'none', border: 'none', color: 'rgba(255,255,255,0.5)',
      fontSize: '1.1rem', cursor: 'pointer', lineHeight: '1'
    },
    onclick: function() { narrativePanel.style.display = 'none'; }
  }, '✕');
  narrativeHeader.appendChild(closeNarrative);
  narrativePanel.appendChild(narrativeHeader);

  var narrativeType = el('div', { style: { fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)', marginTop: '4px' } }, '—');
  narrativePanel.appendChild(narrativeType);
  var narrativeDate = el('div', { style: { fontSize: '0.75rem', color: 'rgba(255,255,255,0.4)', marginBottom: '4px' } }, '—');
  narrativePanel.appendChild(narrativeDate);
  var narrativeContent = el('div', {
    style: { fontSize: '0.9rem', lineHeight: '1.6', color: 'rgba(255,255,255,0.85)', flex: 1 }
  }, '点击星云中的节点查看记忆叙事。');
  narrativePanel.appendChild(narrativeContent);

  nebulaWrap.appendChild(narrativePanel);
  app.appendChild(nebulaWrap);

  // 发送关怀区域
  var careSection = el('div', {
    style: {
      borderTop: '1px solid var(--rule)',
      paddingTop: '10px',
      flexShrink: 0,
    }
  });
  careSection.appendChild(el('div', {
    style: { fontWeight: '700', marginBottom: '6px', fontSize: '0.9rem' }
  }, '发送关怀'));
  var careInput = el('textarea', {
    style: {
      width: '100%',
      minHeight: '48px',
      borderRadius: '10px',
      border: '1px solid var(--rule)',
      padding: '8px',
      fontSize: '0.9rem',
      resize: 'vertical',
      boxSizing: 'border-box',
      marginBottom: '6px',
    },
    placeholder: '输入文字关怀，或发送语音留言…'
  });
  careSection.appendChild(careInput);

  var careBtnRow = el('div', {
    style: { display: 'flex', gap: '8px' }
  });
  careBtnRow.appendChild(el('button', {
    className: 'btn-primary',
    style: { flex: 1, padding: '8px' },
    onclick: function() {
      var text = careInput.value.trim();
      if (!text) return;
      var elderlyId = data.elderlyId || '';
      if (!elderlyId) {
        alert('请先绑定老人');
        return;
      }
      var msg = sendWebSocketCare(elderlyId, text, null);
      wsSend(msg);
      careInput.value = '';
      alert('已发送关怀');
    }
  }, '发送文字'));
  careBtnRow.appendChild(el('button', {
    className: 'btn-secondary',
    style: { flex: 1, padding: '8px' },
    onclick: function() {
      alert('语音留言功能：请使用录音按钮录制后发送');
    }
  }, '发送语音'));
  careSection.appendChild(careBtnRow);
  app.appendChild(careSection);

  // 底部操作栏
  var bar = el('div', {
    style: {
      display: 'flex',
      gap: '10px',
      paddingTop: '8px',
      borderTop: '1px solid var(--rule)',
      flexShrink: 0,
    }
  });
  bar.appendChild(el('button', {
    className: 'btn-secondary',
    style: { flex: 1 },
    onclick: function() {
      import('../ui/scale.js').then(function(mod) { mod.openScalePanel(); });
    }
  }, '查看量表'));
  bar.appendChild(el('button', {
    className: 'btn-secondary',
    style: { flex: 1 },
    onclick: function() {
      alert('历史记录功能开发中');
    }
  }, '查看历史'));
  app.appendChild(bar);

  container.appendChild(app);

  // 初始化 3D 星云
  var _nebulaController = null;
  function showNarrative(node) {
    narrativePanel.style.display = 'flex';
    narrativeTitle.textContent = node.label || '记忆节点';
    var typeLabels = { person: '人物', event: '事件', place: '地点', time: '时间', item: '物品', self: '自我', anon: '匿名' };
    narrativeType.textContent = (typeLabels[node.type] || '节点') + (node.emotion ? ' · ' + (node.emotion === 'positive' ? '积极' : node.emotion === 'negative' ? '消极' : '中性') : '');
    var d = new Date(node.date);
    narrativeDate.textContent = isNaN(d.getTime()) ? '—' : d.toLocaleDateString('zh-CN');
    narrativeContent.textContent = node.narrative || '暂无叙事内容';
  }

  import('../3d/memory-nebula.js').then(function(mod) {
    _nebulaController = mod.initMemoryNebula(nebulaWrap, graphNodes, memories);
    if (_nebulaController) {
      _nebulaController.setOnNodeClick(showNarrative);
    } else {
      // WebGL 不支持：回退到记忆列表
      nebulaWrap.innerHTML = '';
      nebulaWrap.style.background = 'var(--bg2)';
      nebulaWrap.style.padding = '16px';
      nebulaWrap.style.overflowY = 'auto';
      memories.slice(0, 10).forEach(function(m) {
        var card = el('div', {
          style: {
            background: 'var(--bg)',
            borderRadius: '10px',
            padding: '12px',
            marginBottom: '8px',
          }
        });
        var dateStr = m.date || m.created_at ? new Date(m.date || m.created_at).toLocaleDateString('zh-CN') : '今天';
        card.appendChild(el('div', { style: { fontSize: '0.75rem', color: 'var(--muted)', marginBottom: '4px' } }, dateStr));
        card.appendChild(el('div', { style: { fontSize: '0.9rem', lineHeight: '1.5', color: 'var(--ink)' } }, m.narrative_text || m.text || '—'));
        nebulaWrap.appendChild(card);
      });
    }
  }).catch(function(err) {
    console.error('3D module load failed:', err);
  });

  // 启动 WebSocket 连接
  var token = getToken();
  if (token) {
    wsConnect(token, function(msg) {
      if (msg.type === 'new_session' || msg.type === 'new_scale') {
        try {
          var audio = new Audio('/notification.mp3');
          audio.volume = 0.3;
          audio.play().catch(function() {});
        } catch (e) {}
        unreadCount++;
        badge.textContent = String(unreadCount);
        badge.style.display = 'block';
      }
      if (msg.type === 'read_receipt') {
        console.log('老人已读消息', msg.payload);
      }
    });
  }

  // 同步指示器更新
  function updateSyncIndicator() {
    if (isConnected()) {
      syncDot.style.background = '#4A7C4A';
      syncIndicator.lastChild.textContent = isUsingSSE() ? '已连接 (SSE)' : '已连接';
    } else {
      syncDot.style.background = '#C75B5B';
      syncIndicator.lastChild.textContent = '未连接';
    }
  }
  updateSyncIndicator();
  var indicatorInterval = setInterval(updateSyncIndicator, 3000);
  container._cleanup = function() { clearInterval(indicatorInterval); if (_nebulaController) _nebulaController.destroy(); };
}

// 辅助函数：供 main.js 调用以获取老人数据
export function fetchFamilyData() {
  return Promise.all([
    listSessions(10).catch(function() { return []; }),
    getHealthTrend(1).catch(function() { return null; }),
    getNotifications().catch(function() { return []; }),
    getLatestGraph().catch(function() { return null; })
  ]).then(function(results) {
    var sessions = results[0] || [];
    var trend = results[1] || {};
    var notifications = results[2] || [];
    var graph = results[3] || null;
    return {
      healthScore: trend.score != null ? trend.score : (sessions[0] && sessions[0].health_score ? sessions[0].health_score : 85),
      anomalies: trend.anomalies || notifications.slice(0, 3).map(function(n) {
        return { message: n.message || n.title || '异常提醒' };
      }),
      memories: sessions,
      unreadCount: notifications.filter(function(n) { return !n.is_read; }).length,
      graphNodes: graph && graph.nodes ? graph.nodes : [],
      graphEdges: graph && graph.edges ? graph.edges : [],
    };
  });
}
