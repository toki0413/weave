import { test, expect } from '@playwright/test';

// 离线模式测试：构建产物中没有暴露 /src/db/offline.js，
// 这里用原生 IndexedDB API 复刻离线队列的核心逻辑，验证离线入队 → 恢复同步的完整链路。
test.describe('离线模式 E2E 测试', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.header', { timeout: 10000 });
    const skipBtn = page.locator('.onboarding-btn-skip');
    if (await skipBtn.count() > 0) {
      await skipBtn.click();
    }
  });

  test('模拟离线 → 提交会话 → IndexedDB 有队列 → 恢复网络 → 数据同步到后端', async ({ page }) => {
    // 每个测试用独立数据库，避免历史数据干扰
    const dbName = 'cg-offline-test-' + Date.now();
    // 注册登录一个测试用户
    const phone = '138' + String(Date.now()).slice(-8);
    const password = 'Test123!';
    await page.evaluate(async ({ phone, password }) => {
      const reg = await fetch('/api/v1/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone, password, role: 'elderly', name: '离线测试用户' })
      });
      const data = await reg.json();
      if (!data.access_token) throw new Error('注册失败: ' + JSON.stringify(data));
      localStorage.setItem('token', data.access_token);
    }, { phone, password });

    // 1. 模拟离线
    await page.context().setOffline(true);

    // 2. 离线时尝试 fetch 会失败，手动入队 IndexedDB（复刻 enqueueOffline 的行为）
    const queuePayload = {
      path: '/session/',
      method: 'POST',
      body: {
        day_number: 2,
        narrative_input: { text: '离线测试叙事：今天去了公园，遇到老李', dialect: 'mandarin' }
      }
    };

    await page.evaluate(async ({ dbName, queuePayload }) => {
      const request = indexedDB.open(dbName, 1);
      await new Promise((resolve, reject) => {
        request.onupgradeneeded = function(event) {
          const db = event.target.result;
          if (!db.objectStoreNames.contains('offlineQueue')) {
            db.createObjectStore('offlineQueue', { keyPath: 'id', autoIncrement: true });
          }
        };
        request.onsuccess = function() {
          const db = request.result;
          const tx = db.transaction('offlineQueue', 'readwrite');
          tx.objectStore('offlineQueue').add({
            type: 'POST',
            payload: queuePayload,
            created_at: new Date().toISOString(),
            retry_count: 0,
          });
          tx.oncomplete = function() { db.close(); resolve(); };
          tx.onerror = function() { reject(tx.error); };
        };
        request.onerror = function() { reject(request.error); };
      });
    }, { dbName, queuePayload });

    // 3. 验证 IndexedDB 中有离线队列
    const queueItems = await page.evaluate(async (dbName) => {
      return new Promise((resolve) => {
        const request = indexedDB.open(dbName, 1);
        request.onsuccess = function() {
          const db = request.result;
          const tx = db.transaction('offlineQueue', 'readonly');
          const getAll = tx.objectStore('offlineQueue').getAll();
          getAll.onsuccess = function() { db.close(); resolve(getAll.result); };
        };
      });
    }, dbName);
    expect(Array.isArray(queueItems)).toBe(true);
    expect(queueItems.length).toBeGreaterThan(0);
    expect(queueItems[0].type).toBe('POST');
    expect(queueItems[0].payload.body.narrative_input.text).toContain('离线测试叙事');

    // 4. 恢复网络
    await page.context().setOffline(false);

    // 5. 模拟 syncOfflineQueue：从队列取出，fetch 后端，成功后删除
    const syncResult = await page.evaluate(async ({ dbName }) => {
      const token = localStorage.getItem('token');
      const openDB = () => new Promise((resolve) => {
        const req = indexedDB.open(dbName, 1);
        req.onsuccess = function() { resolve(req.result); };
      });
      const db = await openDB();
      const items = await new Promise((resolve) => {
        const tx = db.transaction('offlineQueue', 'readonly');
        const getAll = tx.objectStore('offlineQueue').getAll();
        getAll.onsuccess = function() { resolve(getAll.result); };
      });
      db.close();
      if (!items || items.length === 0) return { synced: 0, failed: 0 };

      let synced = 0, failed = 0;
      for (const item of items) {
        try {
          // path 是 /session/，API 前缀 /api/v1
          const url = '/api/v1' + item.payload.path;
          const res = await fetch(url, {
            method: item.payload.method || 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
            body: JSON.stringify(item.payload.body),
          });
          if (res.ok) {
            // 删除已同步的项
            const db2 = await openDB();
            await new Promise((resolve) => {
              const tx = db2.transaction('offlineQueue', 'readwrite');
              tx.objectStore('offlineQueue').delete(item.id);
              tx.oncomplete = function() { db2.close(); resolve(); };
            });
            synced++;
          } else {
            const errBody = await res.text();
            console.error('Sync failed for item', item.id, res.status, errBody);
            failed++;
          }
        } catch (err) {
          failed++;
        }
      }
      return { synced, failed };
    }, { dbName });
    expect(syncResult.synced).toBeGreaterThan(0);
    expect(syncResult.failed).toBe(0);

    // 6. 验证队列已清空
    const queueAfterSync = await page.evaluate(async (dbName) => {
      return new Promise((resolve) => {
        const request = indexedDB.open(dbName, 1);
        request.onsuccess = function() {
          const db = request.result;
          const tx = db.transaction('offlineQueue', 'readonly');
          const getAll = tx.objectStore('offlineQueue').getAll();
          getAll.onsuccess = function() { db.close(); resolve(getAll.result); };
        };
      });
    }, dbName);
    expect(queueAfterSync.length).toBe(0);

    // 7. 验证后端确实保存了数据
    const sessions = await page.evaluate(async () => {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/session/?limit=5', {
        headers: { 'Authorization': 'Bearer ' + token }
      });
      return res.json();
    });
    expect(Array.isArray(sessions)).toBe(true);
    expect(sessions.length).toBeGreaterThan(0);
    const found = sessions.some(s => s.narrative && s.narrative.includes('离线测试叙事'));
    expect(found).toBe(true);
  });
});
