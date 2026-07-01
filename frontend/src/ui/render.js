// ============ UI RENDER ============
import { state, NODE_TYPES, EDGE_TYPES, zoomPan } from '../state.js';
import { el } from './components.js';
import { computeMetrics } from '../graph/metrics.js';
import { handleSvgClick, handleMouseMove, handleMouseUp, handleNodeMouseDown } from './interactions.js';
import { showOnboarding } from './onboarding.js';
import { renderHeader } from './panels/header.js';
import { renderTimeline } from './panels/timeline.js';
import { renderRightPanel, renderRightPanelOnly } from './panels/rightPanel.js';
import { renderLeftPanel } from './panels/leftPanel.js';

function getGraphApis() {
  return window.__graphApis || {
    startAnimation: function() {},
    stopAnimation: function() {},
    applyZoomPan: function() {},
    throttle: function(fn) { return fn; },
  };
}

function render() {
  if (!state.welcomeDismissed) {
    showOnboarding();
  }
  var app = document.getElementById('app');
  
  // First render: full build
  if (!app.querySelector('.main')) {
    app.innerHTML = '';

    var skipLink = el('a', {
      className: 'skip-link',
      href: '#canvas-wrap',
      onclick: function(e) {
        e.preventDefault();
        var target = document.getElementById('canvas-wrap');
        if (target) target.focus();
      }
    }, '跳到主内容');
    app.appendChild(skipLink);

    app.appendChild(renderHeader());
    var main = el('div', { className: 'main' });
    main.appendChild(renderLeftPanel());
    main.appendChild(renderCanvas());
    main.appendChild(renderRightPanel());
    app.appendChild(main);
    app.appendChild(renderTimeline());
    return;
  }
  
  // Incremental update: replace only changed panels
  var existingHeader = app.querySelector('.header');
  if (existingHeader) app.replaceChild(renderHeader(), existingHeader);
  
  var main = app.querySelector('.main');
  if (main) {
    var existingLeft = main.querySelector('.panel-left');
    if (existingLeft) main.replaceChild(renderLeftPanel(), existingLeft);
    renderCanvas();
    var existingRight = main.querySelector('.panel-right');
    if (existingRight) main.replaceChild(renderRightPanel(), existingRight);
  }
  
  var existingTimeline = app.querySelector('.timeline');
  if (existingTimeline) app.replaceChild(renderTimeline(), existingTimeline);
}

function renderLeftPanelOnly() {
  var main = document.querySelector('.main');
  if (!main) return;
  var existing = main.querySelector('.panel-left');
  if (existing) {
    main.replaceChild(renderLeftPanel(), existing);
  }
}

function renderTimelineOnly() {
  var app = document.getElementById('app');
  var existing = app.querySelector('.timeline');
  if (existing) {
    app.replaceChild(renderTimeline(), existing);
  }
}

function renderCanvas() {
  var existing = document.getElementById('canvas-wrap');
  if (existing) {
    updateSVGDimensions();
    updateSVG(document.getElementById('canvas-svg'));
    return existing;
  }
  var wrap = el('div', { className: 'canvas-wrap', id: 'canvas-wrap', tabindex: '-1' });
  wrap.appendChild(el('div', { className: 'canvas-bg' }));

  var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 ' + state.svgW + ' ' + state.svgH);
  svg.setAttribute('class', 'canvas-svg');
  svg.setAttribute('id', 'canvas-svg');
  svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
  svg.setAttribute('role', 'application');
  svg.setAttribute('aria-label', '记忆网络图画布，点击空白添加节点，拖拽移动节点，选中节点后点击另一节点连线');
  
  // Event delegation: combined click handler for background and nodes
  svg.addEventListener('click', function(e) {
    var nodeEl = e.target.closest('[data-node-id]');
    if (nodeEl) {
      var nodeId = nodeEl.getAttribute('data-node-id');
      var n = state.nodes.find(function(n) { return String(n.id) === nodeId; });
      if (n) {
        e.stopPropagation();
        state.selectedNode = n;
        renderEngine.invalidate('canvas');
      }
    } else {
      handleSvgClick(e);
    }
  });
  svg.addEventListener('mousedown', function(e) {
    var nodeEl = e.target.closest('[data-node-id]');
    if (nodeEl) {
      var nodeId = nodeEl.getAttribute('data-node-id');
      var n = state.nodes.find(function(n) { return String(n.id) === nodeId; });
      if (n) handleNodeMouseDown(e, n);
    }
  });
  svg.addEventListener('mousemove', handleMouseMove);
  svg.addEventListener('mouseup', handleMouseUp);
  svg.addEventListener('mouseleave', handleMouseUp);
  var throttledZoom = getGraphApis().throttle(function(e) {
    var zoomSpeed = 0.001;
    zoomPan.scale = Math.max(0.3, Math.min(3, zoomPan.scale - e.deltaY * zoomSpeed));
    getGraphApis().applyZoomPan(svg);
  }, 16);
  svg.addEventListener('wheel', function(e) {
    e.preventDefault();
    throttledZoom(e);
  }, { passive: false });

  // ========== 触摸手势支持 ==========
  var _touchState = {
    touches: [],
    lastDist: 0,
    lastCenter: { x: 0, y: 0 },
    isPanning: false,
    panVelocity: { x: 0, y: 0 },
    lastPanTime: 0,
    longPressTimer: null,
    longPressNode: null,
    longPressStart: { x: 0, y: 0 },
  };

  function _getTouchPos(touch) {
    var rect = svg.getBoundingClientRect();
    return {
      x: (touch.clientX - rect.left) * (state.svgW / rect.width),
      y: (touch.clientY - rect.top) * (state.svgH / rect.height),
    };
  }

  function _distance(a, b) {
    return Math.sqrt((a.x - b.x) * (a.x - b.x) + (a.y - b.y) * (a.y - b.y));
  }

  function _showNodeMenu(node, x, y) {
    var existing = document.getElementById('node-context-menu');
    if (existing) existing.remove();
    var menu = el('div', {
      id: 'node-context-menu',
      style: {
        position: 'absolute',
        left: x + 'px',
        top: y + 'px',
        zIndex: 1000,
        background: '#fff',
        border: '1px solid var(--rule)',
        borderRadius: '8px',
        boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
        display: 'flex',
        flexDirection: 'column',
        minWidth: '120px',
        overflow: 'hidden',
      },
      role: 'menu',
    });
    var items = [
      { label: '编辑', action: function() {
        var label = prompt('编辑节点名称:', node.label);
        if (label) { node.label = label; renderCanvas(); }
      }},
      { label: '连接', action: function() {
        state.selectedNode = node;
        renderCanvas();
      }},
      { label: '删除', action: function() {
        state.nodes = state.nodes.filter(function(n) { return n.id !== node.id; });
        state.edges = state.edges.filter(function(e) { return e.from !== node.id && e.to !== node.id; });
        renderCanvas();
        getGraphApis().startAnimation();
      }},
    ];
    items.forEach(function(it) {
      var btn = el('button', {
        style: {
          border: 'none',
          background: 'transparent',
          padding: '10px 14px',
          textAlign: 'left',
          cursor: 'pointer',
          fontSize: '0.9rem',
          color: it.label === '删除' ? 'var(--danger)' : 'var(--ink)',
        },
        role: 'menuitem',
        onclick: function() { it.action(); menu.remove(); },
      }, it.label);
      menu.appendChild(btn);
    });
    wrap.appendChild(menu);
    // 点击空白关闭菜单
    setTimeout(function() {
      svg.addEventListener('click', function _closeMenu() { menu.remove(); svg.removeEventListener('click', _closeMenu); });
    }, 50);
  }

  svg.addEventListener('touchstart', function(e) {
    e.preventDefault();
    var touches = e.touches;
    _touchState.touches = Array.from(touches);
    if (touches.length === 1) {
      var pos = _getTouchPos(touches[0]);
      var nodeEl = e.target.closest('[data-node-id]');
      if (nodeEl) {
        var nodeId = nodeEl.getAttribute('data-node-id');
        var n = state.nodes.find(function(n) { return String(n.id) === nodeId; });
        if (n) {
          _touchState.longPressNode = n;
          _touchState.longPressStart = { x: pos.x, y: pos.y };
          var rect = wrap.getBoundingClientRect();
          var menuX = touches[0].clientX - rect.left;
          var menuY = touches[0].clientY - rect.top;
          _touchState.longPressTimer = setTimeout(function() {
            if (_touchState.longPressNode) {
              _showNodeMenu(_touchState.longPressNode, menuX, menuY);
              _touchState.longPressNode = null;
            }
          }, 600);
          handleNodeMouseDown(e, n);
        }
      } else {
        _touchState.isPanning = true;
        _touchState.lastCenter = pos;
        _touchState.lastPanTime = Date.now();
      }
    } else if (touches.length === 2) {
      _touchState.lastDist = _distance(
        _getTouchPos(touches[0]),
        _getTouchPos(touches[1])
      );
    }
  }, { passive: false });

  svg.addEventListener('touchmove', function(e) {
    e.preventDefault();
    var touches = e.touches;
    // 节点拖拽
    if (state.dragging !== null) {
      handleMouseMove(e);
      if (_touchState.longPressTimer) {
        clearTimeout(_touchState.longPressTimer);
        _touchState.longPressTimer = null;
        _touchState.longPressNode = null;
      }
      return;
    }
    if (touches.length === 1 && _touchState.isPanning) {
      var pos = _getTouchPos(touches[0]);
      var now = Date.now();
      var dt = now - _touchState.lastPanTime;
      if (dt > 0) {
        _touchState.panVelocity = {
          x: (pos.x - _touchState.lastCenter.x) / dt,
          y: (pos.y - _touchState.lastCenter.y) / dt,
        };
      }
      zoomPan.panX += pos.x - _touchState.lastCenter.x;
      zoomPan.panY += pos.y - _touchState.lastCenter.y;
      _touchState.lastCenter = pos;
      _touchState.lastPanTime = now;
      getGraphApis().applyZoomPan(svg);
      // 取消长按计时
      if (_touchState.longPressTimer) {
        clearTimeout(_touchState.longPressTimer);
        _touchState.longPressTimer = null;
        _touchState.longPressNode = null;
      }
    } else if (touches.length === 2) {
      var dist = _distance(
        _getTouchPos(touches[0]),
        _getTouchPos(touches[1])
      );
      if (_touchState.lastDist > 0) {
        var scaleFactor = dist / _touchState.lastDist;
        zoomPan.scale = Math.max(0.3, Math.min(3, zoomPan.scale * scaleFactor));
        getGraphApis().applyZoomPan(svg);
      }
      _touchState.lastDist = dist;
    }
  }, { passive: false });

  svg.addEventListener('touchend', function(e) {
    e.preventDefault();
    var touches = e.touches;
    if (touches.length === 0) {
      // 惯性滑动
      if (_touchState.isPanning && (Math.abs(_touchState.panVelocity.x) > 0.01 || Math.abs(_touchState.panVelocity.y) > 0.01)) {
        var vx = _touchState.panVelocity.x * 16;
        var vy = _touchState.panVelocity.y * 16;
        var friction = 0.9;
        function inertia() {
          if (Math.abs(vx) < 0.5 && Math.abs(vy) < 0.5) return;
          zoomPan.panX += vx;
          zoomPan.panY += vy;
          vx *= friction;
          vy *= friction;
          getGraphApis().applyZoomPan(svg);
          requestAnimationFrame(inertia);
        }
        inertia();
      }
      _touchState.isPanning = false;
      _touchState.panVelocity = { x: 0, y: 0 };
      if (_touchState.longPressTimer) {
        clearTimeout(_touchState.longPressTimer);
        _touchState.longPressTimer = null;
        _touchState.longPressNode = null;
      }
      handleMouseUp();
    } else if (touches.length === 1) {
      _touchState.lastDist = 0;
      _touchState.isPanning = true;
      _touchState.lastCenter = _getTouchPos(touches[0]);
    }
  }, { passive: false });

  wrap.appendChild(svg);

  // Update dimensions after DOM insertion
  setTimeout(function() {
    updateSVGDimensions();
    if (state.nodes.length > 0) getGraphApis().startAnimation();
  }, 50);

  // Toolbar
  var toolbar = el('div', { className: 'canvas-toolbar' });
  toolbar.appendChild(el('button', { className: 'mode-btn active' }, '织网模式'));
  var baselineBtn = el('button', { className: 'mode-btn' }, '基准对比');
  baselineBtn.onclick = function() {
    if (!state.baselineMetrics) {
      state.baselineMetrics = computeMetrics();
      alert('已保存当前网络为基准图');
    } else {
      if (confirm('重新以当前网络为基准？')) {
        state.baselineMetrics = computeMetrics();
      }
    }
    renderEngine.invalidate('right');
  };
  toolbar.appendChild(baselineBtn);
  wrap.appendChild(toolbar);

  wrap.appendChild(el('div', { className: 'canvas-overlay' }, '点击空白添加节点 · 拖拽移动 · 选中后点击另一节点连线'));
  wrap.appendChild(el('div', { className: 'zoom-hint' }, '滚轮缩放 · 拖拽节点'));

  return wrap;
}

function updateSVG(svg) {
  if (!svg) return;
  var g = svg.querySelector('.zoom-pan-group');
  if (!g) {
    g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.setAttribute('class', 'zoom-pan-group');
    svg.appendChild(g);
  }

  // Check if structure changed (node/edge count changed)
  var existingEdges = g.querySelector('.edges-group');
  var existingNodes = g.querySelector('.nodes-group');
  var structureChanged = !existingEdges || !existingNodes ||
    existingEdges.children.length !== state.edges.length ||
    existingNodes.children.length !== state.nodes.length;

  if (structureChanged) {
    // Full rebuild needed
    while (g.firstChild) g.removeChild(g.firstChild);
    _rebuildSVG(g);
  } else {
    // Incremental update: only update positions and selection states
    _updateSVGIncremental(g);
  }

  getGraphApis().applyZoomPan(svg);
}

function _rebuildSVG(g) {
  var edgesGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
  edgesGroup.setAttribute('class', 'edges-group');
  state.edges.forEach(function(e, idx) {
    var fromNode = state.nodes.find(function(n) { return n.id === e.from; });
    var toNode = state.nodes.find(function(n) { return n.id === e.to; });
    if (!fromNode || !toNode) return;
    var info = EDGE_TYPES[e.type] || EDGE_TYPES.custom;
    var line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('data-edge-idx', idx);
    line.setAttribute('x1', fromNode.x);
    line.setAttribute('y1', fromNode.y);
    line.setAttribute('x2', toNode.x);
    line.setAttribute('y2', toNode.y);
    line.setAttribute('stroke', info.color);
    line.setAttribute('stroke-width', info.width);
    if (info.dash !== 'none') line.setAttribute('stroke-dasharray', info.dash);
    line.setAttribute('class', 'graph-edge');
    edgesGroup.appendChild(line);
  });
  g.appendChild(edgesGroup);

  var nodesGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
  nodesGroup.setAttribute('class', 'nodes-group');
  state.nodes.forEach(function(n) {
    var info = NODE_TYPES[n.type] || NODE_TYPES.item;
    var isSelected = state.selectedNode && state.selectedNode.id === n.id;
    var nodeG = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    nodeG.setAttribute('data-node-id', n.id);
    nodeG.setAttribute('class', 'graph-node' + (isSelected ? ' selected' : '') + (n.isAnon ? ' anon' : ''));
    nodeG.setAttribute('transform', 'translate(' + n.x + ',' + n.y + ')');

    var circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    circle.setAttribute('r', n.radius);
    circle.setAttribute('fill', info.color);
    circle.setAttribute('stroke', '#fff');
    circle.setAttribute('stroke-width', '3');
    nodeG.appendChild(circle);

    var text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    text.setAttribute('text-anchor', 'middle');
    text.setAttribute('dy', '0.35em');
    text.setAttribute('fill', '#fff');
    text.setAttribute('font-size', n.type === 'self' ? '14' : '12');
    text.setAttribute('font-weight', '600');
    text.textContent = n.isAnon ? '?' : n.label;
    nodeG.appendChild(text);

    if (n.isAnon && n.matchedTo) {
      var sub = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      sub.setAttribute('text-anchor', 'middle');
      sub.setAttribute('y', n.radius + 14);
      sub.setAttribute('fill', '#837A6E');
      sub.setAttribute('font-size', '10');
      sub.textContent = n.matchedTo;
      nodeG.appendChild(sub);
    }

    nodesGroup.appendChild(nodeG);
  });
  g.appendChild(nodesGroup);
}

function _updateSVGIncremental(g) {
  var edgesGroup = g.querySelector('.edges-group');
  var nodesGroup = g.querySelector('.nodes-group');
  if (!edgesGroup || !nodesGroup) return;

  // Update edge positions
  var edgeLines = edgesGroup.querySelectorAll('line');
  state.edges.forEach(function(e, idx) {
    var line = edgeLines[idx];
    if (!line) return;
    var fromNode = state.nodes.find(function(n) { return n.id === e.from; });
    var toNode = state.nodes.find(function(n) { return n.id === e.to; });
    if (!fromNode || !toNode) return;
    line.setAttribute('x1', fromNode.x);
    line.setAttribute('y1', fromNode.y);
    line.setAttribute('x2', toNode.x);
    line.setAttribute('y2', toNode.y);
  });

  // Update node positions and selection states
  var nodeGroups = nodesGroup.querySelectorAll('g[data-node-id]');
  nodeGroups.forEach(function(nodeG) {
    var nodeId = nodeG.getAttribute('data-node-id');
    var n = state.nodes.find(function(n) { return String(n.id) === nodeId; });
    if (!n) return;
    var isSelected = state.selectedNode && state.selectedNode.id === n.id;
    var newClass = 'graph-node' + (isSelected ? ' selected' : '') + (n.isAnon ? ' anon' : '');
    if (nodeG.getAttribute('class') !== newClass) {
      nodeG.setAttribute('class', newClass);
    }
    nodeG.setAttribute('transform', 'translate(' + n.x + ',' + n.y + ')');
  });
}


function updateSVGDimensions() {
  var wrap = document.getElementById('canvas-wrap');
  if (!wrap) return;
  var rect = wrap.getBoundingClientRect();
  if (rect.width > 50 && rect.height > 50) {
    state.svgW = Math.round(rect.width);
    state.svgH = Math.round(rect.height);
    var svg = document.getElementById('canvas-svg');
    if (svg) {
      svg.setAttribute('viewBox', '0 0 ' + state.svgW + ' ' + state.svgH);
    }
  }
}

export var renderEngine = {
  _queue: new Set(),
  _scheduled: false,
  invalidate: function(panel) {
    this._queue.add(panel);
    if (!this._scheduled) {
      this._scheduled = true;
      requestAnimationFrame(() => this._flush());
    }
  },
  _flush: function() {
    var panels = Array.from(this._queue);
    this._queue.clear();
    this._scheduled = false;
    if (panels.indexOf('full') !== -1 || !document.getElementById('app').querySelector('.main')) {
      render();
      return;
    }
    if (panels.indexOf('header') !== -1) {
      var app = document.getElementById('app');
      var existingHeader = app.querySelector('.header');
      if (existingHeader) app.replaceChild(renderHeader(), existingHeader);
    }
    if (panels.indexOf('left') !== -1) renderLeftPanelOnly();
    if (panels.indexOf('right') !== -1) renderRightPanelOnly();
    if (panels.indexOf('canvas') !== -1) renderCanvas();
    if (panels.indexOf('timeline') !== -1) renderTimelineOnly();
  }
};

export { render, renderCanvas, renderTimeline, renderRightPanel, renderRightPanelOnly, renderLeftPanel, renderLeftPanelOnly, renderTimelineOnly, updateSVGDimensions };
