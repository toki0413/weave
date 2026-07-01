import { test, expect } from '@playwright/test';

test.describe('认知量表 E2E 测试', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.header', { timeout: 10000 });
    // 关闭首次访问的引导遮罩，否则会拦截后续点击
    const skipBtn = page.locator('.onboarding-btn-skip');
    if ((await skipBtn.count()) > 0) {
      await skipBtn.click();
    }
  });

  test('打开量表 → 提交 → 查看历史', async ({ page }) => {
    // 先注册登录一个用户，量表入口需要 token 才能拉到量表列表
    const phone = '138' + String(Date.now()).slice(-8);
    const password = 'Test123!';
    await page.evaluate(async ({ phone, password }) => {
      const reg = await fetch('/api/v1/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone, password, role: 'elderly', name: '量表测试用户' })
      });
      const data = await reg.json();
      localStorage.setItem('token', data.access_token);
    }, { phone, password });

    // 切换到医生端（量表入口在医生端左面板）
    await page.click('text=医生端');
    await expect(page.locator('.view-btn.active')).toContainText('医生端');
    await page.waitForSelector('.doc-metric-grid', { timeout: 10000 });

    // 点击"开始认知量表评估"按钮
    await page.click('.scale-entry-btn');
    await page.waitForSelector('.scale-overlay', { timeout: 10000 });
    await expect(page.locator('.scale-overlay')).toBeVisible();

    // 等待量表列表加载，点击第一个量表卡片开始
    await page.waitForSelector('.scale-card', { timeout: 15000 });
    await page.click('.scale-card >> nth=0');

    // 逐题答题：每题点击第一个选项，自动进入下一题
    await page.waitForSelector('.scale-question-text', { timeout: 15000 });
    for (let i = 0; i < 30; i++) {
      await page.waitForSelector('.scale-option', { state: 'visible', timeout: 10000 });
      await page.locator('.scale-option').first().click();
      // 点击后可能进入下一题或提交后跳转结果页，短暂等待渲染
      await page.waitForTimeout(400);
      if ((await page.locator('.scale-result-score').count()) > 0) break;
    }

    // 验证结果页出现
    await expect(page.locator('.scale-result-score')).toBeVisible();
    await expect(page.locator('.scale-result-level')).toBeVisible();

    // 查看历史（通过 API 验证后端已保存）
    const history = await page.evaluate(async () => {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/scale/history/all?limit=10', {
        headers: { 'Authorization': 'Bearer ' + token }
      });
      return res.json();
    });
    expect(Array.isArray(history)).toBe(true);
    expect(history.length).toBeGreaterThan(0);
    expect(history[0].scale_type).toBeTruthy();
  });
});
