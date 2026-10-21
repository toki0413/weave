import { describe, it, expect, vi, beforeEach } from 'vitest';

// mock 掉带副作用的依赖（IndexedDB / DOM Toast），只测 client.js 本体
vi.mock('../ui/toast.js', () => ({
  showOfflineToast: () => {},
  clearOfflineToast: () => {},
}));
vi.mock('../db/offline.js', () => ({
  enqueueOffline: async () => {},
  syncOfflineQueue: async () => ({ synced: 0, failed: 0 }),
  getCachedSessions: async () => [],
  cacheSessions: async () => {},
  getCachedScales: async () => [],
  cacheScales: async () => {},
}));

import { trackEvent, flushTrackEvents, markSessionSource, createSession, register, getSharedCard } from '../api/client.js';

const QUEUE_KEY = 'cg_track_queue';

function mockFetchOk(capture) {
  const fn = vi.fn(async (url, options) => {
    if (capture) capture.push({ url, options });
    return {
      ok: true,
      status: 200,
      json: async () => ({ accepted: 1, id: 's1' }),
    };
  });
  vi.stubGlobal('fetch', fn);
  return fn;
}

describe('零方数据埋点 trackEvent', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.unstubAllGlobals();
  });

  it('事件先入 localStorage 队列', () => {
    trackEvent('daily_prompt_exposed', { topic: 'food' });
    const queue = JSON.parse(localStorage.getItem(QUEUE_KEY));
    expect(queue).toHaveLength(1);
    expect(queue[0].name).toBe('daily_prompt_exposed');
    expect(queue[0].client_ts).toBeTruthy();
  });

  it('flush 批量上报后清空队列', async () => {
    const calls = [];
    mockFetchOk(calls);
    trackEvent('daily_prompt_exposed', {});
    trackEvent('daily_prompt_filled', {});
    await flushTrackEvents();
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toContain('/api/v1/metrics/events');
    const body = JSON.parse(calls[0].options.body);
    expect(body.events.map((e) => e.name)).toEqual(['daily_prompt_exposed', 'daily_prompt_filled']);
    expect(localStorage.getItem(QUEUE_KEY)).toBe('[]');
  });

  it('上报失败时回滚队列，事件不丢', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('network down'); }));
    trackEvent('alerts_viewed', { unread: false });
    await flushTrackEvents();
    const queue = JSON.parse(localStorage.getItem(QUEUE_KEY));
    expect(queue).toHaveLength(1);
    expect(queue[0].name).toBe('alerts_viewed');
  });

  it('离线时不上报，留在本地队列', async () => {
    const calls = [];
    mockFetchOk(calls);
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false);
    trackEvent('daily_prompt_exposed', {});
    await flushTrackEvents();
    expect(calls).toHaveLength(0);
    expect(JSON.parse(localStorage.getItem(QUEUE_KEY))).toHaveLength(1);
    vi.restoreAllMocks();
  });
});

describe('会话来源归因 markSessionSource', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.unstubAllGlobals();
  });

  it('标记后 createSession 携带 source 并附带 submitted 事件，用后即清', async () => {
    const calls = [];
    mockFetchOk(calls);
    markSessionSource('daily_prompt');
    await createSession(1, '今天在公园散步');
    const sessionCall = calls.find((c) => c.url.endsWith('/api/v1/session/'));
    const body = JSON.parse(sessionCall.options.body);
    expect(body.source).toBe('daily_prompt');

    await flushTrackEvents();
    const metricsCall = calls.find((c) => c.url.includes('/metrics/events'));
    const events = JSON.parse(metricsCall.options.body).events;
    expect(events.some((e) => e.name === 'daily_prompt_submitted')).toBe(true);

    // 第二次 createSession 不再携带 source（一次性归因）
    await createSession(2, '今天喝了粥');
    const second = calls.filter((c) => c.url.endsWith('/api/v1/session/'))[1];
    expect(JSON.parse(second.options.body).source).toBeUndefined();
  });

  it('未标记来源时 createSession 不带 source 字段', async () => {
    const calls = [];
    mockFetchOk(calls);
    await createSession(1, '今天看电视');
    const sessionCall = calls.find((c) => c.url.endsWith('/api/v1/session/'));
    expect(JSON.parse(sessionCall.options.body).source).toBeUndefined();
  });
});

describe('分享归因（K 因子）', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.unstubAllGlobals();
  });

  it('注册成功后回传 register_from_share 并清除归因标记', async () => {
    const calls = [];
    mockFetchOk(calls);
    localStorage.setItem('cg_share_ref', 'card-abc');
    await register('13900001234', 'Test123456!');
    const attribution = calls.find((c) => c.url.includes('/metrics/events/public'));
    expect(attribution).toBeTruthy();
    const body = JSON.parse(attribution.options.body);
    expect(body.events[0].name).toBe('register_from_share');
    expect(body.events[0].properties.card_id).toBe('card-abc');
    expect(localStorage.getItem('cg_share_ref')).toBeNull();
  });

  it('无归因标记时注册不发公开事件', async () => {
    const calls = [];
    mockFetchOk(calls);
    await register('13900001235', 'Test123456!');
    expect(calls.find((c) => c.url.includes('/metrics/events/public'))).toBeUndefined();
  });

  it('getSharedCard 免登录直连公开端点', async () => {
    const calls = [];
    mockFetchOk(calls);
    const data = await getSharedCard('card-xyz');
    const call = calls.find((c) => c.url.includes('/card/public/card-xyz'));
    expect(call).toBeTruthy();
    // 裸 fetch 不带任何头（无 Authorization）
    expect((call.options && call.options.headers && call.options.headers.Authorization)).toBeUndefined();
    expect(data).toBeTruthy();
  });
});
