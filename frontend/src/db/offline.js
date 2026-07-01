// ============ IndexedDB Offline Cache ============
// 原生 IndexedDB API，不依赖 dexie，减少依赖体积

const DB_NAME = 'cognitive-garden-offline';
const DB_VERSION = 2;

function openDB() {
  return new Promise(function(resolve, reject) {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onerror = function() { reject(request.error); };
    request.onsuccess = function() { resolve(request.result); };
    request.onupgradeneeded = function(event) {
      const db = event.target.result;
      if (!db.objectStoreNames.contains('offlineQueue')) {
        db.createObjectStore('offlineQueue', { keyPath: 'id', autoIncrement: true });
      }
      if (!db.objectStoreNames.contains('cachedSessions')) {
        const store = db.createObjectStore('cachedSessions', { keyPath: 'id' });
        store.createIndex('user_id', 'user_id', { unique: false });
        store.createIndex('created_at', 'created_at', { unique: false });
      }
      if (!db.objectStoreNames.contains('cachedScales')) {
        const store = db.createObjectStore('cachedScales', { keyPath: 'id' });
        store.createIndex('scale_type', 'scale_type', { unique: false });
        store.createIndex('created_at', 'created_at', { unique: false });
      }
      // 新增：设备向量时钟与离线队列增强
      if (!db.objectStoreNames.contains('deviceSync')) {
        const store = db.createObjectStore('deviceSync', { keyPath: 'device_id' });
      }
      if (!db.objectStoreNames.contains('cachedMessages')) {
        db.createObjectStore('cachedMessages', { keyPath: 'id' });
      }
    };
  });
}

function withStore(storeName, mode) {
  return openDB().then(function(db) {
    return new Promise(function(resolve, reject) {
      const tx = db.transaction(storeName, mode);
      tx.oncomplete = function() { db.close(); };
      tx.onerror = function() { reject(tx.error); };
      resolve(tx.objectStore(storeName));
    });
  });
}

function promisifyRequest(request) {
  return new Promise(function(resolve, reject) {
    request.onsuccess = function() { resolve(request.result); };
    request.onerror = function() { reject(request.error); };
  });
}

function getDeviceId() {
  var agent = navigator.userAgent || '';
  var rand = Math.random().toString(36).slice(2, 10);
  var key = 'cg_device_id';
  var stored = localStorage.getItem(key);
  if (!stored) {
    stored = agent + '::' + rand;
    localStorage.setItem(key, stored);
  }
  return stored;
}

// ========== Device Sync Vector Clock ==========
export async function getLocalVectorClock() {
  const store = await withStore('deviceSync', 'readonly');
  try {
    const record = await promisifyRequest(store.get(getDeviceId()));
    return (record && record.vector_clock) || {};
  } catch (e) {
    return {};
  }
}

export async function setLocalVectorClock(clock) {
  const store = await withStore('deviceSync', 'readwrite');
  const record = {
    device_id: getDeviceId(),
    vector_clock: clock,
    last_sync_at: new Date().toISOString(),
  };
  return promisifyRequest(store.put(record));
}

// ========== Offline Queue ==========
export async function enqueueOffline(type, payload) {
  const store = await withStore('offlineQueue', 'readwrite');
  const item = {
    type: type,
    payload: payload,
    device_id: getDeviceId(),
    vector_clock: await getLocalVectorClock(),
    created_at: new Date().toISOString(),
    retry_count: 0,
  };
  return promisifyRequest(store.add(item));
}

export async function getOfflineQueue() {
  const store = await withStore('offlineQueue', 'readonly');
  return promisifyRequest(store.getAll());
}

export async function deleteOfflineItem(id) {
  const store = await withStore('offlineQueue', 'readwrite');
  return promisifyRequest(store.delete(id));
}

export async function incrementRetryCount(id) {
  const store = await withStore('offlineQueue', 'readwrite');
  const item = await promisifyRequest(store.get(id));
  if (item) {
    item.retry_count = (item.retry_count || 0) + 1;
    await promisifyRequest(store.put(item));
  }
}

export async function syncOfflineQueue(apiBase, getToken) {
  const items = await getOfflineQueue();
  if (!items || items.length === 0) return { synced: 0, failed: 0 };

  let synced = 0;
  let failed = 0;
  const maxRetries = 3;

  for (const item of items) {
    if (item.retry_count >= maxRetries) {
      failed++;
      continue;
    }
    try {
      let url = apiBase + item.payload.path;
      let body = item.payload.body;
      const headers = { 'Content-Type': 'application/json' };
      const token = getToken();
      if (token) headers['Authorization'] = 'Bearer ' + token;

      const response = await fetch(url, {
        method: item.payload.method || 'POST',
        headers: headers,
        body: body ? JSON.stringify(body) : undefined,
      });
      if (response.ok) {
        await deleteOfflineItem(item.id);
        synced++;
      } else {
        await incrementRetryCount(item.id);
        failed++;
      }
    } catch (err) {
      await incrementRetryCount(item.id);
      failed++;
    }
  }

  return { synced: synced, failed: failed };
}

// ========== Pull / Push Changes ==========
export async function pullChanges(apiBase, getToken, userId) {
  const token = getToken();
  if (!token) return { changes: {}, server_vector_clock: {} };

  const localClock = await getLocalVectorClock();
  const url = apiBase + '/sync/pull?user_id=' + encodeURIComponent(userId);
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
    body: JSON.stringify({ device_id: getDeviceId(), last_vector_clock: localClock }),
  });
  if (!response.ok) throw new Error('pull_changes failed: ' + response.status);
  const data = await response.json();
  if (data.server_vector_clock) {
    await setLocalVectorClock(data.server_vector_clock);
  }
  return data;
}

export async function pushChanges(apiBase, getToken, changes) {
  const token = getToken();
  if (!token) return { conflicts: [], new_vector_clock: {} };

  const url = apiBase + '/sync/push';
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
    body: JSON.stringify({ device_id: getDeviceId(), changes: changes }),
  });
  if (!response.ok) throw new Error('push_changes failed: ' + response.status);
  const data = await response.json();
  if (data.new_vector_clock) {
    await setLocalVectorClock(data.new_vector_clock);
  }
  return data;
}

export async function resolveConflictsAndNotify(conflicts, notifyFn) {
  if (!conflicts || conflicts.length === 0) return;
  for (var i = 0; i < conflicts.length; i++) {
    var c = conflicts[i];
    console.log('[Sync] Conflict resolved:', c);
    if (notifyFn) {
      notifyFn('此条目已在其他设备更新，已合并: ' + (c.type || 'unknown'));
    }
  }
}

// ========== Cached Sessions ==========
export async function cacheSessions(sessions) {
  const store = await withStore('cachedSessions', 'readwrite');
  const now = new Date().toISOString();
  const thirtyDaysAgo = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString();

  // 先清理超过30天的缓存
  const index = store.index('created_at');
  const range = IDBKeyRange.upperBound(thirtyDaysAgo);
  const oldKeys = await promisifyRequest(index.getAllKeys(range));
  for (const key of oldKeys) {
    store.delete(key);
  }

  // 写入新数据
  for (const session of sessions) {
    if (!session.created_at) session.created_at = now;
    await promisifyRequest(store.put(session));
  }
}

export async function getCachedSessions(userId) {
  const store = await withStore('cachedSessions', 'readonly');
  const all = await promisifyRequest(store.getAll());
  if (userId) {
    return all.filter(function(s) { return s.user_id === userId; });
  }
  return all;
}

export async function clearCachedSessions() {
  const store = await withStore('cachedSessions', 'readwrite');
  return promisifyRequest(store.clear());
}

// ========== Cached Scales ==========
export async function cacheScales(scales) {
  const store = await withStore('cachedScales', 'readwrite');
  const now = new Date().toISOString();
  for (const scale of scales) {
    if (!scale.created_at) scale.created_at = now;
    await promisifyRequest(store.put(scale));
  }
}

export async function getCachedScales(scaleType) {
  const store = await withStore('cachedScales', 'readonly');
  if (scaleType) {
    const index = store.index('scale_type');
    return promisifyRequest(index.getAll(scaleType));
  }
  return promisifyRequest(store.getAll());
}

export async function clearCachedScales() {
  const store = await withStore('cachedScales', 'readwrite');
  return promisifyRequest(store.clear());
}

// ========== Cached Messages ==========
export async function cacheMessages(messages) {
  const store = await withStore('cachedMessages', 'readwrite');
  for (const msg of messages) {
    await promisifyRequest(store.put(msg));
  }
}

export async function getCachedMessages() {
  const store = await withStore('cachedMessages', 'readonly');
  return promisifyRequest(store.getAll());
}

export async function clearCachedMessages() {
  const store = await withStore('cachedMessages', 'readwrite');
  return promisifyRequest(store.clear());
}

// ========== Helpers ==========
export async function clearAllCache() {
  await clearCachedSessions();
  await clearCachedScales();
  await clearCachedMessages();
}
