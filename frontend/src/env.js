// ============ 运行环境检测（U2 微信内浏览器分流） ============
// 微信内置浏览器（X5/WKWebView）的 getUserMedia 权限与 IndexedDB
// 持久化配额不可靠，录音主路径必须引导到系统浏览器。

export function isWeChatBrowser() {
  return /MicroMessenger/i.test(navigator.userAgent || '');
}

// 复制文本：优先 clipboard API，失败回退 execCommand（微信内旧内核）
export function copyToClipboard(text) {
  return new Promise(function(resolve) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(
        function() { resolve(true); },
        function() { resolve(_fallbackCopy(text)); }
      );
    } else {
      resolve(_fallbackCopy(text));
    }
  });
}

function _fallbackCopy(text) {
  try {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    var ok = document.execCommand('copy');
    document.body.removeChild(ta);
    return ok;
  } catch (e) {
    return false;
  }
}
