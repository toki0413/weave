// ============ 按钮加载态工具 ============

function setLoading(btn, isLoading, loadingText) {
  if (!btn) return;
  if (isLoading) {
    if (!btn._originalText && btn.textContent) btn._originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = loadingText || '处理中…';
  } else {
    btn.disabled = false;
    btn.textContent = btn._originalText || '';
    btn._originalText = null;
  }
}

function withLoading(btn, fn, loadingText) {
  setLoading(btn, true, loadingText);
  var done = function() { setLoading(btn, false); };
  try {
    var result = fn();
    if (result && typeof result.then === 'function') {
      return result.then(
        function(value) { done(); return value; },
        function(err) { done(); throw err; }
      );
    }
    done();
    return result;
  } catch (err) {
    done();
    throw err;
  }
}

export { setLoading, withLoading };
