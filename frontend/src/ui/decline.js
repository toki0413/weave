// ============ 脑健康小结 UI（story-9 重写） ============
// 顶部卡片渲染后端 tier 引擎结论（绿/琥珀/红 + 可做的下一步）——
// 旧版渲染的 decline_score/level 三档已被取代（PRD story-9 AC5）。
// 详细分析（四维 + 时间线）保留给愿意深看的家属/医生。
import { el } from './components.js';
import { getDeclineAnalysis, getDeclineTimeline } from '../api/client.js';
import { tierDisplay } from './tier-copy.js';
import { trapFocus } from './interactions.js';

var overlayEl = null;
var _restoreFocus = null;
var _savedFocus = null;

// 打开小结弹窗
export function openDeclinePanel() {
  closeDeclinePanel();
  _savedFocus = document.activeElement;
  var overlay = el('div', {
    className: 'decline-overlay',
    id: 'decline-overlay',
    role: 'dialog',
    'aria-modal': 'true',
    'aria-label': '脑健康小结',
  });
  document.body.appendChild(overlay);
  overlayEl = overlay;
  renderLoading();
  Promise.all([
    getDeclineAnalysis(7),
    getDeclineTimeline(30),
  ]).then(function(res) {
    renderContent(res[0], res[1]);
  }).catch(function(err) {
    renderError(err);
  });
  _restoreFocus = trapFocus(overlay, _savedFocus);
}

export function closeDeclinePanel() {
  if (overlayEl && overlayEl.parentNode) {
    overlayEl.parentNode.removeChild(overlayEl);
  }
  if (_restoreFocus) {
    _restoreFocus();
    _restoreFocus = null;
  }
  _savedFocus = null;
  overlayEl = null;
}

// 加载中
function renderLoading() {
  var modal = buildModalShell('脑健康小结');
  modal.body.appendChild(el('div', { className: 'decline-loading' }, '正在汇总本周记录…'));
  paint(modal);
}

// 出错
function renderError(err) {
  var modal = buildModalShell('脑健康小结');
  modal.body.appendChild(el('div', { className: 'decline-error' },
    '加载失败：' + (err && err.offline ? '无法连接服务器，请检查网络' : (err && err.message) || '未知错误')));
  paint(modal);
}

// 主体内容
function renderContent(analysis, timeline) {
  var modal = buildModalShell('脑健康小结');

  // 顶部：tier 引擎结论卡（绿/琥珀/红 + 可做的下一步）
  var card = buildTierCard(analysis);
  modal.body.appendChild(card);

  modal.body.appendChild(renderSectionTitle('详细分析 · 一、实体遗忘'));
  modal.body.appendChild(renderForgottenEntities(analysis));

  modal.body.appendChild(renderSectionTitle('详细分析 · 二、叙事复杂度趋势'));
  modal.body.appendChild(renderSimplification(analysis));

  modal.body.appendChild(renderSectionTitle('详细分析 · 三、重复叙述检测'));
  modal.body.appendChild(renderRepetition(analysis));

  modal.body.appendChild(renderSectionTitle('详细分析 · 四、匿名化趋势'));
  modal.body.appendChild(renderAnonymization(analysis));

  modal.body.appendChild(renderSectionTitle('实体出现 / 消失时间线'));
  modal.body.appendChild(renderTimeline(timeline));

  paint(modal);
}

// ---------- story-9：tier 风险卡 ----------

// 供 family 专属模式内嵌渲染：container.appendChild(renderTierInto(el('div'), analysis))
export function renderTierInto(container, analysis) {
  container.innerHTML = '';
  container.appendChild(buildTierCard(analysis));
  return container;
}

var TONE_COLORS = {
  ok:     { border: '#4A7C4A', bg: 'rgba(74,124,74,0.10)',  dot: '#4A7C4A' },
  warn:   { border: '#B8860B', bg: 'rgba(184,134,11,0.10)', dot: '#B8860B' },
  danger: { border: '#C75B5B', bg: 'rgba(199,91,91,0.10)',  dot: '#C75B5B' },
  muted:  { border: '#8a8a8a', bg: 'rgba(128,128,128,0.08)', dot: '#8a8a8a' },
};

function buildTierCard(analysis) {
  var d = tierDisplay(analysis);
  var tone = TONE_COLORS[d.tone] || TONE_COLORS.muted;

  var card = el('div', {
    style: {
      border: '2px solid ' + tone.border, background: tone.bg,
      borderRadius: '14px', padding: '16px', marginBottom: '16px',
    }
  });

  // 色点 + 标题（大字号，家属一眼懂）
  var head = el('div', {
    style: { display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px' }
  });
  head.appendChild(el('span', {
    'aria-hidden': 'true',
    style: { width: '16px', height: '16px', borderRadius: '50%', background: tone.dot, flexShrink: '0' }
  }));
  head.appendChild(el('span', {
    style: { fontSize: '1.25rem', fontWeight: '800', color: 'var(--ink)' }
  }, d.title));
  card.appendChild(head);

  // 数据不足时说明缺多少（诚实，不编等级）
  if (d.insufficient) {
    card.appendChild(el('div', {
      style: { fontSize: '0.95rem', color: 'var(--muted)', marginBottom: '6px' }
    }, d.reason || '有效记录还不足以下结论。'));
  }

  // 值得留意的信号（只列 warning/danger，生活语言，来自 tier-copy 映射）
  if (d.signals.length > 0) {
    var list = el('div', { style: { margin: '8px 0' } });
    d.signals.forEach(function(s) {
      var row = el('div', {
        style: { display: 'flex', gap: '8px', alignItems: 'baseline', padding: '3px 0', fontSize: '0.98rem', color: 'var(--ink2)' }
      });
      row.appendChild(el('span', {
        style: { width: '8px', height: '8px', borderRadius: '50%', background: s.severity === 'danger' ? tone.dot : '#B8860B', display: 'inline-block', flexShrink: '0' }
      }));
      row.appendChild(document.createTextNode(s.label));
      list.appendChild(row);
    });
    card.appendChild(list);
  }

  // 下一步：advice 文字 + 真按钮（发关怀/联系医生依赖家属绑定，P1 批次补）
  var advice = el('div', {
    style: { fontSize: '1.02rem', fontWeight: '700', color: 'var(--ink)', margin: '10px 0 12px' }
  }, d.advice);
  card.appendChild(advice);

  if (!d.insufficient) {
    var btn = el('button', {
      className: 'cg-btn btn-primary',
      style: { fontSize: '1rem', padding: '0.6rem 1.1rem' },
      onclick: function() {
        import('./scale.js').then(function(mod) { mod.openScalePanel(); });
      }
    }, '陪老人做一次认知量表');
    card.appendChild(btn);
  }

  // 色盲安全：颜色之外有文字等级（title 本身即等级）+ aria
  card.setAttribute('role', 'status');

  // 未标定声明（产品定位：tier 是附带的趋势观察，不承诺准确率）
  var foot = el('div', {
    style: { marginTop: '10px', fontSize: '0.78rem', color: 'var(--muted)' }
  }, d.calibrationNote + (d.configVersion ? '（' + d.configVersion + '）' : ''));
  card.appendChild(foot);
  return card;
}

// 弹窗外壳
function buildModalShell(title) {
  var container = el('div', { className: 'decline-modal' });
  var header = el('div', { className: 'decline-modal-header' }, [
    el('h2', { className: 'decline-modal-title' }, title),
    el('button', {
      className: 'decline-close-btn',
      'aria-label': '关闭',
      onclick: closeDeclinePanel,
    }, '✕'),
  ]);
  var body = el('div', { className: 'decline-modal-body' });
  container.appendChild(header);
  container.appendChild(body);
  return { container: container, body: body };
}

function paint(modal) {
  if (!overlayEl) return;
  overlayEl.innerHTML = '';
  overlayEl.appendChild(modal.container);
}

function renderSectionTitle(text) {
  return el('div', { className: 'decline-section-title' }, text);
}

// （旧版 renderRiskCard：decline_score 大数字 + 正常/关注/警告三档——
//  story-9 AC5 已删除，由 buildTierCard 的 tier 结论取代，不再双轨展示）

// 实体遗忘
function renderForgottenEntities(analysis) {
  var list = analysis.forgotten_entities || [];
  if (list.length === 0) {
    return el('div', { className: 'decline-empty' }, '未检测到遗忘实体，近期叙事保持了原有的实体覆盖。');
  }
  var wrap = el('div', { className: 'decline-entity-list' });
  list.slice(0, 12).forEach(function(item) {
    wrap.appendChild(el('div', { className: 'decline-entity-row' }, [
      el('span', { className: 'decline-entity-name' }, item.entity),
      el('span', { className: 'decline-entity-meta' },
        '已 ' + item.days_absent + ' 天未提及 · 历史出现 ' + item.previous_count + ' 次'),
    ]));
  });
  if (list.length > 12) {
    wrap.appendChild(el('div', { className: 'decline-more' }, '还有 ' + (list.length - 12) + ' 个实体未展示'));
  }
  return wrap;
}

// 叙事简化：用 CSS 模拟折线图（句子长度 / 实体密度）
function renderSimplification(analysis) {
  var s = analysis.narrative_simplification;
  if (!s || Object.keys(s).length === 0) {
    return el('div', { className: 'decline-empty' }, '叙事复杂度数据不足。');
  }
  var wrap = el('div', { className: 'decline-simplification' });

  // 两个迷你折线图：历史 vs 近期
  wrap.appendChild(renderMiniTrend(
    '平均句子长度',
    s.prev_avg_sentence_len,
    s.recent_avg_sentence_len,
    s.sentence_len_drop
  ));
  wrap.appendChild(renderMiniTrend(
    '实体密度（每百字）',
    s.prev_entity_density,
    s.recent_entity_density,
    s.entity_density_drop
  ));
  return wrap;
}

// 迷你折线：用两段高度不同的 div 模拟趋势
function renderMiniTrend(label, prevVal, recentVal, drop) {
  var maxVal = Math.max(prevVal, recentVal, 1);
  var prevH = Math.round((prevVal / maxVal) * 60) + 8;
  var recentH = Math.round((recentVal / maxVal) * 60) + 8;
  var dropPct = Math.round((drop || 0) * 100);
  var trendCls = drop > 0.05 ? 'down' : drop < -0.05 ? 'up' : 'flat';
  var trendText = drop > 0.05 ? '↓ ' + dropPct + '%' : drop < -0.05 ? '↑ ' + (-dropPct) + '%' : '基本持平';

  return el('div', { className: 'decline-mini-trend' }, [
    el('div', { className: 'decline-mini-trend-label' }, label),
    el('div', { className: 'decline-mini-trend-chart' }, [
      el('div', { className: 'decline-bar-group' }, [
        el('div', { className: 'decline-bar prev', style: { height: prevH + 'px' } }),
        el('div', { className: 'decline-bar-label' }, '历史'),
      ]),
      el('div', { className: 'decline-bar-group' }, [
        el('div', { className: 'decline-bar recent', style: { height: recentH + 'px' } }),
        el('div', { className: 'decline-bar-label' }, '近期'),
      ]),
    ]),
    el('div', { className: 'decline-mini-trend-values' }, [
      el('span', {}, '历史 ' + prevVal.toFixed(1)),
      el('span', {}, '近期 ' + recentVal.toFixed(1)),
    ]),
    el('div', { className: 'decline-trend-tag ' + trendCls }, trendText),
  ]);
}

// 重复叙述
function renderRepetition(analysis) {
  var list = analysis.repetition || [];
  if (list.length === 0) {
    return el('div', { className: 'decline-empty' }, '未检测到重复叙述行为。');
  }
  var wrap = el('div', { className: 'decline-repetition-list' });
  list.forEach(function(item) {
    wrap.appendChild(el('div', { className: 'decline-repetition-row' }, [
      el('span', { className: 'decline-repetition-event' }, '"' + item.event + '"'),
      el('span', { className: 'decline-repetition-meta' },
        '已连续提及 ' + item.consecutive_days + ' 天，可能是记忆固着信号'),
    ]));
  });
  return wrap;
}

// 匿名化趋势
function renderAnonymization(analysis) {
  var a = analysis.anonymization_trend;
  if (!a || Object.keys(a).length === 0) {
    return el('div', { className: 'decline-empty' }, '匿名化数据不足。');
  }
  var risePct = Math.round((a.rise_pct || 0) * 100);
  var cls = risePct > 20 ? 'warn' : 'ok';
  var desc = risePct > 50
    ? '匿名节点比例显著上升，可能存在人物识别困难'
    : risePct > 20
      ? '匿名化略有上升，建议持续观察'
      : '匿名化比例稳定';
  return el('div', { className: 'decline-anon-trend' }, [
    el('div', { className: 'decline-anon-row' }, [
      el('span', {}, '历史匿名比例'),
      el('span', { className: 'decline-anon-val' }, (a.prev_anon_ratio || 0).toFixed(2)),
    ]),
    el('div', { className: 'decline-anon-row' }, [
      el('span', {}, '近期匿名比例'),
      el('span', { className: 'decline-anon-val' }, (a.recent_anon_ratio || 0).toFixed(2)),
    ]),
    el('div', { className: 'decline-anon-tag ' + cls }, (risePct >= 0 ? '+' : '') + risePct + '% · ' + desc),
  ]);
}

// 时间线视图
function renderTimeline(timeline) {
  if (!timeline || !timeline.timeline || timeline.timeline.length === 0) {
    return el('div', { className: 'decline-empty' }, '暂无时间线数据。');
  }
  var wrap = el('div', { className: 'decline-timeline-wrap' });

  // 消失中的实体
  var disappearing = timeline.disappearing || [];
  if (disappearing.length > 0) {
    var dpTitle = el('div', { className: 'decline-timeline-sub' }, '正在消失的实体');
    wrap.appendChild(dpTitle);
    var dpList = el('div', { className: 'decline-disappearing-list' });
    disappearing.slice(0, 8).forEach(function(d) {
      dpList.appendChild(el('div', { className: 'decline-disappearing-row' }, [
        el('span', { className: 'decline-disappearing-name' }, d.entity),
        el('span', { className: 'decline-disappearing-meta' },
          '最后出现：' + d.last_seen + ' · 已 ' + d.days_since_last_seen + ' 天未提及' +
          ' · 历史出现 ' + d.appearances + ' 次'),
      ]));
    });
    wrap.appendChild(dpList);
  }

  // 时间线条形图：每天实体数
  var tlTitle = el('div', { className: 'decline-timeline-sub' }, '每日实体数量');
  wrap.appendChild(tlTitle);

  var tl = timeline.timeline;
  var maxCount = 1;
  tl.forEach(function(t) {
    var total = Object.keys(t.entities).length;
    if (total > maxCount) maxCount = total;
  });

  var chart = el('div', { className: 'decline-timeline-chart' });
  tl.forEach(function(t) {
    var total = Object.keys(t.entities).length;
    var h = Math.round((total / maxCount) * 80) + 4;
    var bar = el('div', { className: 'decline-tl-bar-group' }, [
      el('div', { className: 'decline-tl-bar', style: { height: h + 'px' }, title: t.date + '：' + total + ' 个实体' }),
      el('div', { className: 'decline-tl-bar-label' }, 'D' + (t.day_number || '')),
    ]);
    chart.appendChild(bar);
  });
  wrap.appendChild(chart);

  wrap.appendChild(el('div', { className: 'decline-timeline-summary' },
    '共追踪 ' + (timeline.total_entities || 0) + ' 个实体 · ' +
    '正在消失 ' + disappearing.length + ' 个'));

  return wrap;
}
