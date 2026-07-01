import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:8004',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    // 关闭限流避免 E2E 频繁注册触发 429；日志重定向到项目内可写目录
    command: 'cd ../backend && set "CG_DISABLE_RATE_LIMIT=1" && set "CG_LOG_DIR=..\\logs" && python run.py',
    url: 'http://localhost:8004/health',
    reuseExistingServer: !process.env.CI,
    timeout: 30000,
  },
});
