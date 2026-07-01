// ============ 家属端通知 UI ============
// 通知铃铛 + 下拉面板，挂在 header 上
import { el } from './components.js';
import {
  getNotifications,
  markNotificationRead,
  markAllNotificationsRead,
  getUnreadCount,
} from '../api/client.js';

// 通知类型对应的图标
var TYPE_ICON = {
  anomaly: '⚠️',
  decline: '📉',
  scale_reminder: '📋',
};

// severity 对应的颜色类名
var SEVERITY_CLASS = {
  info: 'notif-info',
  warning: 'notif-warning',
  danger: 'notif-danger',
};

// 面板状态，避免全局污染
var panel = {
  bell: null,
  dropdown: null,
  unreadCount: 0,
  isOpen: false,
  pollTimer: null,
};

// 把时间戳转成"几分钟前"这种相对时间
function formatTime(iso) {
  var d = new Date(iso);
  var now = new Date();
  var diff = Math.floor((now - d) / 1000);
  if (diff < 60) return '刚刚';
  if (diff < 3600) return Math.floor(diff / 60) + ' 分钟前';
  if (diff < 86400) return Math.floor(diff / 3600) + ' 小时前';
  if (diff < 604800) return Math.floor(diff / 86400) + ' 天前';
  return d.toLocaleDateString('zh-CN');
}

// 创建铃铛按钮（含未读红点），挂到 header 上
export function createNotificationBell() {
  var wrap = el('div', { className: 'notif-bell-wrap' });

  var btn = el('button', {
    className: 'notif-bell-btn',
    'aria-label': '通知',
    onclick: function(e) {
      e.stopPropagation();
      toggleDropdown();
    },
  }, '🔔');

  var badge = el('span', { className: 'notif-badge', style: { display: 'none' } }, '0');

  wrap.appendChild(btn);
  wrap.appendChild(badge);
  panel.bell = wrap;

  // 点页面其他地方收起面板
  document.addEventListener('click', function(e) {
    if (panel.isOpen && !panel.bell.contains(e.target) && panel.dropdown && !panel.dropdown.contains(e.target)) {
      closeDropdown();
    }
  });

  // 首次拉一下未读数，然后定时轮询
  refreshUnreadCount();
  startPolling();

  return wrap;
}

// 轮询未读数，每 60 秒一次
function startPolling() {
  stopPolling();
  panel.pollTimer = setInterval(refreshUnreadCount, 60000);
}

function stopPolling() {
  if (panel.pollTimer) {
    clearInterval(panel.pollTimer);
    panel.pollTimer = null;
  }
}

// 刷新未读数量
function refreshUnreadCount() {
  getUnreadCount().then(function(res) {
    panel.unreadCount = res.unread_count || 0;
    updateBadge();
  }).catch(function() {
    // 静默失败，不打扰用户
  });
}

function updateBadge() {
  var badge = panel.bell.querySelector('.notif-badge');
  if (!badge) return;
  if (panel.unreadCount > 0) {
    badge.textContent = panel.unreadCount > 99 ? '99+' : String(panel.unreadCount);
    badge.style.display = '';
  } else {
    badge.style.display = 'none';
  }
}

// 展开/收起下拉面板
function toggleDropdown() {
  if (panel.isOpen) {
    closeDropdown();
  } else {
    openDropdown();
  }
}

function openDropdown() {
  if (panel.dropdown) closeDropdown();

  var dropdown = el('div', { className: 'notif-dropdown' });
  panel.dropdown = dropdown;
  panel.isOpen = true;

  // 头部：标题 + 全部已读按钮
  var header = el('div', { className: 'notif-dropdown-header' }, [
    el('span', { className: 'notif-dropdown-title' }, '通知'),
    el('button', {
      className: 'notif-mark-all-btn',
      onclick: function(e) {
        e.stopPropagation();
        markAllNotificationsRead().then(function() {
          panel.unreadCount = 0;
          updateBadge();
          loadList(dropdown);
        }).catch(function() {});
      },
    }, '全部已读'),
  ]);
  dropdown.appendChild(header);

  // 列表容器，先放个 loading
  var list = el('div', { className: 'notif-list' });
  list.appendChild(el('div', { className: 'notif-loading' }, '加载中…'));
  dropdown.appendChild(list);

  document.body.appendChild(dropdown);
  positionDropdown(dropdown);
  loadList(dropdown);

  // 滚动时跟着铃铛走
  window.addEventListener('scroll', positionDropdownHandler, true);
  window.addEventListener('resize', positionDropdownHandler);
}

function positionDropdownHandler() {
  if (panel.dropdown) positionDropdown(panel.dropdown);
}

function positionDropdown(dropdown) {
  if (!panel.bell || !dropdown) return;
  var rect = panel.bell.getBoundingClientRect();
  var dropdownWidth = 360;
  // 确保不超出右边屏幕
  var left = rect.right - dropdownWidth;
  if (left < 8) left = 8;
  dropdown.style.position = 'fixed';
  dropdown.style.top = (rect.bottom + 6) + 'px';
  dropdown.style.left = left + 'px';
}

function closeDropdown() {
  if (panel.dropdown) {
    panel.dropdown.parentNode.removeChild(panel.dropdown);
    panel.dropdown = null;
  }
  panel.isOpen = false;
  window.removeEventListener('scroll', positionDropdownHandler, true);
  window.removeEventListener('resize', positionDropdownHandler);
}

// 加载通知列表
function loadList(dropdown) {
  var list = dropdown.querySelector('.notif-list');
  if (!list) return;
  list.innerHTML = '';
  list.appendChild(el('div', { className: 'notif-loading' }, '加载中…'));

  getNotifications(false).then(function(items) {
    list.innerHTML = '';
    if (!items || items.length === 0) {
      list.appendChild(el('div', { className: 'notif-empty' }, '暂无通知'));
      return;
    }
    items.forEach(function(n) {
      list.appendChild(buildItem(n, dropdown));
    });
  }).catch(function(err) {
    list.innerHTML = '';
    list.appendChild(el('div', { className: 'notif-empty' },
      '加载失败：' + (err.offline ? '无法连接服务器' : err.message)));
  });
}

// 构建单条通知
function buildItem(n, dropdown) {
  var sevClass = SEVERITY_CLASS[n.severity] || SEVERITY_CLASS.info;
  var icon = TYPE_ICON[n.type] || '🔔';

  var item = el('div', {
    className: 'notif-item' + (n.is_read ? '' : ' unread') + ' ' + sevClass,
    onclick: function() {
      if (!n.is_read) {
        markNotificationRead(n.id).then(function() {
          n.is_read = true;
          item.classList.remove('unread');
          panel.unreadCount = Math.max(0, panel.unreadCount - 1);
          updateBadge();
        }).catch(function() {});
      }
    },
  });

  // 左侧图标
  item.appendChild(el('div', { className: 'notif-item-icon' }, icon));

  // 右侧内容
  var body = el('div', { className: 'notif-item-body' });
  body.appendChild(el('div', { className: 'notif-item-title' }, n.title));
  if (n.content) {
    // content 里可能有换行，用 white-space: pre-line 处理
    body.appendChild(el('div', { className: 'notif-item-content' }, n.content));
  }
  body.appendChild(el('div', { className: 'notif-item-time' }, formatTime(n.created_at)));
  item.appendChild(body);

  return item;
}

// 导出给外部主动刷新用（比如切到家属端时）
export function refreshNotifications() {
  refreshUnreadCount();
}

// 清理轮询定时器（页面卸载时调）
export function destroyNotificationBell() {
  stopPolling();
  closeDropdown();
}
