import { test, expect } from '@playwright/test';

test.describe('衰退分析 E2E 测试', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.header', { timeout: 10000 });
    // 关闭首次访问的引导遮罩，否则会拦截后续点击
    const skipBtn = page.locator('.onboarding-btn-skip');
    if (await skipBtn.count() > 0) {
      await skipBtn.click();
    }
  });

  test('查看衰退分析页面', async ({ page }) => {
    // 衰退分析需要登录医生账号（API 要求认证）
    const ts = String(Date.now()).slice(-8);
    const doctorPhone = '137' + ts;
    const password = 'Test123!';

    const token = await page.evaluate(async ({ doctorPhone, password }) => {
      const reg = await fetch('/api/v1/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone: doctorPhone, password, role: 'doctor', name: '测试医生' })
      });
      const data = await reg.json();
      if (!data.access_token) throw new Error('医生注册失败: ' + JSON.stringify(data));
      localStorage.setItem('token', data.access_token);
      return data.access_token;
    }, { doctorPhone, password });

    // 1. 切换到医生端（衰退分析入口在医生端左面板）
    await page.click('text=医生端');
    await expect(page.locator('.view-btn.active')).toContainText('医生端');
    // 等医生端左面板加载
    await page.waitForSelector('.doc-metric-grid', { timeout: 10000 });

    // 2. 点击"查看记忆衰退分析"按钮
    await page.click('.decline-entry-btn');
    // 实际弹窗是 .decline-overlay / .decline-modal
    await page.waitForSelector('.decline-overlay', { timeout: 10000 });
    await expect(page.locator('.decline-overlay')).toBeVisible();
    await expect(page.locator('.decline-modal')).toBeVisible();

    // 3. 检查关键元素：风险分数卡片 + 维度标题
    // 等待内容渲染（API 异步加载），数据不足时会显示对应状态
    await page.waitForSelector('.decline-risk-card, .decline-error', { timeout: 15000 });

    // 登录后 API 能正常返回（即使数据不足也是 renderContent 路径），section-title 应出现
    await expect(page.locator('.decline-section-title').first()).toBeVisible({ timeout: 10000 });
  });
});
