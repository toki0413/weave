import { test, expect } from '@playwright/test';

test.describe('认证流程 E2E 测试', () => {
  // 用时间戳生成动态手机号，避免与持久化 DB 已有账号冲突
  const testPhone = '138' + String(Date.now()).slice(-8);
  const testPassword = 'Test123!';
  const testName = '测试用户';

  test('注册 → 登录 → 查看个人资料', async ({ page }) => {
    // 1. 注册
    await page.goto('/');
    await page.waitForSelector('.header', { timeout: 10000 });

    // 直接走 API 注册并登录，避免依赖尚未实现的注册 UI
    const registerResponse = await page.evaluate(async ({ phone, password, name }) => {
      const res = await fetch('/api/v1/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone, password, role: 'elderly', name })
      });
      return res.json();
    }, { phone: testPhone, password: testPassword, name: testName });

    expect(registerResponse.access_token).toBeDefined();

    // 2. 登录
    const loginResponse = await page.evaluate(async ({ phone, password }) => {
      const res = await fetch('/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone, password })
      });
      return res.json();
    }, { phone: testPhone, password: testPassword });

    expect(loginResponse.access_token).toBeDefined();

    // 3. 设置 token 并查看个人资料
    await page.evaluate(async (token) => {
      localStorage.setItem('token', token);
    }, loginResponse.access_token);

    const meResponse = await page.evaluate(async () => {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/auth/me', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      return res.json();
    });

    expect(meResponse.phone).toBe(testPhone);
    expect(meResponse.name).toBe(testName);
  });
});
