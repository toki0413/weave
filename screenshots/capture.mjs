// 截图脚本：注册测试账号，录入示例数据，截取各视图界面
import { createRequire } from 'module';
import { fileURLToPath } from 'url';
import path from 'path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(path.resolve(__dirname, '../frontend/package.json'));
const { chromium } = require('playwright');
const BASE = 'http://127.0.0.1:8004';
const API = BASE + '/api/v1';

const USERNAME = 'wangxiulan';
const PASSWORD = 'Test@1234';
const NAME = '王秀兰';

async function apiFetch(p, options = {}, token) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const resp = await fetch(API + p, { ...options, headers, body: options.body ? JSON.stringify(options.body) : undefined });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: 'HTTP ' + resp.status }));
    throw new Error(err.detail || 'HTTP ' + resp.status);
  }
  return resp.json();
}

async function prepareData() {
  const reg = await apiFetch('/auth/register', {
    method: 'POST',
    body: { username: USERNAME, password: PASSWORD, role: 'elderly', name: NAME },
  });
  const token = reg.access_token;
  console.log('注册成功');
  const narratives = [
    '今天早上在小区花园散步，见到了老邻居张阿姨，我们一起聊了聊她养的花，她种的月季开得真好。',
    '中午女儿打电话来了，说下周要带外孙回来看我，我很开心，外孙今年上小学三年级了。',
    '下午去社区活动中心参加了书法班，我写了一幅静字，老师说比上次有进步。',
    '想起上周去医院复查，医生说我的血压控制得不错，让我继续保持。',
    '今天傍晚下了点小雨，我坐在阳台上听雨声，觉得很平静。',
  ];
  let ok = 0;
  for (let i = 0; i < narratives.length; i++) {
    try {
      await apiFetch('/session/', {
        method: 'POST',
        body: { day_number: i + 1, narrative_input: { text: narratives[i], dialect: 'mandarin' } },
      }, token);
      ok++;
    } catch (e) { console.log('叙事#' + (i + 1) + '跳过:', e.message); }
  }
  console.log('录入', ok, '/', narratives.length, '条叙事');
  try {
    await apiFetch('/training/', { method: 'POST', body: { game_type: 'memory_challenge', score: 85 } }, token);
  } catch (e) {}
  return token;
}

async function main() {
  let token;
  try {
    token = await prepareData();
  } catch (e) {
    console.log('登录已有账号:', e.message);
    const login = await apiFetch('/auth/login', { method: 'POST', body: { identifier: USERNAME, password: PASSWORD } });
    token = login.access_token;
  }

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  const errors = [];
  page.on('pageerror', (e) => errors.push('PAGE: ' + e.message));
  page.on('console', (msg) => { if (msg.type() === 'error') errors.push('CONSOLE: ' + msg.text()); });
  page.on('response', (r) => {
    if (r.status() === 401) errors.push('401: ' + r.url());
    if (r.status() === 404) errors.push('404: ' + r.url());
  });

  // 1. 未登录首页
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(3000);
  await page.screenshot({ path: path.join(__dirname, '01-landing.png') });
  console.log('截图 1: 未登录首页');

  // 2. 注册弹窗
  await page.evaluate(() => {
    const btn = document.querySelector('[data-action="auth"], .auth-trigger, .btn-login, #login-btn');
    if (btn) btn.click();
    else if (window.showAuthModal) window.showAuthModal();
  });
  await page.waitForTimeout(1000);
  await page.evaluate(() => {
    for (const t of document.querySelectorAll('button')) {
      if (t.textContent.trim() === '注册') { t.click(); break; }
    }
  });
  await page.waitForTimeout(500);
  await page.fill('#auth-identifier', 'testuser').catch(() => {});
  await page.fill('#auth-phone', '13800000002').catch(() => {});
  await page.fill('#auth-name', '测试用户').catch(() => {});
  await page.fill('#auth-password', 'Test@1234').catch(() => {});
  await page.screenshot({ path: path.join(__dirname, '02-register.png') });
  console.log('截图 2: 注册弹窗');

  // 3. 已登录主界面 — addInitScript 在 JS 执行前注入 token
  // 拦截 /auth/me：返回中性角色，避免简化版模式覆盖完整认知花园图谱界面
  await page.route('**/api/v1/auth/me', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: 'demo', username: USERNAME, role: '', name: NAME }),
    });
  });
  await page.addInitScript((t) => { localStorage.setItem('token', t); }, token);
  errors.length = 0;
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => {
    const sk = document.getElementById('skeleton');
    return !sk || sk.style.opacity === '0' || !sk.parentNode;
  }, { timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(3000);
  const debug = await page.evaluate(() => {
    const app = document.getElementById('app');
    return {
      bodyLen: document.body.innerHTML.length,
      appLen: app ? app.innerHTML.length : -1,
      initCalled: !!window.__init_called__,
      initErr: window.__init_error__ || null,
      skeletonGone: !document.getElementById('skeleton'),
      hasCanvas: !!document.querySelector('canvas'),
      hasGraph: !!document.getElementById('graph-canvas'),
      hasLeft: !!document.querySelector('.left-panel, #left-panel'),
      appChildren: app ? app.children.length : -1,
      bodySnippet: document.body.innerHTML.slice(0, 300),
    };
  });
  console.log('DEBUG:', JSON.stringify(debug));
  console.log('ERRORS:', errors.length > 0 ? errors.slice(0, 8).join(' | ') : 'OK');
  await page.screenshot({ path: path.join(__dirname, '03-main.png') });
  console.log('截图 3: 主界面');

  // 4. 家属端
  await page.evaluate(() => { const b = document.querySelectorAll('.view-btn'); if (b.length >= 2) b[1].click(); });
  await page.waitForTimeout(3000);
  await page.screenshot({ path: path.join(__dirname, '04-family.png') });
  console.log('截图 4: 家属端');

  // 5. 医生端
  await page.evaluate(() => { const b = document.querySelectorAll('.view-btn'); if (b.length >= 3) b[2].click(); });
  await page.waitForTimeout(3000);
  await page.screenshot({ path: path.join(__dirname, '05-doctor.png') });
  console.log('截图 5: 医生端');

  // 6. 老人端全页面
  await page.evaluate(() => { const b = document.querySelectorAll('.view-btn'); if (b.length >= 1) b[0].click(); });
  await page.waitForTimeout(3000);
  await page.screenshot({ path: path.join(__dirname, '06-elderly-full.png'), fullPage: true });
  console.log('截图 6: 老人端全页面');

  await browser.close();
  console.log('全部完成');
}

main().catch((e) => { console.error('失败:', e); process.exit(1); });
