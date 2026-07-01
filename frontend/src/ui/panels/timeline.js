// ============ TIMELINE PANEL ============
// 底部时序网络：引导示例、真实会话历史、今日新建
import { state, SCENARIOS } from '../../state.js';
import { el } from '../components.js';
import { parseText } from '../../nlp/parse.js';
import { computeMetrics, computeHealth } from '../../graph/metrics.js';
import { getSelfNode } from '../../graph/model.js';
import { render } from '../render.js';
import { renderHeatmap } from '../charts/heatmap.js';

function getGraphApis() {
  return window.__graphApis || {
    startAnimation: function() {},
    stopAnimation: function() {},
    applyZoomPan: function() {},
    throttle: function(fn) { return fn; },
  };
}

// 缓存引导示例的解析结果，避免每次渲染重复计算
var _scenarioCache = null;

function _buildScenarioCache() {
  if (_scenarioCache) return _scenarioCache;
  var cache = [];
  var tmpNodes = state.nodes.slice();
  var tmpEdges = state.edges.slice();
  var tmpId = state.nodeIdCounter;
  SCENARIOS.forEach(function(s) {
    var selfNode = tmpNodes.find(function(n) { return n.type === 'self'; });
    state.nodes = selfNode ? [selfNode] : [getSelfNode()];
    state.edges = [];
    state.nodeIdCounter = 1;
    parseText(s.text);
    var tmpM = computeMetrics();
    var tmpH = computeHealth(tmpM);
    cache.push({ healthScore: tmpH, status: tmpH >= 80 ? 'ok' : tmpH >= 50 ? 'warn' : 'danger' });
  });
  state.nodes = tmpNodes;
  state.edges = tmpEdges;
  state.nodeIdCounter = tmpId;
  _scenarioCache = cache;
  return cache;
}

function renderTimeline() {
  var tl = el('div', { className: 'timeline', role: 'navigation', 'aria-label': '时序网络' });

  // 30日热力图回顾
  var heatmapWrap = el('div', { style: { padding: '10px 20px 6px', borderBottom: '1px solid var(--rule)', background: 'var(--bg2)' } });
  var heatmapTitle = el('div', { className: 'timeline-section-label', style: { marginBottom: '6px' } }, '30日回顾');
  heatmapWrap.appendChild(heatmapTitle);
  var heatmapContainer = el('div');
  var heatmapSessions = state.sessionHistory.map(function(s, idx) {
    var d = new Date(s.date);
    return {
      date: (d.getMonth() + 1) + '/' + d.getDate(),
      dateLabel: (d.getMonth() + 1) + '/' + d.getDate(),
      value: (s.graph && s.graph.nodes) ? s.graph.nodes.length : 0,
      sessionIndex: idx,
    };
  });
  renderHeatmap(heatmapContainer, heatmapSessions, {
    onClick: function(s) {
      var idx = s.sessionIndex;
      var sess = state.sessionHistory[idx];
      if (!sess) return;
      state.currentDay = idx;
      state.guidedMode = false;
      if (sess.graph) {
        state.nodes = sess.graph.nodes.map(function(n) {
          return {
            id: n.id, label: n.label, type: n.type,
            x: n.x || state.svgW / 2, y: n.y || state.svgH / 2,
            vx: 0, vy: 0,
            radius: n.type === 'self' ? 28 : n.type === 'anon' ? 22 : 20,
            isAnon: n.isAnon, matchedTo: n.matchedTo || null,
            matchConfidence: n.matchConfidence || 0, fixed: false,
          };
        });
        state.edges = sess.graph.edges || [];
        state.nodeIdCounter = sess.graph.nodeIdCounter || state.nodes.length;
        state.anomalies = sess.anomalies || [];
      }
      state.selectedNode = null;
      state.convergeCount = 0;
      render();
      getGraphApis().startAnimation();
    }
  });
  heatmapWrap.appendChild(heatmapContainer);
  tl.appendChild(heatmapWrap);

  tl.appendChild(el('span', { className: 'timeline-label' }, '时序网络'));

  var scrollWrap = el('div', { className: 'timeline-scroll' });

  // 引导示例（前7天）
  var guideLabel = el('div', { className: 'timeline-section-label' }, '引导示例');
  scrollWrap.appendChild(guideLabel);

  var scenarioCache = _buildScenarioCache();
  SCENARIOS.forEach(function(s, idx) {
    var cached = scenarioCache[idx];
    var dynStatus = cached.status;
    var card = el('button', {
      className: 'day-card' +
        (state.currentDay === s.day - 1 && state.guidedMode ? ' active' : '') +
        (dynStatus === 'warn' ? ' warn' : '') +
        (dynStatus === 'danger' ? ' danger' : ''),
      onclick: function() {
        state.currentDay = s.day - 1;
        state.guidedMode = true;
        var sn = state.nodes.find(function(n) { return n.type === 'self'; });
        state.nodes = sn ? [sn] : [getSelfNode()];
        state.edges = [];
        state.nodeIdCounter = 1;
        state.selectedNode = null;
        state.convergeCount = 0;
        var scenario = SCENARIOS[state.currentDay];
        parseText(scenario.text);
        render();
        getGraphApis().startAnimation();
      }
    }, [
      el('span', { className: 'day-card-num' }, 'D' + s.day),
      el('span', { className: 'day-card-label' }, s.label.substring(0, 2)),
      el('span', { className: 'day-card-dot ' + dynStatus }),
    ]);
    scrollWrap.appendChild(card);
  });

  // 真实会话历史
  if (state.sessionHistory.length > 0) {
    scrollWrap.appendChild(el('div', { className: 'timeline-section-label' }, '我的记录'));
    state.sessionHistory.forEach(function(sess, idx) {
      var d = new Date(sess.date);
      var dateStr = (d.getMonth() + 1) + '/' + d.getDate();
      var status = sess.healthScore >= 80 ? 'ok' : sess.healthScore >= 50 ? 'warn' : 'danger';
      var card = el('button', {
        className: 'day-card' +
          (!state.guidedMode && state.currentDay === idx ? ' active' : '') +
          (status === 'warn' ? ' warn' : '') +
          (status === 'danger' ? ' danger' : ''),
        onclick: function() {
          state.currentDay = idx;
          state.guidedMode = false;
          if (sess.graph) {
            state.nodes = sess.graph.nodes.map(function(n) {
              return {
                id: n.id, label: n.label, type: n.type,
                x: n.x || state.svgW / 2, y: n.y || state.svgH / 2,
                vx: 0, vy: 0,
                radius: n.type === 'self' ? 28 : n.type === 'anon' ? 22 : 20,
                isAnon: n.isAnon, matchedTo: n.matchedTo || null,
                matchConfidence: n.matchConfidence || 0, fixed: false,
              };
            });
            state.edges = sess.graph.edges || [];
            state.nodeIdCounter = sess.graph.nodeIdCounter || state.nodes.length;
            state.anomalies = sess.anomalies || [];
          }
          state.selectedNode = null;
          state.convergeCount = 0;
          render();
          getGraphApis().startAnimation();
        }
      }, [
        el('span', { className: 'day-card-num' }, dateStr),
        el('span', { className: 'day-card-label' }, sess.healthScore + '分'),
        el('span', { className: 'day-card-dot ' + status }),
      ]);
      scrollWrap.appendChild(card);
    });
  }

  // 今日新建按钮
  var todayBtn = el('button', {
    className: 'day-card today-btn',
    onclick: function() {
      state.guidedMode = false;
      state.currentDay = state.sessionHistory.length;
      var sn = state.nodes.find(function(n) { return n.type === 'self'; });
      state.nodes = sn ? [sn] : [getSelfNode()];
      state.edges = [];
      state.nodeIdCounter = 1;
      state.selectedNode = null;
      state.convergeCount = 0;
      state.anomalies = [];
      render();
      getGraphApis().startAnimation();
    }
  }, [
    el('span', { className: 'day-card-num' }, '+'),
    el('span', { className: 'day-card-label' }, '今日'),
  ]);
  scrollWrap.appendChild(todayBtn);

  tl.appendChild(scrollWrap);
  return tl;
}

export { renderTimeline };
