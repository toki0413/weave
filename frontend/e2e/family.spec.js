import { test, expect } from '@playwright/test';

test.describe('家属端 E2E 测试', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.header', { timeout: 10000 });
    // 关闭首次访问的引导遮罩，否则会拦截后续点击
    const skipBtn = page.locator('.onboarding-btn-skip');
    if (await skipBtn.count() > 0) {
      await skipBtn.click();
    }
  });

  test('登录家属账号 → 查看老人看板 → 查看通知 → 发送语音留言 → 查看老人历史', async ({ page }) => {
    // 用时间戳生成动态手机号，避免与持久化 DB 已有账号冲突
    const ts = String(Date.now()).slice(-8);
    const elderlyPhone = '138' + ts;
    const familyPhone = '139' + ts;
    const password = 'Test123!';

    const tokens = await page.evaluate(async ({ elderlyPhone, familyPhone, password }) => {
      // 注册老人
      const elderlyReg = await fetch('/api/v1/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone: elderlyPhone, password, role: 'elderly', name: '测试老人' })
      });
      const elderlyData = await elderlyReg.json();
      if (!elderlyData.access_token) throw new Error('老人注册失败: ' + JSON.stringify(elderlyData));
      const elderlyToken = elderlyData.access_token;

      // 注册家属
      const familyReg = await fetch('/api/v1/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone: familyPhone, password, role: 'family', name: '测试家属' })
      });
      const familyData = await familyReg.json();
      if (!familyData.access_token) throw new Error('家属注册失败: ' + JSON.stringify(familyData));
      const familyToken = familyData.access_token;

      // 家属绑定老人
      const linkRes = await fetch('/api/v1/notification/family-link', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + familyToken
        },
        body: JSON.stringify({ elderly_username: elderlyPhone, relation: '子女' })
      });
      if (!linkRes.ok) throw new Error('家属绑定失败: ' + await linkRes.text());

      // 老人创建一条会话
      const sessionRes = await fetch('/api/v1/session/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + elderlyToken
        },
        body: JSON.stringify({
          day_number: 1,
          narrative_input: { text: '今天去医院看张医生，量了血压，然后去药店买了药', dialect: 'mandarin' }
        })
      });
      const sessionData = await sessionRes.json();
      if (!sessionRes.ok) throw new Error('会话创建失败: ' + JSON.stringify(sessionData));

      // 老人分享会话给家属（这会触发通知）
      const shareRes = await fetch('/api/v1/share/session/' + sessionData.id, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + elderlyToken
        },
        body: JSON.stringify({ message: '分享今天的记录' })
      });
      if (!shareRes.ok) throw new Error('分享失败: ' + await shareRes.text());

      // 保存 token
      localStorage.setItem('token', familyToken);
      localStorage.setItem('elderlyToken', elderlyToken);
      return { familyToken, elderlyToken };
    }, { elderlyPhone, familyPhone, password });

    // 1. 切换到家属端（已经在 localStorage 中设置了 token）
    await page.click('text=家属端');
    await expect(page.locator('.view-btn.active')).toContainText('家属端');

    // 2. 查看老人状态看板
    await expect(page.locator('.fam-hero')).toBeVisible();

    // 3. 查看通知（调用 API 并验证）
    const notifications = await page.evaluate(async () => {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/notification/', {
        headers: { 'Authorization': 'Bearer ' + token }
      });
      return res.json();
    });
    expect(Array.isArray(notifications)).toBe(true);
    expect(notifications.length).toBeGreaterThan(0);

    // 4. 发送语音留言（模拟 base64 音频）
    const elderlyId = await page.evaluate(async () => {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/notification/family-members', {
        headers: { 'Authorization': 'Bearer ' + token }
      });
      const members = await res.json();
      return members[0]?.elderly_user_id;
    });

    expect(elderlyId).toBeDefined();

    const voiceResult = await page.evaluate(async (elderlyId) => {
      const token = localStorage.getItem('token');
      // 模拟 1 秒的 base64 音频（空数据占位）
      const fakeAudio = 'data:audio/webm;base64,GkXfo6ChoCgICAgICA'; 
      const res = await fetch('/api/v1/voice-message/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + token
        },
        body: JSON.stringify({
          receiver_id: elderlyId,
          audio_base64: fakeAudio,
          duration: 1
        })
      });
      return res.json();
    }, elderlyId);
    expect(voiceResult.id).toBeDefined();
    expect(voiceResult.audio_url).toContain('/uploads/');

    // 5. 查看老人历史记录（分享记录）
    const shareResult = await page.evaluate(async () => {
      const elderlyToken = localStorage.getItem('elderlyToken');
      // 获取老人会话列表
      const res = await fetch('/api/v1/session/?limit=5', {
        headers: { 'Authorization': 'Bearer ' + elderlyToken }
      });
      return res.json();
    });
    expect(Array.isArray(shareResult)).toBe(true);
    expect(shareResult.length).toBeGreaterThan(0);
    expect(shareResult[0].narrative).toContain('医院');
  });
});
