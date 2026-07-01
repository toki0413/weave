// ============ I18N ============
const DEFAULT_LANG = 'zh';
const STORAGE_KEY = 'cg-lang';

let _locale = null;
let _dict = null;

const _locales = {};

async function loadLocale(lang) {
  if (_locales[lang]) return _locales[lang];
  try {
    const mod = await import(/* @vite-ignore */ `./locales/${lang}.json`);
    _locales[lang] = mod.default || mod;
    return _locales[lang];
  } catch (e) {
    if (lang !== DEFAULT_LANG) {
      return loadLocale(DEFAULT_LANG);
    }
    return {};
  }
}

export async function initI18n() {
  const saved = localStorage.getItem(STORAGE_KEY);
  const navLang = typeof navigator !== 'undefined' && navigator.language ? navigator.language.toLowerCase() : '';
  const lang = saved || (navLang.startsWith('zh') ? 'zh' : 'en');
  _locale = lang;
  _dict = await loadLocale(lang);
  document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
}

export function t(key, fallback) {
  if (!_dict) return fallback || key;
  const keys = key.split('.');
  let val = _dict;
  for (let i = 0; i < keys.length; i++) {
    if (val && typeof val === 'object' && keys[i] in val) {
      val = val[keys[i]];
    } else {
      return fallback !== undefined ? fallback : key;
    }
  }
  return typeof val === 'string' ? val : (fallback !== undefined ? fallback : key);
}

export function setLocale(lang) {
  localStorage.setItem(STORAGE_KEY, lang);
  location.reload();
}

export function getLocale() {
  return _locale || DEFAULT_LANG;
}
