import { describe, it, expect, vi, beforeEach } from 'vitest';

// 家属端记忆卡片 + 医生端漏斗 + 公开分享页渲染
vi.mock('../api/client.js', () => ({
  el: undefined,
  listSessions: vi.fn(async () => []),
  getHealthTrend: vi.fn(async () => ({})),
  getNotifications: vi.fn(async () => []),
  // 家属-老人绑定闭环（modes/family.js 新增依赖）：默认无绑定 → 渲染关联卡
  getFamilyMembers: vi.fn(async () => []),
  linkFamilyMember: vi.fn(async () => ({ link_id: 'l-1' })),
  invalidateCache: vi.fn(),
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

import { getSharedCard, trackEventPublic, trackEvent, generateMemoryCard, getFamilyMembers, linkFamilyMember, sendWebSocketCare, invalidateCache } from '../api/client.js';
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

describe('家属-老人绑定闭环（audit-5 / audit-24）', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    vi.clearAllMocks();
    window.alert = vi.fn();
    getFamilyMembers.mockResolvedValue([]);
  });

  it('无绑定时渲染关联卡，未关联不发关怀', async () => {
    var container = document.createElement('div');
    document.body.appendChild(container);
    renderFamilyMode(container, { healthScore: 72 });
    await flushPromises();

    expect(container.textContent).toContain('还没有关联老人');
    var bindBtn = Array.from(container.querySelectorAll('button'))
      .find((b) => b.textContent === '关联');
    expect(bindBtn).toBeTruthy();

    var care = Array.from(container.querySelectorAll('textarea'))
      .find((t) => (t.placeholder || '').indexOf('输入文字关怀') === 0);
    expect(care).toBeTruthy();
    care.value = '妈，今天冷，多穿点';
    var sendBtn = Array.from(container.querySelectorAll('button'))
      .find((b) => b.textContent === '发送文字');
    sendBtn.click();
    // 死锁修复前这里是 alert('请先绑定老人') 且永不发送
    expect(sendWebSocketCare).not.toHaveBeenCalled();
    expect(window.alert).toHaveBeenCalledWith('请先在上方关联老人');
  });

  it('填写手机号关联后清缓存重取列表并显示漏录提醒', async () => {
    getFamilyMembers.mockResolvedValueOnce([]);
    var container = document.createElement('div');
    document.body.appendChild(container);
    renderFamilyMode(container, { healthScore: 72 });
    await flushPromises();

    linkFamilyMember.mockResolvedValueOnce({ link_id: 'l-1', elderly_user_id: 'e-1' });
    getFamilyMembers.mockResolvedValueOnce([{
      link_id: 'l-1', elderly_user_id: 'e-1', elderly_name: '秀兰',
      last_session_at: '2026-10-20T04:00:00', missing_days: 3, relation: '子女',
    }]);

    var inputs = container.querySelectorAll('input');
    inputs[0].value = '13800000001';
    var bindBtn = Array.from(container.querySelectorAll('button'))
      .find((b) => b.textContent === '关联');
    bindBtn.click();
    await flushPromises();
    await flushPromises();

    expect(linkFamilyMember).toHaveBeenCalledWith('13800000001', null);
    expect(invalidateCache).toHaveBeenCalledWith('/notification/family-members');
    expect(container.textContent).toContain('秀兰已经 3 天没有新的回忆了');

    // 关怀解锁：elderlyId 真正接到发送调用
    var care = Array.from(container.querySelectorAll('textarea'))
      .find((t) => (t.placeholder || '').indexOf('输入文字关怀') === 0);
    care.value = '周末我回来';
    var sendBtn = Array.from(container.querySelectorAll('button'))
      .find((b) => b.textContent === '发送文字');
    sendBtn.click();
    expect(sendWebSocketCare).toHaveBeenCalledWith('e-1', '周末我回来', null);
  });
});
