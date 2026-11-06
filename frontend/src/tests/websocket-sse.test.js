import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// 实时通道降级路径：WebSocket 不可用时走 SSE，SSE 必须携带 access token
// （服务端 /events 强制鉴权，缺 token 直接 401，实时通道会静默失效）

describe('实时通道 SSE 鉴权', () => {
  var sseUrls = [];
  var OriginalWS;
  var OriginalES;

  beforeEach(() => {
    sseUrls = [];
    OriginalWS = global.WebSocket;
    OriginalES = global.EventSource;

    // 构造后立即触发 error，走首次降级分支
    global.WebSocket = class FakeWebSocket {
      constructor() {
        this.readyState = 0;
        setTimeout(() => { if (this.onerror) this.onerror(new Error('ws blocked')); }, 0);
      }
      close() {}
      send() {}
    };
    global.EventSource = class FakeEventSource {
      constructor(url) {
        sseUrls.push(String(url));
        this.readyState = 0;
      }
      close() {}
    };
  });

  afterEach(() => {
    global.WebSocket = OriginalWS;
    global.EventSource = OriginalES;
    vi.useRealTimers();
  });

  it('降级到 SSE 时 URL 携带 token 查询参数', async () => {
    const { connect } = await import('../services/websocket.js');
    connect('tok-abc-123', function() {});
    await new Promise((r) => setTimeout(r, 20));

    expect(sseUrls.length).toBeGreaterThan(0);
    expect(sseUrls[0]).toContain('/events');
    expect(sseUrls[0]).toContain('token=tok-abc-123');
  });

  it('token 做 URL 编码，避免特殊字符破坏查询串', async () => {
    const { connect } = await import('../services/websocket.js');
    connect('a+b/c=d', function() {});
    await new Promise((r) => setTimeout(r, 20));

    expect(sseUrls[0]).toContain('token=a%2Bb%2Fc%3Dd');
  });
});
