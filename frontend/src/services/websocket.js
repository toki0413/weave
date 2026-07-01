// ============ WebSocket 三端通信服务 ============
// 封装连接管理、自动重连、SSE 降级

const WS_URL = (() => {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.host;
  return `${protocol}//${host}/api/v1/ws`;
})();

let _ws = null;
let _token = '';
let _onMessage = null;
let _reconnectTimer = null;
let _reconnectAttempts = 0;
let _maxReconnectDelay = 30000; // 最大 30s
let _sseSource = null;
let _useSSE = false;
let _connected = false;
let _pendingQueue = [];

function _getDeviceId() {
  // device_id = navigator.userAgent + 随机字符串
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

export function getDeviceId() {
  return _getDeviceId();
}

export function connect(token, onMessage) {
  _token = token;
  _onMessage = onMessage;
  _useSSE = false;
  _connected = false;
  _reconnectAttempts = 0;
  if (_reconnectTimer) {
    clearTimeout(_reconnectTimer);
    _reconnectTimer = null;
  }
  _tryConnect();
}

function _tryConnect() {
  if (_ws && (_ws.readyState === WebSocket.OPEN || _ws.readyState === WebSocket.CONNECTING)) {
    return;
  }
  if (_useSSE) {
    _connectSSE();
    return;
  }
  try {
    var url = WS_URL + '?token=' + encodeURIComponent(_token);
    _ws = new WebSocket(url);
  } catch (e) {
    console.warn('[WebSocket] 创建失败，降级到 SSE', e);
    _useSSE = true;
    _connectSSE();
    return;
  }

  _ws.onopen = function() {
    _connected = true;
    _reconnectAttempts = 0;
    console.log('[WebSocket] 已连接');
    // 发送待发送队列
    while (_pendingQueue.length > 0) {
      var msg = _pendingQueue.shift();
      _send(msg);
    }
  };

  _ws.onmessage = function(event) {
    try {
      var msg = JSON.parse(event.data);
      if (_onMessage) _onMessage(msg);
    } catch (e) {
      console.warn('[WebSocket] 消息解析失败', e);
    }
  };

  _ws.onclose = function() {
    _connected = false;
    _ws = null;
    console.log('[WebSocket] 连接断开');
    _scheduleReconnect();
  };

  _ws.onerror = function(e) {
    console.warn('[WebSocket] 错误', e);
    _ws = null;
    _connected = false;
    // 首次失败时尝试降级到 SSE
    if (_reconnectAttempts === 0) {
      _useSSE = true;
      _connectSSE();
    } else {
      _scheduleReconnect();
    }
  };
}

function _scheduleReconnect() {
  if (_reconnectTimer) return;
  var delay = Math.min(1000 * Math.pow(2, _reconnectAttempts), _maxReconnectDelay);
  _reconnectAttempts++;
  _reconnectTimer = setTimeout(function() {
    _reconnectTimer = null;
    if (_useSSE) {
      _connectSSE();
    } else {
      _tryConnect();
    }
  }, delay);
}

function _connectSSE() {
  if (_sseSource) {
    try { _sseSource.close(); } catch (e) {}
    _sseSource = null;
  }
  try {
    var url = '/events';
    _sseSource = new EventSource(url);
    _sseSource.onmessage = function(event) {
      try {
        var msg = JSON.parse(event.data);
        if (_onMessage) _onMessage(msg);
      } catch (e) {
        console.warn('[SSE] 消息解析失败', e);
      }
    };
    _sseSource.onopen = function() {
      _connected = true;
      console.log('[SSE] 已连接（降级模式）');
    };
    _sseSource.onerror = function() {
      _connected = false;
      _sseSource.close();
      _sseSource = null;
      _scheduleReconnect();
    };
  } catch (e) {
    console.warn('[SSE] 创建失败', e);
    _scheduleReconnect();
  }
}

function _send(msg) {
  if (_ws && _ws.readyState === WebSocket.OPEN) {
    _ws.send(JSON.stringify(msg));
    return true;
  }
  return false;
}

export function send(message) {
  if (typeof message === 'string') {
    message = { type: 'text', payload: message };
  }
  if (!_send(message)) {
    _pendingQueue.push(message);
    console.log('[WebSocket] 消息已入队，等待连接恢复');
  }
}

export function disconnect() {
  if (_reconnectTimer) {
    clearTimeout(_reconnectTimer);
    _reconnectTimer = null;
  }
  if (_ws) {
    try { _ws.close(); } catch (e) {}
    _ws = null;
  }
  if (_sseSource) {
    try { _sseSource.close(); } catch (e) {}
    _sseSource = null;
  }
  _connected = false;
  _useSSE = false;
  _pendingQueue = [];
  console.log('[WebSocket] 已主动断开');
}

export function isConnected() {
  return _connected;
}

export function isUsingSSE() {
  return _useSSE;
}

// 网络恢复时自动从 SSE 升级回 WebSocket
window.addEventListener('online', function() {
  if (_useSSE && _token) {
    console.log('[WebSocket] 网络恢复，尝试升级回 WebSocket');
    _useSSE = false;
    if (_sseSource) {
      try { _sseSource.close(); } catch (e) {}
      _sseSource = null;
    }
    _tryConnect();
  }
});

// 定期发送心跳
setInterval(function() {
  if (_ws && _ws.readyState === WebSocket.OPEN) {
    _ws.send(JSON.stringify({ type: 'ping', timestamp: new Date().toISOString() }));
  }
}, 30000);
