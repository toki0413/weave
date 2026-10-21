import { describe, it, expect, vi, beforeEach } from 'vitest';

// 家属端记忆卡片 + 医生端漏斗 + 公开分享页渲染
vi.mock('../api/client.js', () => ({
  el: undefined,
  listSessions: vi.fn(async () => []),
  getHealthTrend: vi.fn(async () => ({})),
  getNotifications: vi.fn(async () => []),
  getLatestGraph: vi.fn(async () => null),
  sendWebSocketCare: vi.fn(() => ({})),
  generateMemoryCard: vi.fn(async () => ({
    id: 'card-1',
    payload: {
      elderly_name: '张大爷', week_label: '近7天', record_count: 5,
      active_days: 4, total_chars: 800, trend_level: '状态稳定',
      top_entities: [{ label: '老朋友', type: 'person' }, { label: '公园', type: 'place' }],
    },
  })),
  getLatestMemoryCard: vi.fn(async () => ({ card: null })),
  getSharedCard: vi.fn(async () => ({
    payload: {
      elderly_name: '张大爷', week_label: '近7天', record_count: 5,
      active_days: 4, total_chars: 800, trend_level: '状态稳定',
      top_entities: [{ label: '公园', type: 'place' }],
    },
  })),
  trackEvent: vi.fn(),
  trackEventPublic: vi.fn(),
  getResearchSummary: vi.fn(async () => ({
    days: 30, active_users: 3,
    daily_prompt: { exposed: 12, filled: 6, submitted: 3, fill_rate: 0.5, submit_rate: 0.5 },
    alerts: { created: 4, resolved: 2, false_alarm: 1, false_alarm_rate: 0.25 },
  })),
  getScaleHistory: vi.fn(async () => []),
  getDeclineAnalysis: vi.fn(async () => null),
  sendWebSocketAdvice: vi.fn(() => ({})),
  getToken: vi.fn(() => null),
}));
vi.mock('../services/websocket.js', () => ({
  connect: vi.fn(),
  send: vi.fn(),
  isConnected: vi.fn(() => false),
  isUsingSSE: vi.fn(() => false),
}));

import { getSharedCard, trackEventPublic, trackEvent, generateMemoryCard } from '../api/client.js';
import { isShareRoute, shareCardId, renderSharePage } from '../ui/share-page.js';
import { renderFamilyMode } from '../modes/family.js';
import { renderDoctorMode } from '../modes/doctor.js';

function flushPromises() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

describe('家属端记忆卡片区块', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    vi.clearAllMocks();
  });

  it('无历史卡片时显示生成按钮，生成后渲染聚合数据与分享按钮', async () => {
    var container = document.createElement('div');
    document.body.appendChild(container);
    renderFamilyMode(container, { healthScore: 85 });
    await flushPromises();

    var section = container.querySelector('.memory-card-section');
    expect(section).toBeTruthy();
    var genBtn = Array.from(section.querySelectorAll('button'))
      .find((b) => b.textContent === '生成本周卡片');
    expect(genBtn).toBeTruthy();

    genBtn.click();
    await flushPromises();

    expect(generateMemoryCard).toHaveBeenCalledWith(7);
    expect(section.textContent).toContain('记录 5 次');
    expect(section.textContent).toContain('状态稳定');
    expect(section.textContent).toContain('常提起：老朋友、公园');
    var shareBtn = Array.from(section.querySelectorAll('button'))
      .find((b) => b.textContent === '复制分享链接');
    expect(shareBtn).toBeTruthy();

    // 复制 → 分享埋点（jsdom 无 clipboard，打桩）
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn(async () => {}) }, configurable: true,
    });
    shareBtn.click();
    await flushPromises();
    expect(trackEvent).toHaveBeenCalledWith('memory_card_shared', { card_id: 'card-1' });
  });
});

describe('医生端研究漏斗面板', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    vi.clearAllMocks();
  });

  it('渲染漏斗指标芯片', async () => {
    var container = document.createElement('div');
    document.body.appendChild(container);
    renderDoctorMode(container);
    await flushPromises();

    var funnel = container.querySelector('#doctor-funnel');
    expect(funnel).toBeTruthy();
    expect(funnel.textContent).toContain('日课曝光');
    expect(funnel.textContent).toContain('12');
    expect(funnel.textContent).toContain('提交');
    expect(funnel.textContent).toContain('误报率');
    expect(funnel.textContent).toContain('25%');
  });
});

describe('公开分享页', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    vi.clearAllMocks();
    location.hash = '#/share/card/card-xyz';
  });

  it('路由匹配与卡片 id 提取', () => {
    expect(isShareRoute()).toBe(true);
    expect(shareCardId()).toBe('card-xyz');
    location.hash = '#/other';
    expect(isShareRoute()).toBe(false);
  });

  it('免登录渲染卡片并发 landing_viewed 匿名埋点', async () => {
    var container = document.createElement('div');
    document.body.appendChild(container);
    renderSharePage(container);
    await flushPromises();

    expect(getSharedCard).toHaveBeenCalledWith('card-xyz');
    var call = getSharedCard.mock.calls[0];
    expect(call).toEqual(['card-xyz']);

    expect(trackEventPublic).toHaveBeenCalledWith('landing_viewed', { card_id: 'card-xyz' });

    // CTA 写入归因标记
    var cta = Array.from(container.querySelectorAll('button'))
      .find((b) => b.textContent.includes('记忆花园'));
    expect(cta).toBeTruthy();
    cta.click();
    expect(localStorage.getItem('cg_share_ref')).toBe('card-xyz');
    localStorage.clear();
  });
});
