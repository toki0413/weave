// ============ 2D / 3D VIEW SWITCHER ============
// Manages toggling between SVG graph and WebGL nebula views

import { state } from '../state.js';
import { el } from '../ui/components.js';

var _currentMode = localStorage.getItem('viewMode') || '2d';
var _nebulaController = null;
var _onNodeClick = null;

export function renderViewSwitcher(container) {
  var wrap = el('div', {
    className: 'view-switcher-3d',
    style: {
      display: 'flex',
      gap: '2px',
      background: 'rgba(0,0,0,0.15)',
      borderRadius: '100px',
      padding: '3px',
      alignItems: 'center',
    }
  });

  var btn2D = el('button', {
    className: 'view-mode-btn' + (_currentMode === '2d' ? ' active' : ''),
    style: {
      padding: '6px 14px',
      border: 'none',
      borderRadius: '100px',
      background: _currentMode === '2d' ? '#fff' : 'transparent',
      color: _currentMode === '2d' ? 'var(--accent-d)' : 'rgba(255,255,255,0.6)',
      fontSize: '0.8rem',
      fontWeight: '600',
      cursor: 'pointer',
      transition: 'all 0.2s',
      whiteSpace: 'nowrap',
    },
    onclick: function() { setViewMode('2d'); }
  }, '2D 视图');

  var btn3D = el('button', {
    className: 'view-mode-btn' + (_currentMode === '3d' ? ' active' : ''),
    style: {
      padding: '6px 14px',
      border: 'none',
      borderRadius: '100px',
      background: _currentMode === '3d' ? '#fff' : 'transparent',
      color: _currentMode === '3d' ? 'var(--accent-d)' : 'rgba(255,255,255,0.6)',
      fontSize: '0.8rem',
      fontWeight: '600',
      cursor: 'pointer',
      transition: 'all 0.2s',
      whiteSpace: 'nowrap',
    },
    onclick: function() { setViewMode('3d'); }
  }, '3D 星云');

  wrap.appendChild(btn2D);
  wrap.appendChild(btn3D);
  container.appendChild(wrap);

  // Expose update method for external mode changes
  wrap._update = function(mode) {
    _currentMode = mode;
    if (mode === '2d') {
      btn2D.style.background = '#fff'; btn2D.style.color = 'var(--accent-d)';
      btn3D.style.background = 'transparent'; btn3D.style.color = 'rgba(255,255,255,0.6)';
    } else {
      btn3D.style.background = '#fff'; btn3D.style.color = 'var(--accent-d)';
      btn2D.style.background = 'transparent'; btn2D.style.color = 'rgba(255,255,255,0.6)';
    }
  };

  return wrap;
}

export function getViewMode() {
  return _currentMode;
}

export function setViewMode(mode, options) {
  options = options || {};
  if (_currentMode === mode) return;
  _currentMode = mode;
  localStorage.setItem('viewMode', mode);

  // Update any existing switcher UI
  var switchers = document.querySelectorAll('.view-switcher-3d');
  switchers.forEach(function(s) { if (s._update) s._update(mode); });

  if (mode === '3d') {
    // Default to global state if no options provided
    var nodes = options.nodes || (typeof state !== 'undefined' && state.nodes) || [];
    var sessions = options.sessions || (typeof state !== 'undefined' && state.sessionHistory) || [];
    enter3DMode(nodes, sessions, options.onNodeClick, options.container);
  } else {
    exit3DMode();
  }
}

export function enter3DMode(nodes, sessions, onNodeClick, container) {
  // Find the SVG canvas wrapper to replace/hide
  var canvasWrap = document.getElementById('canvas-wrap');
  if (!canvasWrap) {
    console.warn('No canvas-wrap found for 3D mode');
    return;
  }

  // Hide SVG
  var svg = document.getElementById('canvas-svg');
  if (svg) svg.style.display = 'none';
  var canvasBg = canvasWrap.querySelector('.canvas-bg');
  if (canvasBg) canvasBg.style.display = 'none';
  var toolbar = canvasWrap.querySelector('.canvas-toolbar');
  if (toolbar) toolbar.style.display = 'none';
  var overlay = canvasWrap.querySelector('.canvas-overlay');
  if (overlay) overlay.style.display = 'none';
  var zoomHint = canvasWrap.querySelector('.zoom-hint');
  if (zoomHint) zoomHint.style.display = 'none';

  // Clean up any existing 3D
  if (_nebulaController) {
    _nebulaController.destroy();
    _nebulaController = null;
  }

  // Load 3D module dynamically
  import('./memory-nebula.js').then(function(mod) {
    _nebulaController = mod.initMemoryNebula(canvasWrap, nodes || [], sessions || []);
    if (_nebulaController) {
      _onNodeClick = onNodeClick;
      _nebulaController.setOnNodeClick(onNodeClick || function() {});
    } else {
      // Fallback if WebGL failed
      console.warn('3D init failed, reverting to 2D');
      setViewMode('2d');
    }
  }).catch(function(err) {
    console.error('Failed to load 3D module:', err);
    setViewMode('2d');
  });
}

export function exit3DMode() {
  // Destroy WebGL context
  if (_nebulaController) {
    _nebulaController.destroy();
    _nebulaController = null;
  }

  // Restore SVG
  var canvasWrap = document.getElementById('canvas-wrap');
  if (canvasWrap) {
    var svg = document.getElementById('canvas-svg');
    if (svg) svg.style.display = '';
    var canvasBg = canvasWrap.querySelector('.canvas-bg');
    if (canvasBg) canvasBg.style.display = '';
    var toolbar = canvasWrap.querySelector('.canvas-toolbar');
    if (toolbar) toolbar.style.display = '';
    var overlay = canvasWrap.querySelector('.canvas-overlay');
    if (overlay) overlay.style.display = '';
    var zoomHint = canvasWrap.querySelector('.zoom-hint');
    if (zoomHint) zoomHint.style.display = '';
  }
}

export function getNebulaController() {
  return _nebulaController;
}

export function is3DActive() {
  return _currentMode === '3d' && _nebulaController !== null;
}
