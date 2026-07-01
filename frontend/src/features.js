// ============ FEATURE FLAGS ============
const DEFAULT_FEATURES = {
  // 示例：灰度功能开关
  newChartRenderer: false,
  advancedDecline: false,
  familyNotificationPush: false,
  doctorPdfExport: false,
  llm_enabled: false,
};

function _getEnvFeatures() {
  try {
    var env = null;
    try {
      env = import.meta.env;
    } catch (e) {}
    if (env) {
      const out = {};
      Object.keys(DEFAULT_FEATURES).forEach(function(k) {
        const key = 'VITE_FF_' + k;
        if (key in env) {
          out[k] = env[key] === 'true' || env[key] === '1';
        }
      });
      return out;
    }
  } catch (e) {}
  return {};
}

function _getStorageFeatures() {
  try {
    var raw = localStorage.getItem('cg-features');
    if (raw) return JSON.parse(raw);
  } catch (e) {}
  return {};
}

export function isEnabled(feature) {
  if (!(feature in DEFAULT_FEATURES)) {
    console.warn('Unknown feature flag:', feature);
    return false;
  }
  // llm_enabled 特殊处理：也读取 localStorage.llmEnabled
  if (feature === 'llm_enabled') {
    var llm = localStorage.getItem('llmEnabled');
    if (llm !== null) return llm === 'true' || llm === '1';
  }
  var env = _getEnvFeatures();
  if (feature in env) return env[feature];
  var storage = _getStorageFeatures();
  if (feature in storage) return storage[feature];
  return DEFAULT_FEATURES[feature];
}

export function setFeature(feature, enabled) {
  var storage = _getStorageFeatures();
  storage[feature] = !!enabled;
  localStorage.setItem('cg-features', JSON.stringify(storage));
}

export function listFeatures() {
  var env = _getEnvFeatures();
  var storage = _getStorageFeatures();
  var out = {};
  Object.keys(DEFAULT_FEATURES).forEach(function(k) {
    out[k] = k in env ? env[k] : (k in storage ? storage[k] : DEFAULT_FEATURES[k]);
  });
  return out;
}
