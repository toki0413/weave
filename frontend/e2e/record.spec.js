import { test, expect } from '@playwright/test';

test.describe('认知记录完整链路 E2E 测试', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.header', { timeout: 10000 });
    // 关闭首次访问的引导遮罩，否则会拦截后续点击
    const skipBtn = page.locator('.onboarding-btn-skip');
    if (await skipBtn.count() > 0) {
      await skipBtn.click();
    }
  });

  test('打开页面 → 输入叙事 → 识别并织网 → 确认编辑 → 提交 → 验证图谱 → 查看历史', async ({ page }) => {
    // 1. 打开页面（beforeEach 已完成）
    await expect(page).toHaveTitle(/Weave.*织忆/);

    // 2. 输入叙事文本
    const input = page.locator('#voice-input');
    await expect(input).toBeVisible();
    await input.fill('今天在公园碰见老张，我们一起打太极，然后去超市买了菜，回家做了饭');
    await expect(input).toHaveValue('今天在公园碰见老张，我们一起打太极，然后去超市买了菜，回家做了饭');

    // 3. 点击"识别并织网"
    const parseBtn = page.locator('#parse-btn');
    await expect(parseBtn).toBeVisible();
    await parseBtn.click();

    // 4. 等待解析结果并确认编辑（NLP 结果区域显示）
    await page.waitForSelector('#nlp-result.show', { timeout: 15000 });
    const nlpResult = page.locator('#nlp-result');
    await expect(nlpResult).toBeVisible();
    const resultText = await nlpResult.textContent();
    expect(resultText).toContain('实体');
    expect(resultText).toContain('关系');

    // 5. 提交到后端（模拟登录后调用 API）
    // 用时间戳生成动态手机号，避免与持久化 DB 已有账号冲突
    const testPhone = '138' + String(Date.now()).slice(-8);
    const testPassword = 'Test123!';
    await page.evaluate(async ({ phone, password }) => {
      // 注册
      const regRes = await fetch('/api/v1/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone, password, role: 'elderly', name: '测试老人' })
      });
      const regData = await regRes.json();
      if (!regData.access_token) throw new Error('注册失败: ' + JSON.stringify(regData));
      // 登录
      const loginRes = await fetch('/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone, password })
      });
      const loginData = await loginRes.json();
      if (!loginData.access_token) throw new Error('登录失败: ' + JSON.stringify(loginData));
      localStorage.setItem('token', loginData.access_token);
      // 创建会话
      const sessionRes = await fetch('/api/v1/session/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + loginData.access_token
        },
        body: JSON.stringify({
          day_number: 1,
          narrative_input: { text: '今天在公园碰见老张，我们一起打太极，然后去超市买了菜，回家做了饭', dialect: 'mandarin' }
        })
      });
      if (!sessionRes.ok) throw new Error('会话创建失败: ' + await sessionRes.text());
    }, { phone: testPhone, password: testPassword });

    // 6. 验证图谱显示（SVG 画布中有节点和边）
    const svg = page.locator('#canvas-svg');
    await expect(svg).toBeVisible();
    // 等待动画稳定后检查节点
    await page.waitForTimeout(800);
    const circles = await svg.locator('circle').count();
    expect(circles).toBeGreaterThan(0);

    // 7. 查看历史记录（通过 API 验证后端已保存）
    const historyData = await page.evaluate(async () => {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/session/?limit=10', {
        headers: { 'Authorization': 'Bearer ' + token }
      });
      return res.json();
    });
    expect(Array.isArray(historyData)).toBe(true);
    expect(historyData.length).toBeGreaterThan(0);
    expect(historyData[0].narrative).toContain('公园');
  });
});
