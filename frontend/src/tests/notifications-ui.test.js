import { describe, it, expect, vi, beforeEach } from 'vitest';

// mock 依赖：API 客户端与 toast，只测通知面板 UI 逻辑
vi.mock('../api/client.js', () => ({
  getNotifications: vi.fn(async () => []),
  markNotificationRead: vi.fn(async () => ({})),
  markAllNotificationsRead: vi.fn(async () => ({})),
  getUnreadCount: vi.fn(async () => ({ unread_count: 0 })),
  resolveNotification: vi.fn(async () => ({ detail: 'ok', signal_suppressed: true })),
  invalidateCache: vi.fn(),
}));
vi.mock('../ui/toast.js', () => ({
  showToast: vi.fn(),
  showOfflineToast: vi.fn(),
  clearOfflineToast: vi.fn(),
}));

import { getNotifications, resolveNotification, invalidateCache } from '../api/client.js';
import { showToast } from '../ui/toast.js';
import { createNotificationBell, destroyNotificationBell } from '../ui/notifications.js';

function flushPromises() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

function openPanel() {
  const bell = createNotificationBell();
  document.body.appendChild(bell);
  bell.querySelector('button').click(); // 展开 dropdown
  return bell;
}

describe('告警闭环回填 UI', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    vi.clearAllMocks();
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  it('pending 告警显示四个反馈按钮，点击误报后变为已反馈标签', async () => {
    getNotifications.mockResolvedValueOnce([{
      id: 'notif-1', user_id: 'u1', type: 'anomaly', title: '深夜活动提醒',
      content: '建议：联系老人确认', severity: 'warning', is_read: true,
      resolution_status: 'pending', created_at: new Date().toISOString(),
    }]);

    const bell = openPanel();
    await flushPromises();

    const buttons = document.querySelectorAll('.notif-resolve-btn');
    expect(buttons).toHaveLength(4);
    const labels = Array.from(buttons).map((b) => b.textContent);
    expect(labels).toEqual(['已处理', '有帮助', '没帮助', '误报']);

    buttons[3].click(); // 误报
    await flushPromises();

    expect(resolveNotification).toHaveBeenCalledWith('notif-1', 'false_alarm');
    const label = document.querySelector('.notif-resolved-label');
    expect(label).toBeTruthy();
    expect(label.textContent).toContain('误报');
    expect(invalidateCache).toHaveBeenCalledWith('/notification/');
    expect(showToast).toHaveBeenCalledWith('已记录，同类告警将暂缓推送 30 天');

    destroyNotificationBell();
    bell.remove();
  });

  it('已回填的通知直接显示状态标签，不再出现按钮', async () => {
    getNotifications.mockResolvedValueOnce([{
      id: 'notif-2', user_id: 'u1', type: 'decline', title: '衰退提醒',
      content: '', severity: 'info', is_read: true,
      resolution_status: 'helpful', created_at: new Date().toISOString(),
    }]);

    openPanel();
    await flushPromises();

    expect(document.querySelectorAll('.notif-resolve-btn')).toHaveLength(0);
    expect(document.querySelector('.notif-resolved-label').textContent).toContain('有帮助');
    destroyNotificationBell();
  });

  it('量表提醒不显示回填行', async () => {
    getNotifications.mockResolvedValueOnce([{
      id: 'notif-3', user_id: 'u1', type: 'scale_reminder', title: 'MMSE 到期',
      content: '', severity: 'info', is_read: true,
      resolution_status: 'pending', created_at: new Date().toISOString(),
    }]);

    openPanel();
    await flushPromises();

    expect(document.querySelector('.notif-resolve-row')).toBeNull();
    destroyNotificationBell();
  });

  it('回填失败时恢复按钮并可重试', async () => {
    getNotifications.mockResolvedValueOnce([{
      id: 'notif-4', user_id: 'u1', type: 'anomaly', title: '告警',
      content: '', severity: 'info', is_read: true,
      resolution_status: 'pending', created_at: new Date().toISOString(),
    }]);
    resolveNotification.mockRejectedValueOnce(new Error('network'));

    openPanel();
    await flushPromises();

    const btn = document.querySelector('.notif-resolve-btn');
    btn.click();
    await flushPromises();

    expect(btn.disabled).toBe(false);
    expect(showToast).toHaveBeenCalledWith(expect.stringContaining('回填失败'));
    destroyNotificationBell();
  });
});
