// ============ DOCTOR MODE ============
// 医生端数据面板：量表趋势 + 异常标记 + 导出 + 发送建议
import { el } from '../ui/components.js';
import { getScaleHistory, getDeclineAnalysis, sendWebSocketAdvice, listSessions, getLatestGraph } from '../api/client.js';
import { connect as wsConnect, send as wsSend } from '../services/websocket.js';
import { getToken } from '../api/client.js';

export function renderDoctorMode(container) {
  container.innerHTML = '';
  document.documentElement.classList.remove('elderly-mode', 'family-mode');
  document.documentElement.classList.add('doctor-mode');
  document.body.className = 'mode-doctor';

  var app = el('div', {
    className: 'doctor-app',
    style: {
      display: 'flex',
      flexDirection: 'column',
      height: '100vh',
      padding: '20px',
      gap: '16px',
      overflowY: 'auto',
    }
  });

  // 记忆展示区域：默认 2D 卡片，可切换 3D 星云
  app.appendChild(el('h2', {
    style: { marginBottom: '8px', fontSize: '1.3rem', color: 'var(--ink)' }
  }, '患者记忆网络'));

  var memoryViewMode = '2d'; // '2d' | '3d'
  var memorySection = el('div', {
    style: {
      background: 'var(--bg2)',
      borderRadius: '12px',
      padding: '12px',
      position: 'relative',
      minHeight: '260px',
      overflow: 'hidden',
    }
  });

  // 2D 记忆卡片列表
  var memory2D = el('div', {
    id: 'doctor-memory-2d',
    style: { display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '240px', overflowY: 'auto' }
  });
  memory2D.appendChild(el('div', { style: { color: 'var(--muted)', fontSize: '0.9rem' } }, '加载记忆数据中…'));
  memorySection.appendChild(memory2D);

  // 3D 星云容器
  var memory3D = el('div', {
    id: 'doctor-memory-3d',
    style: {
      position: 'absolute',
      inset: '0',
      display: 'none',
      background: '#0a0908',
      borderRadius: '12px',
    }
  });
  memorySection.appendChild(memory3D);

  // 切换按钮
  var viewToggle = el('div', {
    style: {
      position: 'absolute',
      top: '10px',
      right: '10px',
      display: 'flex',
      gap: '4px',
      zIndex: 10,
    }
  });
  var btn2D = el('button', {
    style: {
      padding: '5px 12px',
      borderRadius: '6px',
      border: '1px solid var(--rule)',
      background: memoryViewMode === '2d' ? 'var(--accent)' : '#fff',
      color: memoryViewMode === '2d' ? '#fff' : 'var(--ink)',
      fontSize: '0.8rem',
      fontWeight: '600',
      cursor: 'pointer',
    },
    onclick: function() {
      memoryViewMode = '2d';
      memory2D.style.display = 'flex';
      memory3D.style.display = 'none';
      btn2D.style.background = 'var(--accent)'; btn2D.style.color = '#fff';
      btn3D.style.background = '#fff'; btn3D.style.color = 'var(--ink)';
      if (_doctorNebula) { _doctorNebula.destroy(); _doctorNebula = null; }
    }
  }, '2D 卡片');
  var _doctorNebula = null;
  var btn3D = el('button', {
    style: {
      padding: '5px 12px',
      borderRadius: '6px',
      border: '1px solid var(--rule)',
      background: memoryViewMode === '3d' ? 'var(--accent)' : '#fff',
      color: memoryViewMode === '3d' ? '#fff' : 'var(--ink)',
      fontSize: '0.8rem',
      fontWeight: '600',
      cursor: 'pointer',
    },
    onclick: function() {
      memoryViewMode = '3d';
      memory2D.style.display = 'none';
      memory3D.style.display = 'block';
      btn3D.style.background = 'var(--accent)'; btn3D.style.color = '#fff';
      btn2D.style.background = '#fff'; btn2D.style.color = 'var(--ink)';
      if (!_doctorNebula) {
        import('../3d/memory-nebula.js').then(function(mod) {
          _doctorNebula = mod.initMemoryNebula(memory3D, _doctorNodes || [], _doctorSessions || []);
        }).catch(function(err) {
          console.error('3D load failed:', err);
          memoryViewMode = '2d';
          memory2D.style.display = 'flex';
          memory3D.style.display = 'none';
          btn2D.style.background = 'var(--accent)'; btn2D.style.color = '#fff';
          btn3D.style.background = '#fff'; btn3D.style.color = 'var(--ink)';
        });
      }
    }
  }, '3D 星云');
  viewToggle.appendChild(btn2D);
  viewToggle.appendChild(btn3D);
  memorySection.appendChild(viewToggle);
  app.appendChild(memorySection);

  var _doctorNodes = [];
  var _doctorSessions = [];

  // 加载记忆数据
  Promise.all([
    listSessions(10).catch(function() { return []; }),
    getLatestGraph().catch(function() { return null; })
  ]).then(function(results) {
    var sessions = results[0] || [];
    var graph = results[1] || null;
    _doctorSessions = sessions;
    _doctorNodes = graph && graph.nodes ? graph.nodes : [];

    memory2D.innerHTML = '';
    sessions.slice(0, 6).forEach(function(s) {
      var card = el('div', {
        style: {
          background: 'var(--bg)',
          borderRadius: '8px',
          padding: '10px',
          borderLeft: '3px solid var(--accent)',
        }
      });
      var dateStr = s.date || s.created_at ? new Date(s.date || s.created_at).toLocaleDateString('zh-CN') : '今天';
      card.appendChild(el('div', { style: { fontSize: '0.75rem', color: 'var(--muted)', marginBottom: '2px' } }, dateStr));
      card.appendChild(el('div', { style: { fontSize: '0.9rem', lineHeight: '1.5', color: 'var(--ink)' } }, s.narrative_text || s.text || '—'));
      memory2D.appendChild(card);
    });
    if (sessions.length === 0) {
      memory2D.appendChild(el('div', { style: { color: 'var(--muted)', fontSize: '0.9rem' } }, '暂无记忆记录'));
    }
  }).catch(function() {
    memory2D.innerHTML = '';
    memory2D.appendChild(el('div', { style: { color: 'var(--muted)', fontSize: '0.9rem' } }, '记忆数据加载失败'));
  });

  // 量表趋势表格容器
  var tableWrap = el('div', {
    style: { overflowX: 'auto', background: 'var(--bg2)', borderRadius: '12px', padding: '12px' }
  });
  var table = el('table', {
    style: {
      width: '100%',
      borderCollapse: 'collapse',
      fontSize: '0.9rem',
      color: 'var(--ink)',
    }
  });
  var thead = el('thead');
  var headerRow = el('tr');
  ['日期', '量表类型', '分数', '趋势', '备注'].forEach(function(h) {
    headerRow.appendChild(el('th', {
      style: {
        padding: '10px',
        borderBottom: '2px solid var(--rule)',
        textAlign: 'left',
        fontWeight: '700',
      }
    }, h));
  });
  thead.appendChild(headerRow);
  table.appendChild(thead);

  var tbody = el('tbody', { id: 'doctor-scale-tbody' });
  tbody.appendChild(el('tr', {}, [
    el('td', { style: { padding: '10px', color: 'var(--muted)' }, colSpan: 5 }, '加载中…')
  ]));
  table.appendChild(tbody);
  tableWrap.appendChild(table);
  app.appendChild(tableWrap);

  // 异常标记列表
  app.appendChild(el('h3', {
    style: { marginTop: '16px', fontSize: '1.1rem', color: 'var(--ink)' }
  }, '异常标记'));
  var anomalyList = el('div', {
    id: 'doctor-anomaly-list',
    style: {
      background: 'var(--bg2)',
      borderRadius: '12px',
      padding: '16px',
      display: 'flex',
      flexDirection: 'column',
      gap: '8px',
    }
  });
  anomalyList.appendChild(el('div', {
    style: { color: 'var(--muted)', fontSize: '0.9rem' }
  }, '加载中…'));
  app.appendChild(anomalyList);

  // 发送建议区域
  app.appendChild(el('h3', {
    style: { marginTop: '16px', fontSize: '1.1rem', color: 'var(--ink)' }
  }, '诊断建议'));
  var adviceSection = el('div', {
    style: {
      background: 'var(--bg2)',
      borderRadius: '12px',
      padding: '16px',
      display: 'flex',
      flexDirection: 'column',
      gap: '10px',
    }
  });
  var categoryInput = el('input', {
    type: 'text',
    placeholder: '建议类别（如：用药 / 生活方式 / 复查）',
    style: {
      padding: '10px',
      borderRadius: '8px',
      border: '1px solid var(--rule)',
      fontSize: '0.95rem',
    }
  });
  adviceSection.appendChild(categoryInput);
  var contentInput = el('textarea', {
    placeholder: '输入诊断建议内容…',
    style: {
      padding: '10px',
      borderRadius: '8px',
      border: '1px solid var(--rule)',
      fontSize: '0.95rem',
      minHeight: '80px',
      resize: 'vertical',
    }
  });
  adviceSection.appendChild(contentInput);
  var prioritySelect = el('select', {
    style: {
      padding: '10px',
      borderRadius: '8px',
      border: '1px solid var(--rule)',
      fontSize: '0.95rem',
    }
  }, [
    el('option', { value: 'low' }, '低优先级'),
    el('option', { value: 'medium', selected: true }, '中优先级'),
    el('option', { value: 'high' }, '高优先级'),
  ]);
  adviceSection.appendChild(prioritySelect);
  var patientIdInput = el('input', {
    type: 'text',
    placeholder: '患者 ID（ elderly_id ）',
    style: {
      padding: '10px',
      borderRadius: '8px',
      border: '1px solid var(--rule)',
      fontSize: '0.95rem',
    }
  });
  adviceSection.appendChild(patientIdInput);
  adviceSection.appendChild(el('button', {
    className: 'btn-primary',
    style: { marginTop: '4px' },
    onclick: function() {
      var patientId = patientIdInput.value.trim();
      var category = categoryInput.value.trim();
      var content = contentInput.value.trim();
      var priority = prioritySelect.value;
      if (!patientId || !content) {
        alert('请填写患者 ID 和建议内容');
        return;
      }
      var msg = sendWebSocketAdvice(patientId, category, content, priority);
      wsSend(msg);
      alert('建议已发送');
      contentInput.value = '';
    }
  }, '发送建议'));
  app.appendChild(adviceSection);

  // 建议卡片列表（显示已发送的建议）
  var adviceCards = el('div', {
    id: 'doctor-advice-cards',
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: '10px',
    }
  });
  app.appendChild(adviceCards);

  // 导出 PDF 按钮
  app.appendChild(el('button', {
    className: 'btn-primary',
    style: { marginTop: '16px', width: '100%', fontSize: '1rem', padding: '12px' },
    onclick: function() { window.print(); }
  }, '导出 PDF'));

  container.appendChild(app);

  // 加载量表和异常数据
  loadDoctorData(tbody, anomalyList, adviceCards);

  // 清理
  container._cleanup = function() {
    if (_doctorNebula) { _doctorNebula.destroy(); _doctorNebula = null; }
  };

  // 启动 WebSocket
  var token = getToken();
  if (token) {
    wsConnect(token, function(msg) {
      if (msg.type === 'read_receipt') {
        console.log('患者已读建议', msg.payload);
      }
    });
  }
}

function loadDoctorData(tbody, anomalyList, adviceCards) {
  Promise.all([
    getScaleHistory('MMSE').catch(function() { return []; }),
    getScaleHistory('AD8').catch(function() { return []; }),
    getDeclineAnalysis(7).catch(function() { return null; })
  ]).then(function(results) {
    var mmse = results[0] || [];
    var ad8 = results[1] || [];
    var decline = results[2];

    // 合并并排序
    var all = mmse.concat(ad8).sort(function(a, b) {
      return new Date(b.date || b.created_at || 0) - new Date(a.date || a.created_at || 0);
    });

    tbody.innerHTML = '';
    if (all.length === 0) {
      tbody.appendChild(el('tr', {}, [
        el('td', { style: { padding: '10px', color: 'var(--muted)' }, colSpan: 5 }, '暂无量表历史数据')
      ]));
    } else {
      all.forEach(function(item, idx) {
        var prev = all[idx + 1];
        var score = item.total_score != null ? item.total_score : (item.score || '—');
        var prevScore = prev && prev.total_score != null ? prev.total_score : (prev && prev.score ? prev.score : null);
        var trend = '—';
        if (prevScore != null && score !== '—') {
          var diff = score - prevScore;
          if (diff > 0) trend = '↑ +' + diff;
          else if (diff < 0) trend = '↓ ' + diff;
          else trend = '→ 持平';
        }
        var row = el('tr', { style: { borderBottom: '1px solid var(--rule)' } }, [
          el('td', { style: { padding: '10px' } }, item.date || item.created_at ? new Date(item.date || item.created_at).toLocaleDateString('zh-CN') : '—'),
          el('td', { style: { padding: '10px' } }, item.scale_type || '—'),
          el('td', { style: { padding: '10px', fontWeight: '700' } }, String(score)),
          el('td', { style: { padding: '10px' } }, trend),
          el('td', { style: { padding: '10px', color: 'var(--muted)', fontSize: '0.85rem' } }, item.notes || ''),
        ]);
        tbody.appendChild(row);
      });
    }

    // 异常标记
    anomalyList.innerHTML = '';
    var anomalies = [];
    if (decline && decline.anomalies) {
      anomalies = decline.anomalies;
    }
    if (anomalies.length === 0) {
      anomalyList.appendChild(el('div', {
        style: { color: 'var(--muted)', fontSize: '0.9rem' }
      }, '暂无异常标记'));
    } else {
      anomalies.forEach(function(a) {
        var item = el('div', {
          style: {
            padding: '10px',
            background: 'rgba(199,91,91,0.08)',
            borderRadius: '8px',
            borderLeft: '3px solid var(--danger)',
          }
        });
        item.appendChild(el('div', {
          style: { fontWeight: '700', fontSize: '0.9rem', color: 'var(--danger)' }
        }, a.type || '异常'));
        item.appendChild(el('div', {
          style: { fontSize: '0.85rem', color: 'var(--muted)', marginTop: '2px' }
        }, a.message || a.description || JSON.stringify(a)));
        anomalyList.appendChild(item);
      });
    }

    // 建议卡片
    if (adviceCards) {
      adviceCards.innerHTML = '';
    }
  }).catch(function() {
    tbody.innerHTML = '';
    tbody.appendChild(el('tr', {}, [
      el('td', { style: { padding: '10px', color: 'var(--muted)' }, colSpan: 5 }, '加载失败，请稍后重试')
    ]));
    anomalyList.innerHTML = '';
    anomalyList.appendChild(el('div', {
      style: { color: 'var(--muted)', fontSize: '0.9rem' }
    }, '加载失败'));
  });
}
