// ============ UI INTERACTIONS ============
import { state, zoomPan, STATE_VERSION } from '../state.js';
import { render, renderCanvas, renderRightPanelOnly } from './render.js';
import { el } from './components.js';
import { isLoggedIn, syncState, loadServerState } from '../api/client.js';

import { addNode } from '../graph/model.js';

function getGraphApis() {
  return window.__graphApis || {
    startAnimation: function() {},
    stopAnimation: function() {},
    applyZoomPan: function() {},
    throttle: function(fn) { return fn; },
  };
}

function handleSvgClick(e) {
  if (state.dragging !== null) return;
  // 只拦截真正点在节点上的情况，g/line 等容器元素不算
  if (e.target.tagName === 'circle' || e.target.tagName === 'text') return;
  var svg = document.getElementById('canvas-svg');
  if (!svg) return;
  var rect = svg.getBoundingClientRect();
  var x = (e.clientX - rect.left) * (state.svgW / rect.width);
  var y = (e.clientY - rect.top) * (state.svgH / rect.height);
  if (state.selectedNode) {
    state.selectedNode = null;
    renderCanvas();
    return;
  }
  // Click empty space: add node with selected type
  var type = state.selectedEdgeType === 'emotion' ? 'person' : state.selectedEdgeType === 'space' ? 'place' : state.selectedEdgeType === 'time' ? 'event' : 'item';
  addNode('新节点', type, x, y);
  renderCanvas();
  getGraphApis().startAnimation();
  renderRightPanelOnly();
}

function handleMouseMove(e) {
  if (state.dragging === null) return;
  var svg = document.getElementById('canvas-svg');
  if (!svg) return;
  var rect = svg.getBoundingClientRect();
  var clientX = e.touches ? e.touches[0].clientX : e.clientX;
  var clientY = e.touches ? e.touches[0].clientY : e.clientY;
  var x = (clientX - rect.left) * (state.svgW / rect.width) - state.dragOffset.x;
  var y = (clientY - rect.top) * (state.svgH / rect.height) - state.dragOffset.y;
  for (var i = 0; i < state.nodes.length; i++) {
    if (state.nodes[i].id === state.dragging) {
      state.nodes[i].x = Math.max(40, Math.min(state.svgW - 40, x));
      state.nodes[i].y = Math.max(40, Math.min(state.svgH - 40, y));
      break;
    }
  }
  renderCanvas();
}

function handleMouseUp() {
  if (state.dragging !== null) {
    for (var i = 0; i < state.nodes.length; i++) {
      if (state.nodes[i].id === state.dragging) {
        state.nodes[i].fixed = false;
        break;
      }
    }
    state.dragging = null;
    getGraphApis().startAnimation();
  }
}

function handleNodeMouseDown(e, node) {
  e.stopPropagation();
  state.dragging = node.id;
  var svg = document.getElementById('canvas-svg');
  var rect = svg.getBoundingClientRect();
  var clientX = e.touches ? e.touches[0].clientX : e.clientX;
  var clientY = e.touches ? e.touches[0].clientY : e.clientY;
  state.dragOffset = {
    x: (clientX - rect.left) * (state.svgW / rect.width) - node.x,
    y: (clientY - rect.top) * (state.svgH / rect.height) - node.y,
  };
  node.fixed = true;
  getGraphApis().stopAnimation();
}

function handleGlobalKey(e) {
  // 忽略输入框内的快捷键
  var target = e.target;
  if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) {
    if (e.key === 'Escape') {
      target.blur();
    }
    return;
  }
  if (e.key === 'Delete' || e.key === 'Backspace') {
    if (state.selectedNode) {
      var id = state.selectedNode.id;
      state.nodes = state.nodes.filter(function(n) { return n.id !== id; });
      state.edges = state.edges.filter(function(e) { return e.from !== id && e.to !== id; });
      state.selectedNode = null;
      pushHistory();
      render();
      getGraphApis().startAnimation();
      e.preventDefault();
    }
  }
  if (e.key === 'z' && (e.ctrlKey || e.metaKey) && !e.shiftKey) {
    undo(); e.preventDefault();
  }
  if ((e.key === 'y' && (e.ctrlKey || e.metaKey)) || (e.key === 'z' && (e.ctrlKey || e.metaKey) && e.shiftKey)) {
    redo(); e.preventDefault();
  }
  if (e.key === 'Escape') {
    state.selectedNode = null;
    renderCanvas();
  }
  if (e.key === '?' && !e.ctrlKey && !e.metaKey && !e.altKey) {
    showKeyboardShortcuts(); e.preventDefault();
  }
}

// ============ 键盘快捷键说明面板 ============
var _shortcutOverlay = null;
function showKeyboardShortcuts() {
  if (_shortcutOverlay) return;
  var savedFocus = document.activeElement;
  _shortcutOverlay = el('div', {
    className: 'onboarding-overlay',
    role: 'dialog',
    'aria-modal': 'true',
    'aria-label': '键盘快捷键',
    onclick: function(e) { if (e.target === _shortcutOverlay) closeKeyboardShortcuts(savedFocus); },
  });
  var card = el('div', { className: 'onboarding-card', style: { maxWidth: '400px' } }, [
    el('div', { className: 'onboarding-step-tag' }, '帮助'),
    el('h2', { className: 'onboarding-title' }, '键盘快捷键'),
    el('div', { style: { fontSize: '0.9rem', lineHeight: '1.8', color: 'var(--ink2)' } }, [
      el('div', {}, [el('kbd', { style: { fontFamily: 'monospace', background: 'var(--bg2)', padding: '2px 6px', borderRadius: '4px' } }, 'Ctrl+Z'), ' 撤销']),
      el('div', {}, [el('kbd', { style: { fontFamily: 'monospace', background: 'var(--bg2)', padding: '2px 6px', borderRadius: '4px' } }, 'Ctrl+Y / Ctrl+Shift+Z'), ' 重做']),
      el('div', {}, [el('kbd', { style: { fontFamily: 'monospace', background: 'var(--bg2)', padding: '2px 6px', borderRadius: '4px' } }, 'Delete / Backspace'), ' 删除选中节点']),
      el('div', {}, [el('kbd', { style: { fontFamily: 'monospace', background: 'var(--bg2)', padding: '2px 6px', borderRadius: '4px' } }, 'Esc'), ' 取消选择']),
      el('div', {}, [el('kbd', { style: { fontFamily: 'monospace', background: 'var(--bg2)', padding: '2px 6px', borderRadius: '4px' } }, '?'), ' 打开快捷键帮助']),
    ]),
    el('div', { className: 'onboarding-actions', style: { justifyContent: 'center' } }, [
      el('button', {
        className: 'onboarding-btn onboarding-btn-primary',
        onclick: function() { closeKeyboardShortcuts(savedFocus); },
      }, '关闭'),
    ]),
  ]);
  _shortcutOverlay.appendChild(card);
  document.body.appendChild(_shortcutOverlay);
  // 聚焦关闭按钮
  var closeBtn = card.querySelector('button');
  if (closeBtn) closeBtn.focus();
}

function closeKeyboardShortcuts(returnFocusTo) {
  if (_shortcutOverlay && _shortcutOverlay.parentNode) {
    _shortcutOverlay.parentNode.removeChild(_shortcutOverlay);
  }
  _shortcutOverlay = null;
  if (returnFocusTo && returnFocusTo.focus) returnFocusTo.focus();
}

// ============ 焦点管理工具 ============
export function trapFocus(container, returnFocusTo) {
  if (!container) return function() {};
  var focusables = container.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
  var first = focusables[0];
  var last = focusables[focusables.length - 1];
  if (first) first.focus();

  function onKeydown(e) {
    if (e.key !== 'Tab') return;
    if (e.shiftKey) {
      if (document.activeElement === first) {
        e.preventDefault();
        last.focus();
      }
    } else {
      if (document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  }
  container.addEventListener('keydown', onKeydown);
  return function restoreFocus() {
    container.removeEventListener('keydown', onKeydown);
    if (returnFocusTo && returnFocusTo.focus) returnFocusTo.focus();
  };
}

function saveState() {
  try {
    var payload = {
      version: STATE_VERSION,
      nodes: state.nodes.map(function(n) {
        return { id: n.id, label: n.label, type: n.type, x: n.x, y: n.y, isAnon: n.isAnon, matchedTo: n.matchedTo, matchConfidence: n.matchConfidence };
      }),
      edges: state.edges,
      nodeIdCounter: state.nodeIdCounter,
      currentDay: state.currentDay,
      daySnapshots: state.daySnapshots,
      baselineMetrics: state.baselineMetrics,
      welcomeDismissed: state.welcomeDismissed,
      voiceFeedback: state.voiceFeedback,
      sessionHistory: state.sessionHistory,
      guidedMode: state.guidedMode,
      trendWindow: state.trendWindow,
      trainingScores: state.trainingScores,
      lastEmotion: state.lastEmotion,
    };
    localStorage.setItem('cognitive-garden-state', JSON.stringify(payload));
  } catch (e) {}
  // API sync: if logged in, push to backend (async, non-blocking)
  if (isLoggedIn()) {
    syncState({
      nodes: state.nodes.map(function(n) { return { id: n.id, label: n.label, type: n.type, x: n.x, y: n.y, isAnon: n.isAnon, matchedTo: n.matchedTo, matchConfidence: n.matchConfidence }; }),
      edges: state.edges,
      node_id_counter: state.nodeIdCounter,
      current_day: state.currentDay,
      day_snapshots: state.daySnapshots,
      baseline_metrics: state.baselineMetrics,
      welcome_dismissed: state.welcomeDismissed,
    }).catch(function(err) { console.warn('State sync failed:', err); });
  }
}

function loadState() {
  // Try backend first if logged in
  if (isLoggedIn()) {
    loadServerState().then(function(payload) {
      if (payload.nodes && payload.nodes.length > 0) {
        state.nodes = payload.nodes.map(function(n) {
          return {
            id: n.id, label: n.label, type: n.type,
            x: n.x, y: n.y, vx: 0, vy: 0,
            radius: n.type === 'self' ? 28 : n.type === 'anon' ? 22 : 20,
            isAnon: n.isAnon, matchedTo: n.matchedTo || null,
            matchConfidence: n.matchConfidence || 0, fixed: false,
          };
        });
        state.edges = payload.edges || [];
        state.nodeIdCounter = payload.node_id_counter || state.nodes.length;
        state.currentDay = payload.current_day || 0;
        state.daySnapshots = payload.day_snapshots || {};
        state.baselineMetrics = payload.baseline_metrics || null;
        state.welcomeDismissed = payload.welcome_dismissed || false;
        render();
        getGraphApis().startAnimation();
        return;
      }
      loadLocalState();
    }).catch(function() { loadLocalState(); });
  } else {
    loadLocalState();
  }
}

function loadLocalState() {
  try {
    var raw = localStorage.getItem('cognitive-garden-state');
    if (!raw) return;
    var payload = JSON.parse(raw);
    // 状态版本校验：schema 变化时避免旧数据导致异常
    if (payload.version && payload.version !== STATE_VERSION) {
      console.warn('Local state version mismatch, clearing old state');
      localStorage.removeItem('cognitive-garden-state');
      return;
    }
    if (payload.nodes && payload.nodes.length > 0) {
      state.nodes = payload.nodes.map(function(n) {
        return {
          id: n.id, label: n.label, type: n.type,
          x: n.x, y: n.y, vx: 0, vy: 0,
          radius: n.type === 'self' ? 28 : n.type === 'anon' ? 22 : 20,
          isAnon: n.isAnon, matchedTo: n.matchedTo || null,
          matchConfidence: n.matchConfidence || 0, fixed: false,
        };
      });
      state.edges = payload.edges || [];
      state.nodeIdCounter = payload.nodeIdCounter || state.nodes.length;
      state.currentDay = payload.currentDay || 0;
      state.daySnapshots = payload.daySnapshots || {};
      state.baselineMetrics = payload.baselineMetrics || null;
      state.welcomeDismissed = payload.welcomeDismissed || false;
      state.sessionHistory = payload.sessionHistory || [];
      state.guidedMode = payload.guidedMode !== undefined ? payload.guidedMode : true;
      state.trendWindow = payload.trendWindow || 30;
      state.trainingScores = payload.trainingScores || [];
      state.lastEmotion = payload.lastEmotion || null;
    }
  } catch (e) {}
}

function pushHistory() {
  var snapshot = {
    nodes: JSON.parse(JSON.stringify(state.nodes.map(function(n) {
      return { id: n.id, label: n.label, type: n.type, x: n.x, y: n.y, isAnon: n.isAnon, matchedTo: n.matchedTo, matchConfidence: n.matchConfidence };
    }))),
    edges: JSON.parse(JSON.stringify(state.edges)),
    nodeIdCounter: state.nodeIdCounter,
  };
  state.historyStack = state.historyStack.slice(0, state.historyIndex + 1);
  state.historyStack.push(snapshot);
  state.historyIndex = state.historyStack.length - 1;
  if (state.historyStack.length > 50) { state.historyStack.shift(); state.historyIndex--; }
}

function undo() {
  if (state.historyIndex <= 0) return;
  state.historyIndex--;
  var s = state.historyStack[state.historyIndex];
  state.nodes = s.nodes.map(function(n) {
    return {
      id: n.id, label: n.label, type: n.type, x: n.x, y: n.y, vx: 0, vy: 0,
      radius: n.type === 'self' ? 28 : n.type === 'anon' ? 22 : 20,
      isAnon: n.isAnon, matchedTo: n.matchedTo, matchConfidence: n.matchConfidence, fixed: false,
    };
  });
  state.edges = JSON.parse(JSON.stringify(s.edges));
  state.nodeIdCounter = s.nodeIdCounter;
  render();
  getGraphApis().startAnimation();
}

function redo() {
  if (state.historyIndex >= state.historyStack.length - 1) return;
  state.historyIndex++;
  var s = state.historyStack[state.historyIndex];
  state.nodes = s.nodes.map(function(n) {
    return {
      id: n.id, label: n.label, type: n.type, x: n.x, y: n.y, vx: 0, vy: 0,
      radius: n.type === 'self' ? 28 : n.type === 'anon' ? 22 : 20,
      isAnon: n.isAnon, matchedTo: n.matchedTo, matchConfidence: n.matchConfidence, fixed: false,
    };
  });
  state.edges = JSON.parse(JSON.stringify(s.edges));
  state.nodeIdCounter = s.nodeIdCounter;
  render();
  getGraphApis().startAnimation();
}

function exportJSON() {
  var payload = {
    nodes: state.nodes,
    edges: state.edges,
    nodeIdCounter: state.nodeIdCounter,
    currentDay: state.currentDay,
    exportedAt: new Date().toISOString(),
  };
  var blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a');
  a.href = url;
  a.download = 'cognitive-garden-' + Date.now() + '.json';
  a.click();
  URL.revokeObjectURL(url);
}

function exportCSV() {
  var lines = ['id,label,type,x,y,isAnon'];
  state.nodes.forEach(function(n) {
    lines.push([n.id, '"' + (n.label || '').replace(/"/g, '""') + '"', n.type, n.x.toFixed(1), n.y.toFixed(1), n.isAnon ? 1 : 0].join(','));
  });
  lines.push('');
  lines.push('from,to,type,weight');
  state.edges.forEach(function(e) {
    lines.push([e.from, e.to, e.type, e.weight || 1].join(','));
  });
  var blob = new Blob([lines.join('\n')], { type: 'text/csv' });
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a');
  a.href = url;
  a.download = 'cognitive-garden-' + Date.now() + '.csv';
  a.click();
  URL.revokeObjectURL(url);
}

function exportPNG() {
  var svg = document.getElementById('canvas-svg');
  if (!svg) return;
  var xml = new XMLSerializer().serializeToString(svg);
  var svgBlob = new Blob([xml], { type: 'image/svg+xml;charset=utf-8' });
  var url = URL.createObjectURL(svgBlob);
  var img = new Image();
  img.onload = function() {
    var canvas = document.createElement('canvas');
    canvas.width = state.svgW;
    canvas.height = state.svgH;
    var ctx = canvas.getContext('2d');
    ctx.fillStyle = '#FAF7F0';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0);
    URL.revokeObjectURL(url);
    canvas.toBlob(function(blob) {
      var pngUrl = URL.createObjectURL(blob);
      var a = document.createElement('a');
      a.href = pngUrl;
      a.download = 'cognitive-garden-' + Date.now() + '.png';
      a.click();
      URL.revokeObjectURL(pngUrl);
    });
  };
  img.src = url;
}

export { handleSvgClick, handleMouseMove, handleMouseUp, handleNodeMouseDown, handleGlobalKey, saveState, loadState, pushHistory, undo, redo, exportJSON, exportCSV, exportPNG, showKeyboardShortcuts, closeKeyboardShortcuts };
