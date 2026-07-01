// ============ 全局错误边界 ============
// 捕获未处理的 JS 异常和 Promise 拒绝，避免用户面对空白页

import { showToast } from './toast.js';
import { el } from './components.js';

function showFatalError(title, message, stack) {
  var existing = document.getElementById('fatal-error-overlay');
  if (existing) existing.parentNode.removeChild(existing);

  var overlay = el('div', {
    id: 'fatal-error-overlay',
    className: 'fatal-error-overlay',
    role: 'alert',
  });

  var card = el('div', { className: 'fatal-error-card' }, [
    el('h2', { className: 'fatal-error-title' }, title || '出错了'),
    el('p', { className: 'fatal-error-message' }, message || '应用遇到意外问题，请尝试刷新页面。'),
  ]);

  if (stack) {
    card.appendChild(el('pre', { className: 'fatal-error-stack' }, stack));
  }

  card.appendChild(el('button', {
    className: 'fatal-error-btn',
    onclick: function() { location.reload(); },
  }, '刷新页面'));

  overlay.appendChild(card);
  document.body.appendChild(overlay);
}

window.onerror = function(message, source, lineno, colno, err) {
  console.error('Global error:', message, source, lineno, colno, err);
  showToast('程序运行出错，请刷新页面重试', 'error', 5000);
  return false;
};

window.addEventListener('unhandledrejection', function(e) {
  console.error('Unhandled rejection:', e.reason);
  var msg = e.reason && e.reason.message ? e.reason.message : String(e.reason);
  // 离线错误已由 apiFetch 单独提示，避免重复
  if (e.reason && e.reason.offline) return;
  showToast('操作失败：' + msg, 'error', 5000);
});

export { showFatalError };
