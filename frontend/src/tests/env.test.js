import { describe, it, expect, beforeEach } from 'vitest';
import { isWeChatBrowser, copyToClipboard } from '../env.js';

function setUA(ua) {
  Object.defineProperty(navigator, 'userAgent', {
    value: ua, configurable: true,
  });
}

describe('运行环境检测（U2 微信内浏览器分流）', () => {
  beforeEach(() => {
    setUA('Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0');
  });

  it('MicroMessenger UA 判定为微信内', () => {
    setUA('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) AppleWebKit/605.1.15 MicroMessenger/8.0.49');
    expect(isWeChatBrowser()).toBe(true);
  });

  it('普通浏览器 UA 判定为非微信', () => {
    expect(isWeChatBrowser()).toBe(false);
  });

  it('copyToClipboard 走 clipboard API 成功路径', async () => {
    const written = [];
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: (t) => { written.push(t); return Promise.resolve(); } },
      configurable: true,
    });
    const ok = await copyToClipboard('https://weave.example/#/share/card/x');
    expect(ok).toBe(true);
    expect(written).toEqual(['https://weave.example/#/share/card/x']);
  });

  it('clipboard API 不可用时回退 execCommand 路径', async () => {
    Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true });
    // jsdom 无 execCommand：fallback 捕获异常返回 false，不抛错
    const ok = await copyToClipboard('text');
    expect(ok).toBe(false);
  });
});
