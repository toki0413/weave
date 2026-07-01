// ============ RIGHT PANEL ============
// 右侧面板：老人端健康度、家属端结构指标、医生端拓扑同构分析
import { state } from '../../state.js';
import { el } from '../components.js';
import { computeMetrics, computeHealth } from '../../graph/metrics.js';
import { computeBaselineSimilarity } from '../../graph/similarity.js';
import { createTTSButton } from '../tts-button.js';
import { renderRadarChart } from '../charts/radar-chart.js';
import { renderTrendChart, createTrendViewToggle } from '../charts/trend-chart.js';
import { renderEmotionBadge, getEmotionFromSession } from '../emotion-badge.js';
import { isEnabled } from '../../features.js';
import { llmSummarize, llmQA } from '../../api/client.js';

var rightPanelTab = 'metrics'; // 'metrics' | 'radar' | 'emotion'

function openTrendModal() {
  var existing = document.getElementById('trend-modal-overlay');
  if (existing) existing.remove();

  var overlay = el('div', {
    id: 'trend-modal-overlay',
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
      background: 'var(--bg)', borderRadius: '16px', width: '100%', maxWidth: '560px',
      maxHeight: '80vh', display: 'flex', flexDirection: 'column',
      boxShadow: '0 20px 60px rgba(0,0,0,0.25)', overflow: 'hidden',
    },
  });

  var header = el('div', {
    style: {
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '18px 24px', borderBottom: '1px solid var(--rule)', flexShrink: '0',
    },
  }, [
    el('div', { style: { fontSize: '1.1rem', fontWeight: '800', color: 'var(--ink)' } }, '健康趋势'),
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

  var chartContainer = el('div', { style: { marginBottom: '10px' } });
  var toggleWrap = createTrendViewToggle(null, function(days) {
    var data = generateTrendData(days);
    renderTrendChart(chartContainer, data);
  });
  body.appendChild(toggleWrap);
  body.appendChild(chartContainer);

  var initialData = generateTrendData(7);
  renderTrendChart(chartContainer, initialData);

  modal.appendChild(body);
  overlay.appendChild(modal);
  document.body.appendChild(overlay);
}

// ---------- LLM 弹窗 ----------

function openLLMSummaryModal() {
  var existing = document.getElementById('llm-modal-overlay');
  if (existing) existing.remove();

  var overlay = el('div', {
    id: 'llm-modal-overlay',
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
      background: 'var(--bg)', borderRadius: '16px', width: '100%', maxWidth: '520px',
      maxHeight: '80vh', display: 'flex', flexDirection: 'column',
      boxShadow: '0 20px 60px rgba(0,0,0,0.25)', overflow: 'hidden',
    },
  });

  var header = el('div', {
    style: {
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '18px 24px', borderBottom: '1px solid var(--rule)', flexShrink: '0',
    },
  }, [
    el('div', { style: { fontSize: '1.1rem', fontWeight: '800', color: 'var(--ink)' } }, 'AI 记忆总结'),
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
    style: { padding: '20px 24px', overflowY: 'auto', flex: '1', minHeight: '120px' },
  });

  // 加载动画
  var loading = el('div', { style: { textAlign: 'center', padding: '40px 0', color: 'var(--muted)' } }, [
    el('div', { style: { fontSize: '1.5rem', marginBottom: '12px' } }, '✨'),
    '正在编织记忆故事，请稍候...',
  ]);
  body.appendChild(loading);
  modal.appendChild(body);
  overlay.appendChild(modal);
  document.body.appendChild(overlay);

  // 调用 API
  var narratives = (state.sessionHistory || [])
    .slice(-7)
    .map(function(s) { return s.narrative || s.text || ''; })
    .filter(function(t) { return t; });

  llmSummarize(narratives, 7).then(function(data) {
    loading.remove();
    var summaryText = data && data.summary ? data.summary : '暂无总结内容';
    var content = el('div', { style: { lineHeight: '1.7', color: 'var(--ink)', fontSize: '0.95rem' } }, summaryText);
    body.appendChild(content);
    var ttsBtn = createTTSButton(summaryText, { size: 'small' });
    if (ttsBtn) {
      ttsBtn.style.marginTop = '12px';
      body.appendChild(ttsBtn);
    }
  }).catch(function(err) {
    loading.remove();
    var msg = err && err.message ? err.message : '生成失败';
    body.appendChild(el('div', { style: { color: 'var(--danger)', textAlign: 'center', padding: '20px 0' } },
      '生成总结时出错：' + msg
    ));
  });
}

function openLLMQAModal() {
  var existing = document.getElementById('llm-qa-overlay');
  if (existing) existing.remove();

  var overlay = el('div', {
    id: 'llm-qa-overlay',
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
      background: 'var(--bg)', borderRadius: '16px', width: '100%', maxWidth: '520px',
      maxHeight: '80vh', display: 'flex', flexDirection: 'column',
      boxShadow: '0 20px 60px rgba(0,0,0,0.25)', overflow: 'hidden',
    },
  });

  var header = el('div', {
    style: {
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '18px 24px', borderBottom: '1px solid var(--rule)', flexShrink: '0',
    },
  }, [
    el('div', { style: { fontSize: '1.1rem', fontWeight: '800', color: 'var(--ink)' } }, '问 AI'),
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
    style: { padding: '20px 24px', overflowY: 'auto', flex: '1', minHeight: '120px' },
  });

  // 输入框
  var inputWrap = el('div', { style: { display: 'flex', gap: '8px', marginBottom: '16px' } });
  var input = el('input', {
    type: 'text',
    placeholder: '例如：上周三我做了什么？',
    style: {
      flex: '1', padding: '10px 14px', borderRadius: '8px', border: '1px solid var(--rule)',
      fontSize: '0.9rem', background: 'var(--bg)', color: 'var(--ink)',
    },
  });
  var askBtn = el('button', {
    className: 'btn-primary',
    style: { padding: '10px 16px', fontWeight: '700', whiteSpace: 'nowrap' },
    onclick: function() {
      var q = input.value.trim();
      if (!q) return;
      // 清空结果区
      resultArea.innerHTML = '';
      resultArea.appendChild(el('div', { style: { textAlign: 'center', padding: '20px 0', color: 'var(--muted)' } }, [
        el('div', { style: { fontSize: '1.5rem', marginBottom: '8px' } }, '✨'),
        '正在思考...',
      ]));
      llmQA(q).then(function(data) {
        resultArea.innerHTML = '';
        var answer = data && data.answer ? data.answer : '暂无回答';
        resultArea.appendChild(el('div', { style: { lineHeight: '1.7', color: 'var(--ink)', fontSize: '0.95rem', marginBottom: '8px' } }, answer));
        if (data && data.sources && data.sources.length > 0) {
          resultArea.appendChild(el('div', { style: { fontSize: '0.7rem', color: 'var(--muted)' } },
            '参考了 ' + data.sources.length + ' 条记录'
          ));
        }
      }).catch(function(err) {
        resultArea.innerHTML = '';
        var msg = err && err.message ? err.message : '请求失败';
        resultArea.appendChild(el('div', { style: { color: 'var(--danger)', textAlign: 'center', padding: '12px 0' } },
          '问答出错：' + msg
        ));
      });
    },
  }, '提问');
  inputWrap.appendChild(input);
  inputWrap.appendChild(askBtn);
  body.appendChild(inputWrap);

  var resultArea = el('div', {});
  body.appendChild(resultArea);

  modal.appendChild(body);
  overlay.appendChild(modal);
  document.body.appendChild(overlay);

  // 回车提交
  input.onkeydown = function(e) {
    if (e.key === 'Enter') askBtn.click();
  };
  input.focus();
}

function generateTrendData(days) {
  var trend = [];
  var sessions = state.sessionHistory || [];
  if (sessions.length > 0) {
    var recent = sessions.slice(-days);
    recent.forEach(function(s) {
      var d = new Date(s.date);
      trend.push({
        health: s.healthScore || 80,
        label: (d.getMonth() + 1) + '/' + d.getDate(),
      });
    });
  } else {
    var health = 82;
    for (var i = 1; i <= days; i++) {
      var change = (Math.random() - 0.4) * 10;
      health = Math.max(30, Math.min(100, health + change));
      var d = new Date();
      d.setDate(d.getDate() - (days - i));
      trend.push({
        health: Math.round(health),
        label: (d.getMonth() + 1) + '/' + d.getDate(),
      });
    }
  }
  return trend;
}

function generateEmotionTrendData(days) {
  var trend = [];
  var sessions = state.sessionHistory || [];
  if (sessions.length > 0) {
    var recent = sessions.slice(-days);
    recent.forEach(function(s) {
      var emotion = s.emotion || getEmotionFromSession(s);
      var score = emotion && emotion.score !== undefined ? emotion.score : 0;
      // 将 -1~1 映射到 0~100 以复用趋势图
      var mapped = Math.round((score + 1) * 50);
      var d = new Date(s.date);
      trend.push({
        health: mapped,
        label: (d.getMonth() + 1) + '/' + d.getDate(),
      });
    });
  } else {
    var score = 0;
    for (var i = 1; i <= days; i++) {
      var change = (Math.random() - 0.5) * 20;
      score = Math.max(-100, Math.min(100, score + change));
      var d = new Date();
      d.setDate(d.getDate() - (days - i));
      trend.push({
        health: Math.round((score / 100 + 1) * 50),
        label: (d.getMonth() + 1) + '/' + d.getDate(),
      });
    }
  }
  return trend;
}

function renderRightPanel() {
  var panel = el('div', { className: 'panel-right', role: 'region', 'aria-label': '健康指标' });
  var section = el('div', { className: 'panel-section' });
  var m = computeMetrics();
  var health = computeHealth(m);

  if (state.view === 'family') {
    section.appendChild(el('div', { className: 'panel-title' }, '网络结构指标'));
    if (m) {
      var items = [
        { name: '记忆网密度', val: (m.density * 100).toFixed(1) + '%', desc: '实际连接/最大可能' },
        { name: '最大连通度', val: Math.round(m.connectivity * 100) + '%', desc: '最大连通子图占比' },
        { name: '聚类系数', val: Math.round(m.clustering * 100) + '%', desc: '局部三角关系密度' },
        { name: '平均路径长度', val: m.avgPathLen.toFixed(2), desc: '信息传递效率' },
        { name: '小世界系数σ', val: m.smallWorld.toFixed(2), desc: '整合/分离平衡' },
      ];
      items.forEach(function(it) {
        section.appendChild(el('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 0', borderBottom: '1px solid var(--rule)' } }, [
          el('div', {}, [
            el('div', { style: { fontSize: '0.85rem', fontWeight: '600' } }, it.name),
            el('div', { style: { fontSize: '0.7rem', color: 'var(--ink2)' } }, it.desc),
          ]),
          el('div', { style: { fontSize: '1.2rem', fontWeight: '800' } }, it.val),
        ]));
      });
    }
    panel.appendChild(section);
    return panel;
  }

  if (state.view === 'doctor') {
    var dm = computeMetrics();
    var dHealth = computeHealth(dm);
    var isoScore = computeBaselineSimilarity();
    var isoPct = Math.round(isoScore * 100);
    var isoStatus = isoPct >= 80 ? 'ok' : isoPct >= 50 ? 'warn' : 'danger';
    var isoDesc = isoPct >= 80 ? '拓扑结构高度一致，网络形态稳定' : isoPct >= 50 ? '拓扑结构出现偏移，建议关注' : '拓扑结构严重偏离，需专业评估';
    section.appendChild(el('div', { className: 'panel-title' }, '拓扑同构分析'));
    section.appendChild(el('div', { className: 'iso-card' }, [
      el('div', { className: 'iso-num' }, isoPct + '%'),
      el('div', { className: 'iso-desc' }, isoDesc),
    ]));
    section.appendChild(el('div', { className: 'panel-title', style: { marginTop: '16px' } }, '结构偏移预警'));
    var alertStatus = dHealth >= 80 ? 'ok' : dHealth >= 50 ? 'warn' : 'danger';
    var alertIcon = dHealth >= 80 ? '✓' : dHealth >= 50 ? '⚠' : '✕';
    var alertTitle = dHealth >= 80 ? '网络结构正常' : dHealth >= 50 ? '网络结构轻度偏移' : '网络结构严重偏移';
    var alertDesc = dHealth >= 80 ? '与基准图拓扑一致，无偏移信号' : dHealth >= 50 ? '部分指标偏离基准，建议复查' : '多项指标严重偏离，需专业评估';
    section.appendChild(el('div', { className: 'alert-card ' + alertStatus }, [
      el('span', { style: { fontSize: '1.2rem' } }, alertIcon),
      el('div', {}, [
        el('div', { style: { fontSize: '0.85rem', fontWeight: '600' } }, alertTitle),
        el('div', { style: { fontSize: '0.7rem', color: 'var(--ink2)' } }, alertDesc),
      ]),
    ]));
    // 基准对比明细
    if (state.baselineMetrics && dm) {
      var deltas = [
        { name: '连通度', val: dm.connectivity - state.baselineMetrics.connectivity },
        { name: '聚类系数', val: dm.clustering - state.baselineMetrics.clustering },
        { name: '密度', val: dm.density - state.baselineMetrics.density },
        { name: '全局效率', val: dm.globalEff - state.baselineMetrics.globalEff },
      ];
      section.appendChild(el('div', { className: 'panel-title', style: { marginTop: '16px' } }, '与基准对比'));
      deltas.forEach(function(d) {
        var cls = d.val > 0.05 ? 'up' : d.val < -0.05 ? 'down' : 'flat';
        var sign = d.val > 0 ? '+' : '';
        section.appendChild(el('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0', borderBottom: '1px solid var(--rule)' } }, [
          el('div', { style: { fontSize: '0.85rem', fontWeight: '600' } }, d.name),
          el('div', { className: 'metric-delta ' + cls }, sign + (d.val * 100).toFixed(1) + '%'),
        ]));
      });
    }
    panel.appendChild(section);
    return panel;
  }

  // 老人端
  var healthWrap = el('div', { style: { position: 'relative', marginBottom: '16px' } }, [
    el('div', { className: 'health-card', style: { marginBottom: '0' } }, [
      el('div', { className: 'health-num' }, String(health)),
      el('div', { className: 'health-label' }, '记忆网健康度'),
    ]),
  ]);
  var healthBtn = createTTSButton('今日健康度' + health + '分', { size: 'normal' });
  if (healthBtn) {
    healthBtn.style.position = 'absolute';
    healthBtn.style.top = '10px';
    healthBtn.style.right = '10px';
    healthWrap.appendChild(healthBtn);
  }
  section.appendChild(healthWrap);

  // 今日情绪
  var latestSession = state.sessionHistory && state.sessionHistory.length > 0
    ? state.sessionHistory[state.sessionHistory.length - 1] : null;
  var emotion = latestSession ? (latestSession.emotion || getEmotionFromSession(latestSession)) : null;
  var emotionWrap = el('div', { style: { display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' } }, [
    el('span', { style: { fontSize: '0.8rem', color: 'var(--ink2)' } }, '今日情绪：'),
  ]);
  renderEmotionBadge(emotionWrap, emotion);
  section.appendChild(emotionWrap);

  var metricsSpeakText = m
    ? '今日记忆状态。网络连通度' + Math.round(m.connectivity * 100) + '%，聚类系数' + Math.round(m.clustering * 100) + '%，自我中心度' + Math.round(m.centrality * 100) + '%，时序熵' + Math.round(m.entropy * 100) + '%。'
    : '今日记忆状态';

  // Tab bar
  var tabBar = el('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px', borderBottom: '1px solid var(--rule)', paddingBottom: '8px' } }, [
    el('div', { className: 'panel-title', style: { marginBottom: '0' } }, '今日记忆状态'),
    el('div', { style: { display: 'flex', gap: '4px' } }, [
      el('button', {
        style: {
          padding: '4px 10px', border: '1px solid ' + (rightPanelTab === 'metrics' ? 'var(--accent)' : 'var(--rule)'),
          background: rightPanelTab === 'metrics' ? 'var(--accent)' : '#fff',
          color: rightPanelTab === 'metrics' ? '#fff' : 'var(--ink2)', borderRadius: '6px', cursor: 'pointer',
          fontSize: '0.75rem', fontWeight: '600'
        },
        onclick: function() { rightPanelTab = 'metrics'; renderRightPanelOnly(); }
      }, '指标列表'),
      el('button', {
        style: {
          padding: '4px 10px', border: '1px solid ' + (rightPanelTab === 'radar' ? 'var(--accent)' : 'var(--rule)'),
          background: rightPanelTab === 'radar' ? 'var(--accent)' : '#fff',
          color: rightPanelTab === 'radar' ? '#fff' : 'var(--ink2)', borderRadius: '6px', cursor: 'pointer',
          fontSize: '0.75rem', fontWeight: '600'
        },
        onclick: function() { rightPanelTab = 'radar'; renderRightPanelOnly(); }
      }, '认知雷达'),
      el('button', {
        style: {
          padding: '4px 10px', border: '1px solid ' + (rightPanelTab === 'emotion' ? 'var(--accent)' : 'var(--rule)'),
          background: rightPanelTab === 'emotion' ? 'var(--accent)' : '#fff',
          color: rightPanelTab === 'emotion' ? '#fff' : 'var(--ink2)', borderRadius: '6px', cursor: 'pointer',
          fontSize: '0.75rem', fontWeight: '600'
        },
        onclick: function() { rightPanelTab = 'emotion'; renderRightPanelOnly(); }
      }, '情绪趋势'),
    ]),
  ]);
  section.appendChild(tabBar);
  section.appendChild(createTTSButton(metricsSpeakText, { size: 'small' }));

  if (rightPanelTab === 'metrics') {
    if (m) {
      var metrics = [
        { name: '网络连通度', desc: '最大连通子图占比', val: m.connectivity },
        { name: '聚类系数', desc: '局部三角关系密度', val: m.clustering },
        { name: '自我中心度', desc: '"我"节点度数占比', val: m.centrality },
        { name: '时序熵', desc: '关系类型多样性', val: m.entropy },
      ];
      metrics.forEach(function(mt) {
        var row = el('div', { className: 'metric-row' });
        row.appendChild(el('div', { className: 'metric-header' }, [
          el('div', {}, [
            el('div', { className: 'metric-name' }, mt.name),
            el('div', { className: 'metric-desc' }, mt.desc),
          ]),
          el('div', { style: { textAlign: 'right' } }, [
            el('div', { className: 'metric-val' }, Math.round(mt.val * 100) + '%'),
          ]),
        ]));
        row.appendChild(el('div', { className: 'metric-bar' }, [
          el('div', { className: 'metric-bar-fill', style: { width: Math.min(100, mt.val * 100) + '%' } }),
        ]));
        section.appendChild(row);
      });
    }
  } else if (rightPanelTab === 'radar') {
    var radarContainer = el('div', { style: { marginBottom: '12px' } });
    var radarMetrics = state.radarMetrics || (m ? {
      current: {
        memory: Math.round(m.connectivity * 100),
        language: Math.round(m.clustering * 100),
        orientation: Math.round((m.centrality || 0.5) * 100),
        computation: Math.round((m.density || 0.5) * 100),
        attention: Math.round((m.entropy || 0.5) * 100),
        executive: Math.round((m.smallWorld || 0.5) * 100),
      },
      baseline: state.baselineMetrics ? {
        memory: Math.round(state.baselineMetrics.connectivity * 100),
        language: Math.round(state.baselineMetrics.clustering * 100),
        orientation: Math.round((state.baselineMetrics.centrality || 0.5) * 100),
        computation: Math.round((state.baselineMetrics.density || 0.5) * 100),
        attention: Math.round((state.baselineMetrics.entropy || 0.5) * 100),
        executive: Math.round((state.baselineMetrics.smallWorld || 0.5) * 100),
      } : null,
    } : null);
    renderRadarChart(radarContainer, radarMetrics);
    section.appendChild(radarContainer);
  } else {
    // 情绪趋势标签页
    var emotionChartContainer = el('div', { style: { marginBottom: '10px' } });
    var emotionToggleWrap = createTrendViewToggle(null, function(days) {
      var data = generateEmotionTrendData(days);
      renderTrendChart(emotionChartContainer, data);
    });
    section.appendChild(emotionToggleWrap);
    section.appendChild(emotionChartContainer);
    var initialEmotionData = generateEmotionTrendData(7);
    renderTrendChart(emotionChartContainer, initialEmotionData);
    // 情绪图例说明
    section.appendChild(el('div', { style: { fontSize: '0.7rem', color: 'var(--muted)', textAlign: 'center', marginTop: '4px' } }, [
      '0=消极 ',
      el('span', { style: { display: 'inline-block', width: '20px', height: '3px', background: '#C0392B', verticalAlign: 'middle', margin: '0 4px' } }),
      ' 50=中性 ',
      el('span', { style: { display: 'inline-block', width: '20px', height: '3px', background: '#837A6E', verticalAlign: 'middle', margin: '0 4px' } }),
      ' 100=积极',
    ]));
  }

  // 趋势按钮
  var trendBtn = el('button', {
    className: 'btn-secondary',
    style: { width: '100%', marginTop: '6px', fontWeight: '700', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px' },
    onclick: function() { openTrendModal(); }
  }, '📈 查看健康趋势');
  section.appendChild(trendBtn);

  // LLM 按钮（仅在功能开关开启时显示）
  if (isEnabled('llm_enabled')) {
    var aiBtnWrap = el('div', { style: { display: 'flex', gap: '8px', marginTop: '10px' } });
    var summarizeBtn = el('button', {
      className: 'btn-secondary',
      style: { flex: '1', fontWeight: '700', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px' },
      onclick: function() { openLLMSummaryModal(); }
    }, '✨ AI 总结');
    var qaBtn = el('button', {
      className: 'btn-secondary',
      style: { flex: '1', fontWeight: '700', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px' },
      onclick: function() { openLLMQAModal(); }
    }, '💬 问 AI');
    aiBtnWrap.appendChild(summarizeBtn);
    aiBtnWrap.appendChild(qaBtn);
    section.appendChild(aiBtnWrap);
  }

  var alertStatus = health >= 80 ? 'ok' : health >= 50 ? 'warn' : 'danger';
  var alertIcon = health >= 80 ? '✓' : health >= 50 ? '⚠' : '✕';
  var alertTitle = health >= 80 ? '今天记忆网络很好，继续保持' : health >= 50 ? '记忆网络出现轻微波动，建议关注' : '记忆网络异常，建议尽快就医';
  var alertDesc = health >= 80 ? '各项指标正常，认知状态稳定' : health >= 50 ? '部分指标偏离基准，建议复查' : '多项指标严重偏离，需专业评估';

  // 语义异常提示
  if (state.anomalies && state.anomalies.length > 0) {
    state.anomalies.forEach(function(a) {
      var anomStatus = a.severity === 'danger' ? 'danger' : 'warn';
      var anomIcon = a.severity === 'danger' ? '✕' : '⚠';
      var anomTitle = a.event === '人物-活动错置' ? '检测到人物-活动场景错置' : '检测到"' + a.event + '"的场景异常';
      var anomDesc = a.expectedPlaces.length > 0
        ? '该活动通常发生在：' + a.expectedPlaces.join('、') + '，但当前文本中未出现预期地点'
        : '人物与活动出现在不匹配的场景中';
      section.appendChild(el('div', { className: 'alert-card ' + anomStatus, style: { marginTop: '8px' } }, [
        el('span', { style: { fontSize: '1.2rem' } }, anomIcon),
        el('div', { style: { flex: '1' } }, [
          el('div', { style: { fontSize: '0.85rem', fontWeight: '600' } }, anomTitle),
          el('div', { style: { fontSize: '0.7rem', color: 'var(--muted)' } }, anomDesc),
        ]),
        createTTSButton(anomTitle + '。' + anomDesc, { size: 'small' }),
      ]));
    });
  }

  section.appendChild(el('div', { className: 'alert-card ' + alertStatus, style: { marginTop: '8px' } }, [
    el('span', { style: { fontSize: '1.2rem' } }, alertIcon),
    el('div', { style: { flex: '1' } }, [
      el('div', { style: { fontSize: '0.85rem', fontWeight: '600' } }, alertTitle),
      el('div', { style: { fontSize: '0.7rem', color: 'var(--muted)' } }, alertDesc),
    ]),
    createTTSButton(alertTitle + '。' + alertDesc, { size: 'small' }),
  ]));

  // 训练记录
  var trainingSection = el('div', { className: 'panel-section', style: { marginTop: '16px' } });
  trainingSection.appendChild(el('div', { className: 'panel-title' }, '训练记录'));
  var trainingScores = state.trainingScores || [];
  var gameTypeNames = {
    memory_challenge: '记忆挑战',
    number_link: '数字连线'
  };
  if (trainingScores.length > 0) {
    var latest = trainingScores[trainingScores.length - 1];
    var latestGameName = gameTypeNames[latest.gameType] || latest.gameType;
    trainingSection.appendChild(el('div', { style: { fontSize: '0.85rem', marginBottom: '6px' } }, [
      '最近训练：' + latestGameName + ' ' + latest.score + '分',
    ]));
    var trainingTrend = el('div', { style: { fontSize: '0.75rem', color: 'var(--ink2)' } });
    // 找到同一类型的上一条记录
    var prevSameType = null;
    for (var i = trainingScores.length - 2; i >= 0; i--) {
      if (trainingScores[i].gameType === latest.gameType) {
        prevSameType = trainingScores[i];
        break;
      }
    }
    if (prevSameType) {
      var diff = latest.score - prevSameType.score;
      trainingTrend.textContent = (diff >= 0 ? '↑ ' : '↓ ') + Math.abs(diff) + ' 分';
    } else {
      trainingTrend.textContent = '开始记录训练趋势';
    }
    trainingSection.appendChild(trainingTrend);
  } else {
    trainingSection.appendChild(el('div', { style: { fontSize: '0.8rem', color: 'var(--muted)' } }, '暂无训练记录，点击左侧“训练”按钮开始'));
  }
  section.appendChild(trainingSection);

  panel.appendChild(section);
  return panel;
}

// 只刷新右侧面板（不重建整个界面）
function renderRightPanelOnly() {
  var old = document.querySelector('.panel-right');
  if (old) {
    var newPanel = renderRightPanel();
    old.parentNode.replaceChild(newPanel, old);
  }
}

export { renderRightPanel, renderRightPanelOnly };
