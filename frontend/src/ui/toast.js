// ============ 全局 Toast 提示 ============
// 统一显示成功、错误、警告、离线提示，替代零散 alert

import { el } from './components.js';

var container = null;
var timers = {};
var offlineShown = false;

function _ensureContainer() {
  if (container && container.parentNode) return container;
  container = el('div', {
    id: 'toast-container',
    className: 'toast-container',
    role: 'status',
    'aria-live': 'polite',
  });
  document.body.appendChild(container);
  return container;
}

function _iconFor(type) {
  if (type === 'success') return '✓';
  if (type === 'error') return '✕';
  if (type === 'warning') return '⚠';
  if (type === 'offline') return '⚠';
  return 'ℹ';
}

function showToast(message, type, duration) {
  type = type || 'info';
  duration = duration || (type === 'error' ? 5000 : 3000);

  var wrap = _ensureContainer();
  var toast = el('div', {
    className: 'toast toast-' + type,
    'aria-label': type === 'error' ? '错误提示' : type === 'offline' ? '网络提示' : '提示',
  }, [
    el('span', { className: 'toast-icon' }, _iconFor(type)),
    el('span', { className: 'toast-message' }, message),
  ]);

  wrap.appendChild(toast);

  // 触发动画
  requestAnimationFrame(function() { toast.classList.add('show'); });

  var id = 'toast_' + Date.now() + '_' + Math.random();

  function remove() {
    toast.classList.remove('show');
    setTimeout(function() {
      if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, 250);
  }

  if (duration > 0) {
    timers[id] = setTimeout(remove, duration);
  }

  toast.onclick = function() {
    if (timers[id]) { clearTimeout(timers[id]); delete timers[id]; }
    remove();
  };

  return { el: toast, dismiss: remove };
}

// 离线提示：避免重复刷屏
function showOfflineToast(message) {
  if (offlineShown) return;
  offlineShown = true;
  var t = showToast(message || '网络连接异常，请检查网络后重试', 'offline', 0);
  if (t && t.el) {
    var oldRemove = t.dismiss;
    t.dismiss = function() {
      offlineShown = false;
      oldRemove();
    };
    t.el.onclick = t.dismiss;
  }
  return t;
}

function clearOfflineToast() {
  offlineShown = false;
  var wrap = document.getElementById('toast-container');
  if (!wrap) return;
  var offline = wrap.querySelectorAll('.toast-offline');
  offline.forEach(function(n) {
    n.classList.remove('show');
    setTimeout(function() { if (n.parentNode) n.parentNode.removeChild(n); }, 250);
  });
}

export { showToast, showOfflineToast, clearOfflineToast };
