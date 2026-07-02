import { showOfflineToast, clearOfflineToast } from '../ui/toast.js';
import {
  enqueueOffline,
  syncOfflineQueue,
  getCachedSessions,
  cacheSessions,
  getCachedScales,
  cacheScales,
} from '../db/offline.js';

const API_BASE = '/api/v1';

let _token = '';
let _refreshToken = '';
let _lastSyncedState = null;
// 并发 refresh 锁：同时多个 401 时只刷新一次
let _refreshPromise = null;

export function getToken() {
  if (_token) return _token;
  try { return localStorage.getItem('token') || ''; } catch (e) { return ''; }
}
export function setToken(token) {
  _token = token;
  try {
    if (token) localStorage.setItem('token', token);
    else localStorage.removeItem('token');
  } catch (e) {}
}
export function clearToken() {
  _token = '';
  _refreshToken = '';
  try {
    localStorage.removeItem('token');
    localStorage.removeItem('refresh_token');
  } catch (e) {}
}

export function getRefreshToken() {
  if (_refreshToken) return _refreshToken;
  try { return localStorage.getItem('refresh_token') || ''; } catch (e) { return ''; }
}
export function setRefreshToken(token) {
  _refreshToken = token;
  try {
    if (token) localStorage.setItem('refresh_token', token);
    else localStorage.removeItem('refresh_token');
  } catch (e) {}
}

// access token 过期时用 refresh token 换新对
async function tryRefresh() {
  if (_refreshPromise) return _refreshPromise;
  const rt = getRefreshToken();
  if (!rt) return false;

  _refreshPromise = (async function() {
    try {
      const resp = await fetch(API_BASE + '/auth/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: rt }),
      });
      if (!resp.ok) {
        clearToken();
        return false;
      }
      const data = await resp.json();
      setToken(data.access_token);
      if (data.refresh_token) setRefreshToken(data.refresh_token);
      return true;
    } catch (e) {
      clearToken();
      return false;
    } finally {
      _refreshPromise = null;
    }
  })();
  return _refreshPromise;
}

// 内存缓存
const apiCache = {};

export function invalidateCache(path) {
  if (path) {
    delete apiCache[path];
  } else {
    Object.keys(apiCache).forEach(function(k) { delete apiCache[k]; });
  }
}

function sleep(ms) { return new Promise(function(resolve) { setTimeout(resolve, ms); }); }

async function fetchWithRetry(url, options) {
  const method = (options.method || 'GET').toUpperCase();
  const isRead = method === 'GET' || method === 'HEAD';
  const maxRetries = isRead && options.retry !== false ? 2 : 0;
  var lastErr;
  for (var i = 0; i <= maxRetries; i++) {
    try {
      var _opts = {};
      for (var _k in options) {
        if (_k !== 'cache' && _k !== 'retry' && _k !== '_retried') _opts[_k] = options[_k];
      }
      return await fetch(url, _opts);
    } catch (err) {
      lastErr = err;
      if (i < maxRetries && (err.message === 'Failed to fetch' || err.message.includes('NetworkError') || err.offline)) {
        await sleep(1000 * Math.pow(2, i));
        continue;
      }
      throw err;
    }
  }
  throw lastErr;
}

async function apiFetch(path, options = {}) {
  const url = API_BASE + path;
  const method = (options.method || 'GET').toUpperCase();
  const headers = { 'Content-Type': 'application/json', ...options.headers };
  const token = getToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const body = options.body ? JSON.stringify(options.body) : undefined;
  const isRead = method === 'GET' || method === 'HEAD';

  // 离线模式：写请求入队
  if (!navigator.onLine && !isRead) {
    await enqueueOffline(method, { path: path, method: method, body: options.body });
    showOfflineToast('网络不可用，数据已保存到本地，恢复网络后自动同步');
    // 返回一个可解析的占位对象，让调用者继续
    return { offlineQueued: true, path: path, method: method };
  }

  // GET 缓存优先策略：先返回缓存，后台刷新
  if (isRead && options.cache) {
    const now = Date.now();
    if (apiCache[url] && (now - apiCache[url].ts) < 60000) {
      return JSON.parse(JSON.stringify(apiCache[url].data));
    }
    // 尝试从 IndexedDB 读取缓存作为 fallback
    try {
      if (path.startsWith('/session/')) {
        const cached = await getCachedSessions();
        if (cached && cached.length > 0) {
          // 后台刷新，先返回缓存
          setTimeout(function() {
            fetchWithRetry(url, { ...options, headers, body }).then(function(response) {
              if (response.ok) return response.json();
            }).then(function(data) {
              if (data) {
                apiCache[url] = { data: JSON.parse(JSON.stringify(data)), ts: Date.now() };
                if (Array.isArray(data)) cacheSessions(data);
              }
            }).catch(function() {});
          }, 0);
          return { sessions: cached };
        }
      }
      if (path.includes('/scale/')) {
        const cached = await getCachedScales();
        if (cached && cached.length > 0) {
          setTimeout(function() {
            fetchWithRetry(url, { ...options, headers, body }).then(function(response) {
              if (response.ok) return response.json();
            }).then(function(data) {
              if (data) {
                apiCache[url] = { data: JSON.parse(JSON.stringify(data)), ts: Date.now() };
                if (Array.isArray(data)) cacheScales(data);
              }
            }).catch(function() {});
          }, 0);
          return { scales: cached };
        }
      }
    } catch (e) {
      // IndexedDB 读取失败，继续走网络
    }
  }

  try {
    var response = await fetchWithRetry(url, { ...options, headers, body });
    clearOfflineToast();
    // access token 过期：尝试 refresh 后重试一次
    if (response.status === 401 && !options._retried) {
      const ok = await tryRefresh();
      if (ok) {
        const newToken = getToken();
        if (newToken) headers['Authorization'] = `Bearer ${newToken}`;
        response = await fetchWithRetry(url, { ...options, headers, body, _retried: true });
      }
    }
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }
    const data = await response.json();
    if (isRead && options.cache) {
      apiCache[url] = { data: JSON.parse(JSON.stringify(data)), ts: Date.now() };
    }
    // 成功返回时更新 IndexedDB 缓存
    if (isRead && path.startsWith('/session/') && data) {
      if (Array.isArray(data)) cacheSessions(data);
      else if (data.sessions && Array.isArray(data.sessions)) cacheSessions(data.sessions);
    }
    if (isRead && path.includes('/scale/') && data) {
      if (Array.isArray(data)) cacheScales(data);
      else if (data.scales && Array.isArray(data.scales)) cacheScales(data.scales);
    }
    return data;
  } catch (err) {
    if (err.message === 'Failed to fetch' || err.message.includes('NetworkError')) {
      err.offline = true;
      showOfflineToast('网络连接异常，请检查网络后重试');
      // 如果是 GET 请求，再次尝试从 IndexedDB 返回缓存
      if (isRead && path.startsWith('/session/')) {
        try {
          const cached = await getCachedSessions();
          if (cached && cached.length > 0) return { sessions: cached };
        } catch (e) {}
      }
      if (isRead && path.includes('/scale/')) {
        try {
          const cached = await getCachedScales();
          if (cached && cached.length > 0) return { scales: cached };
        } catch (e) {}
      }
    }
    throw err;
  }
}

// 网络恢复时自动同步离线队列
window.addEventListener('online', function() {
  clearOfflineToast();
  syncOfflineQueue(API_BASE, getToken).then(function(result) {
    if (result && result.synced > 0) {
      console.log('[Offline] Synced ' + result.synced + ' items, failed ' + result.failed);
    }
  }).catch(function(err) {
    console.warn('[Offline] Auto sync failed', err);
  });
});

export { apiCache };

function computeDiff(current, previous) {
  var diff = { added: [], removed: [], modified: [] };
  if (!previous) {
    // 首次同步：全量作为 modified 字段
    diff.modified = [
      { field: 'nodes', value: current.nodes || [] },
      { field: 'edges', value: current.edges || [] },
      { field: 'node_id_counter', value: current.node_id_counter || 0 },
      { field: 'current_day', value: current.current_day || 0 },
      { field: 'day_snapshots', value: current.day_snapshots || {} },
      { field: 'baseline_metrics', value: current.baseline_metrics || null },
      { field: 'welcome_dismissed', value: current.welcome_dismissed || 0 },
    ];
    return diff;
  }
  // 节点 diff
  var prevNodeIds = new Set((previous.nodes || []).map(function(n) { return n.id; }));
  var currNodeIds = new Set((current.nodes || []).map(function(n) { return n.id; }));
  (current.nodes || []).forEach(function(n) {
    if (!prevNodeIds.has(n.id)) {
      diff.added.push({ target: 'nodes', value: n });
    }
  });
  (previous.nodes || []).forEach(function(n) {
    if (!currNodeIds.has(n.id)) {
      diff.removed.push({ target: 'nodes', value: { id: n.id } });
    }
  });
  // 边 diff
  var prevEdgeKeys = new Set((previous.edges || []).map(function(e) { return (e.from || e.source) + '-' + (e.to || e.target) + '-' + e.type; }));
  var currEdgeKeys = new Set((current.edges || []).map(function(e) { return (e.from || e.source) + '-' + (e.to || e.target) + '-' + e.type; }));
  (current.edges || []).forEach(function(e) {
    var key = (e.from || e.source) + '-' + (e.to || e.target) + '-' + e.type;
    if (!prevEdgeKeys.has(key)) {
      diff.added.push({ target: 'edges', value: e });
    }
  });
  (previous.edges || []).forEach(function(e) {
    var key = (e.from || e.source) + '-' + (e.to || e.target) + '-' + e.type;
    if (!currEdgeKeys.has(key)) {
      diff.removed.push({ target: 'edges', value: { from: e.from || e.source, to: e.to || e.target, type: e.type } });
    }
  });
  // 标量字段 diff
  ['node_id_counter', 'current_day', 'welcome_dismissed'].forEach(function(field) {
    if (current[field] !== previous[field]) {
      diff.modified.push({ field: field, value: current[field] });
    }
  });
  if (JSON.stringify(current.day_snapshots) !== JSON.stringify(previous.day_snapshots)) {
    diff.modified.push({ field: 'day_snapshots', value: current.day_snapshots });
  }
  if (JSON.stringify(current.baseline_metrics) !== JSON.stringify(previous.baseline_metrics)) {
    diff.modified.push({ field: 'baseline_metrics', value: current.baseline_metrics });
  }
  return diff;
}

export async function register(phone, password, role = 'elderly', name = '') {
  const data = await apiFetch('/auth/register', { method: 'POST', body: { phone, password, role, name } });
  setToken(data.access_token);
  if (data.refresh_token) setRefreshToken(data.refresh_token);
  return data;
}

export async function login(phone, password) {
  const data = await apiFetch('/auth/login', { method: 'POST', body: { phone, password } });
  setToken(data.access_token);
  if (data.refresh_token) setRefreshToken(data.refresh_token);
  return data;
}

export async function getMe() { return apiFetch('/auth/me'); }
export async function getRecoveryCode() { return apiFetch('/auth/recovery-code'); }
export async function changePassword(oldPassword, newPassword) {
  return apiFetch('/auth/change-password', {
    method: 'POST',
    body: { old_password: oldPassword, new_password: newPassword },
  });
}
export async function logout() {
  // 通知后端吊销 refresh token + 黑名单 access token
  try { await apiFetch('/auth/logout', { method: 'POST' }); } catch (e) { /* 即使失败也清除本地 */ }
  clearToken();
}
export function isLoggedIn() { return !!getToken(); }

export async function createSession(dayNumber, text, dialect = 'mandarin', audioMetrics = null) {
  const body = { day_number: dayNumber, narrative_input: { text, dialect } };
  if (audioMetrics) body.audio_metrics = audioMetrics;
  return apiFetch('/session/', { method: 'POST', body });
}

export async function listSessions(limit = 30) { return apiFetch(`/session/?limit=${limit}`, { cache: true }); }
export async function getHealthTrend(days = 7) { return apiFetch(`/session/trend/health?days=${days}`, { cache: true }); }
export async function getEmotionTrend(days = 30) { return apiFetch(`/session/trend/emotion?days=${days}`, { cache: true }); }
export async function getLatestGraph() { return apiFetch('/graph/latest', { cache: true }); }
export async function exportGraphJSON() { return apiFetch('/graph/export/json'); }
export async function setBaseline(sessionId) { return apiFetch('/baseline/', { method: 'POST', body: { session_id: sessionId } }); }
export async function getBaseline() { return apiFetch('/baseline/', { cache: true }); }
export async function getSttHealth() { return apiFetch('/stt/health', { cache: true }); }

// ========== 训练游戏 ==========
export async function saveTrainingScore(gameType, score) {
  return apiFetch('/training/', { method: 'POST', body: { game_type: gameType, score } });
}
export async function listTrainingHistory(limit = 50) {
  return apiFetch(`/training/?limit=${limit}`, { cache: true });
}
export async function getTrainingStats(days = 30) {
  return apiFetch(`/training/stats?days=${days}`, { cache: true });
}

export async function healthCheck() {
  // /health 无版本前缀
  try {
    const response = await fetchWithRetry('/health', { headers: { 'Content-Type': 'application/json' }, cache: true });
    clearOfflineToast();
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }
    return await response.json();
  } catch (err) {
    if (err.message === 'Failed to fetch' || err.message.includes('NetworkError')) {
      err.offline = true;
      showOfflineToast('网络连接异常，请检查网络后重试');
    }
    throw err;
  }
}

// State sync (login required) — 增量 diff 同步
export async function syncState(payload) {
  var diff = computeDiff(payload, _lastSyncedState);
  _lastSyncedState = JSON.parse(JSON.stringify(payload));
  return apiFetch('/state/', { method: 'PATCH', body: diff });
}
export async function loadServerState() {
  return apiFetch('/state/');
}
export async function clearServerState() {
  return apiFetch('/state/', { method: 'DELETE' });
}

// 数据备份与恢复
export async function exportLogs() {
  const url = API_BASE + '/backup/logs';
  const token = getToken();
  const headers = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const response = await fetch(url, { method: 'GET', headers });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: '导出日志失败' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }
  const blob = await response.blob();
  const blobUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = blobUrl;
  a.download = `cognitive-garden-logs-${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.zip`;
  a.click();
  URL.revokeObjectURL(blobUrl);
}

export async function exportBackup() {
  const url = API_BASE + '/backup/export';
  const token = getToken();
  const headers = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const response = await fetch(url, { method: 'GET', headers });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: '导出失败' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }
  const blob = await response.blob();
  // 触发下载
  const blobUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = blobUrl;
  a.download = `cognitive-garden-backup-${new Date().toISOString().slice(0,10)}.json.gz`;
  a.click();
  URL.revokeObjectURL(blobUrl);
}

export async function importBackup(file) {
  const formData = new FormData();
  formData.append('file', file, file.name);
  const url = API_BASE + '/backup/import';
  const token = getToken();
  const headers = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const response = await fetch(url, { method: 'POST', headers, body: formData });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: '导入失败' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }
  return await response.json();
}

// Upload audio for STT transcription
export async function uploadAudio(blob) {
  const formData = new FormData();
  formData.append('audio', blob, 'recording.webm');
  const url = API_BASE + '/stt/transcribe';
  const token = getToken();
  const headers = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const response = await fetch(url, { method: 'POST', headers, body: formData });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'STT failed' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }
  return await response.json();
}

export { API_BASE };

// ========== 认知量表 ==========
export async function listScales() {
  return apiFetch('/scale/');
}

export async function getScaleDetail(scaleId) {
  return apiFetch(`/scale/${scaleId}`);
}

export async function submitScale(scaleId, answers) {
  return apiFetch(`/scale/${scaleId}/submit`, {
    method: 'POST',
    body: { answers: answers },
  });
}

export async function getScaleHistory(scaleType) {
  const query = scaleType ? `?scale_type=${scaleType}` : '';
  return apiFetch(`/scale/history/all${query}`, { cache: true });
}

// ========== 自定义词典 ==========
export async function getLexicon(wordType) {
  const query = wordType ? `?word_type=${wordType}` : '';
  return apiFetch(`/lexicon/${query}`, { cache: true });
}

export async function addLexiconWord(word, word_type) {
  return apiFetch('/lexicon/', { method: 'POST', body: { word, word_type } });
}

export async function deleteLexiconWord(word_id) {
  return apiFetch(`/lexicon/${word_id}`, { method: 'DELETE' });
}

export async function importLexicon(items) {
  return apiFetch('/lexicon/import', { method: 'POST', body: { items } });
}

// ========== 记忆衰退分析 ==========
export async function getDeclineAnalysis(windowDays = 7) {
  return apiFetch(`/decline/analysis?window_days=${windowDays}`, { cache: true });
}

export async function getDeclineTimeline(days = 30) {
  return apiFetch(`/decline/timeline?days=${days}`, { cache: true });
}

// ========== LLM 接口 ==========
export async function llmSummarize(narratives, days = 7) {
  return apiFetch('/llm/summarize', {
    method: 'POST',
    body: { narratives, days },
  });
}

export async function llmEmotion(text) {
  return apiFetch('/llm/emotion', {
    method: 'POST',
    body: { text },
  });
}

export async function llmQA(question, userId) {
  const body = { question };
  if (userId) body.user_id = userId;
  return apiFetch('/llm/qa', {
    method: 'POST',
    body: body,
  });
}

// ========== 家属端通知 ==========
export async function getNotifications(unread = false) {
  const query = unread ? '?unread=true' : '';
  return apiFetch(`/notification/${query}`, { cache: true });
}

export async function markNotificationRead(id) {
  return apiFetch(`/notification/${id}/read`, { method: 'PUT' });
}

export async function markAllNotificationsRead() {
  return apiFetch('/notification/read-all', { method: 'PUT' });
}

export async function getUnreadCount() {
  return apiFetch('/notification/unread-count', { cache: true });
}

export async function linkFamilyMember(elderly_username, relation) {
  return apiFetch('/notification/family-link', { method: 'POST', body: { elderly_username, relation } });
}

export async function getFamilyMembers() {
  return apiFetch('/notification/family-members', { cache: true });
}

// ========== 端到端加密解密 ==========
// 使用浏览器 Web Crypto API 实现 AES-256-GCM 解密
export async function e2eeDecrypt(ciphertext, iv, tag, senderId) {
  // 从 localStorage 获取主密钥（实际是包装后的，需先 unwrap，这里简化处理）
  var wrappedKey = localStorage.getItem('cg_master_key');
  if (!wrappedKey) {
    throw new Error('主密钥未缓存，无法解密');
  }
  // 派生共享密钥：master_key + senderId
  var encoder = new TextEncoder();
  var salt = encoder.encode(senderId + ':shared');
  var keyMaterial = await crypto.subtle.importKey(
    'raw',
    base64ToBytes(wrappedKey),
    { name: 'HKDF' },
    false,
    ['deriveKey']
  );
  var sharedKey = await crypto.subtle.deriveKey(
    { name: 'HKDF', hash: 'SHA-256', salt: salt, info: encoder.encode('cognitive-garden-e2ee-v1') },
    keyMaterial,
    { name: 'AES-GCM', length: 256 },
    false,
    ['decrypt']
  );
  // 解密
  var ct = base64ToBytes(ciphertext);
  var nonce = base64ToBytes(iv);
  var authTag = base64ToBytes(tag);
  // 将 ciphertext 和 tag 拼接
  var combined = new Uint8Array(ct.length + authTag.length);
  combined.set(ct, 0);
  combined.set(authTag, ct.length);
  var decrypted = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: nonce },
    sharedKey,
    combined
  );
  return new TextDecoder().decode(decrypted);
}

function base64ToBytes(base64) {
  var binaryString = atob(base64);
  var bytes = new Uint8Array(binaryString.length);
  for (var i = 0; i < binaryString.length; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }
  return bytes;
}

// ========== 离线同步协议接口 ==========
export async function pullChanges(userId) {
  return apiFetch('/sync/pull', {
    method: 'POST',
    body: { user_id: userId },
  });
}

export async function pushChanges(changes) {
    return apiFetch('/sync/push', {
    method: 'POST',
    body: { changes: changes },
  });
}

// ========== WebSocket 消息发送 ==========
export async function sendWebSocketCare(to, text, audioBase64) {
  var payload = { to: to, type: 'family_care', payload: { text: text, audio: audioBase64 }, timestamp: new Date().toISOString() };
  return payload;
}

export async function sendWebSocketReadReceipt(to, messageId) {
  return { to: to, type: 'read_receipt', payload: { message_id: messageId }, timestamp: new Date().toISOString() };
}

export async function sendWebSocketAdvice(to, category, content, priority) {
  return { to: to, type: 'doctor_advice', payload: { category: category, content: content, priority: priority }, timestamp: new Date().toISOString() };
}
