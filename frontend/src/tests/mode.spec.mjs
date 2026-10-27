// 模式类名单一来源的行为验算（node:test，零依赖）
// 运行：node --test frontend/src/tests/  或  node frontend/src/tests/mode.spec.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { resolveModeClass, applyMode, rememberRole, recallRole } from '../ui/mode.js';

function mkCls() {
  const set = new Set();
  return { add: c => set.add(c), remove: (...cs) => cs.forEach(c => set.delete(c)),
           contains: c => set.has(c), _set: set };
}
function withDom() {
  const store = new Map();
  global.document = {
    documentElement: { classList: mkCls(), style: { setProperty() {} } },
    body: {},
  };
  global.localStorage = {
    getItem: k => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: k => store.delete(k),
  };
  return store;
}

test('白名单外一律 null，未知角色不得落到老人端主题', () => {
  assert.equal(resolveModeClass('elderly'), 'elderly-mode');
  assert.equal(resolveModeClass('family'), 'family-mode');
  assert.equal(resolveModeClass('doctor'), 'doctor-mode');
  for (const bad of ['', 'admin', undefined, null, 'elderly-mode', 'ELDERLY']) {
    assert.equal(resolveModeClass(bad), null, `${bad} 应映射为完整模式`);
  }
});

test('回归：getMe 失败/未知角色的兜底路径不再停在 elderly-mode', () => {
  withDom();
  assert.equal(applyMode(''), null);
  assert.deepEqual([...document.documentElement.classList._set], []);
});

test('applyMode 幂等、互斥、并同步 body class', () => {
  withDom();
  assert.equal(applyMode('family'), 'family-mode');
  assert.equal(applyMode('family'), 'family-mode');
  assert.deepEqual([...document.documentElement.classList._set], ['family-mode']);
  assert.equal(document.body.className, 'mode-family');
  assert.equal(applyMode('doctor'), 'doctor-mode');
  assert.deepEqual([...document.documentElement.classList._set], ['doctor-mode']);
  assert.equal(applyMode(''), null);
  assert.equal(document.body.className, '');
});

test('角色缓存：只接受白名单；getMe 失败不清缓存', () => {
  const store = withDom();
  assert.equal(recallRole(), '');
  rememberRole('elderly');
  assert.equal(store.get('cg-role'), 'elderly');
  assert.equal(recallRole(), 'elderly');
  rememberRole('nonsense');
  assert.equal(store.has('cg-role'), false, '非法角色应清除缓存而非写入');
  rememberRole('family');
  applyMode('');
  assert.equal(recallRole(), 'family', '归零当前模式不应抹掉缓存角色');
});

test('启动时序：首次无缓存→完整模式；getMe 成功后缓存并应用', () => {
  const store = withDom();
  assert.equal(applyMode(recallRole()), null);
  const role = 'elderly';
  rememberRole(role);
  applyMode(role);
  assert.deepEqual([...document.documentElement.classList._set], ['elderly-mode']);
  // 下次启动
  store.delete('__noop');
  assert.equal(recallRole(), 'elderly');
  assert.equal(applyMode(recallRole()), 'elderly-mode');
});
