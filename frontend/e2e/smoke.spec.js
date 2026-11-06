import { test, expect } from '@playwright/test';

test.describe('织忆 E2E 测试', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    // 等待页面初始化完成
    await page.waitForSelector('.header', { timeout: 10000 });
    // 关闭首次访问的引导遮罩，否则会拦截后续点击
    const skipBtn = page.locator('.onboarding-btn-skip');
    if (await skipBtn.count() > 0) {
      await skipBtn.click();
    }
  });

  test('页面标题正确', async ({ page }) => {
    await expect(page).toHaveTitle(/织忆/);
  });

  test('Header 渲染正常', async ({ page }) => {
    const header = page.locator('.header');
    await expect(header).toBeVisible();
    // 顶栏只显示产品名「织忆」，不再有副标题
    await expect(page.locator('.header-title')).toContainText('织忆');
  });

  test('三视图切换正常', async ({ page }) => {
    // 默认老人端
    await expect(page.locator('.view-btn.active')).toContainText('老人端');
    
    // 切换到家属端
    await page.click('text=家属端');
    await expect(page.locator('.view-btn.active')).toContainText('家属端');
    await expect(page.locator('.fam-hero')).toBeVisible();
    
    // 切换到医生端
    await page.click('text=医生端');
    await expect(page.locator('.view-btn.active')).toContainText('医生端');
    await expect(page.locator('.doc-metric-grid')).toBeVisible();
    
    // 切换回老人端
    await page.click('text=老人端');
    await expect(page.locator('.view-btn.active')).toContainText('老人端');
  });

  test('语音输入区域存在', async ({ page }) => {
    await expect(page.locator('#voice-input')).toBeVisible();
    await expect(page.locator('#parse-btn')).toBeVisible();
  });

  test('画布区域存在', async ({ page }) => {
    await expect(page.locator('#canvas-wrap')).toBeVisible();
    await expect(page.locator('#canvas-svg')).toBeVisible();
  });

  test('时序网络存在', async ({ page }) => {
    await expect(page.locator('.timeline')).toBeVisible();
  });

  test('右侧面板存在', async ({ page }) => {
    await expect(page.locator('.panel-right')).toBeVisible();
  });

  test('健康度显示正常', async ({ page }) => {
    // 实际类名是 .health-card，包含 .health-num 分数和 .health-label 标签
    await expect(page.locator('.health-card')).toBeVisible();
    await expect(page.locator('.health-label')).toContainText('记忆网健康度');
  });

  test('数据导出按钮存在', async ({ page }) => {
    await expect(page.locator('text=JSON')).toBeVisible();
    await expect(page.locator('text=CSV')).toBeVisible();
  });
});
