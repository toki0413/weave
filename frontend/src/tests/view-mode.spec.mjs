// viewMode 按模式分片的行为与旁路验算
// 运行：node --test frontend/src/tests/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'path';

const SRC = path.resolve(import.meta.dirname, '..');
const read = p => fs.readFileSync(path.join(SRC, p), 'utf8');

function withStorage(init = {}) {
  const store = new Map(Object.entries(init));
  global.localStorage = {
    getItem: k => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: k => store.delete(k),
    _store: store,
  };
  return store;
}
function withMode(mode) {
  const set = new Set(mode ? [mode] : []);
  global.document = {
    documentElement: { classList: { add: c => set.add(c), remove: c => set.delete(c), contains: c => set.has(c) } },
    body: {},
  };
  return set;
}
// 每个用例都要重新求值模块，否则 viewModeStore 的模块级状态会串味
let seq = 0;
async function loadStores(mode, storage) {
  withMode(mode); withStorage(storage);
  const q = '?v=' + (++seq);
  const m = await import(`../ui/viewModeStore.js${q}`);
  const md = await import(`../ui/mode.js${q}`);
  return { ...m, currentMode: md.currentMode };
}

test('老人端：既读不到也写不进 3D 偏好', async () => {
  const s = await loadStores('elderly-mode', { 'viewMode': '3d', 'viewMode:elderly-mode': '3d' });
  assert.equal(s.getViewMode('elderly-mode'), '2d', '老人端竟读到了 3d');
  assert.equal(s.prefers3D('elderly-mode'), false);
  assert.equal(s.setViewMode('elderly-mode', '3d'), false, '老人端竟然写成功了');
  assert.equal(s.modeSupports3D('elderly-mode'), false);
});

test('家属端写偏好不得改动医生端与老人端', async () => {
  const s = await loadStores('family-mode', {});
  s.setViewMode('family-mode', '3d');
  assert.equal(localStorage.getItem('viewMode:family-mode'), '3d');
  assert.equal(s.getViewMode('doctor-mode'), '2d', '医生端被串改');
  assert.equal(s.getViewMode('elderly-mode'), '2d');
  assert.equal(localStorage.getItem('viewMode'), null, '不该再碰旧全局键');
});

test('未迁移时回退旧全局键，迁移后按模式归属并删旧键', async () => {
  const s = await loadStores('family-mode', { 'viewMode': '3d' });
  assert.equal(s.getViewMode('family-mode'), '3d', '未迁移时应回退旧键');
  const owner = s.migrateLegacyOnce('family-mode');
  assert.equal(owner, 'family-mode');
  assert.equal(localStorage.getItem('viewMode:family-mode'), '3d');
  assert.equal(localStorage.getItem('viewMode'), null, '旧键必须删除，否则下次又被当权威');
  // 老人端做迁移时不能把 3d 归给自己
  const s2 = await loadStores('elderly-mode', { 'viewMode': '3d' });
  const owner2 = s2.migrateLegacyOnce('elderly-mode');
  assert.equal(owner2, 'family-mode', '老人端不该成为 3d 偏好的归属方');
  assert.equal(s2.prefers3D('elderly-mode'), false);
  assert.equal(s2.getViewMode('family-mode'), '3d');
});

test('非法值与被拒写入都不落盘', async () => {
  const s = await loadStores('family-mode', {});
  assert.equal(s.setViewMode('family-mode', 'nope'), false);
  assert.equal(s.setViewMode('family-mode', null), false);
  assert.equal(s.setViewMode('elderly-mode', '3d'), false);
  assert.equal(localStorage.get?.('viewMode:family-mode'), undefined);
  assert.equal(localStorage.getItem('viewMode:family-mode'), null, '被拒的写入竟然落盘了');
  assert.equal(s.getViewMode('family-mode'), '2d');
});

test('存储键按模式分片，命名可预测', async () => {
  const s = await loadStores('family-mode', {});
  assert.equal(s.viewModeKey('family-mode'), 'viewMode:family-mode');
  assert.equal(s.viewModeKey(undefined), 'viewMode:full');   // 完整模式用占位名，不与旧键撞
});

test('currentMode() 未挂任何模式类时视为完整模式，不默认老人端', async () => {
  const s = await loadStores(null, { 'viewMode': '3d' });
  assert.equal(s.currentMode(), null);
  assert.equal(s.modeSupports3D(s.currentMode()), false, '完整模式不该被当成支持 3D');
  assert.equal(s.prefers3D(), false);
});

test('旁路检查：除 viewModeStore 外不得再有裸的 viewMode 读写', () => {
  const files = [];
  (function walk(d) {
    for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      if (e.name === 'tests' || e.name === 'node_modules') continue;
      const fp = path.join(d, e.name);
      if (e.isDirectory()) walk(fp); else if (/\.(js|mjs)$/.test(e.name)) files.push(fp);
    }
  })(SRC);
  assert.ok(files.length >= 30, '源码文件遍历异常，本断言失去意义: ' + files.length);
  const hits = [];
  for (const f of files) {
    const rel = path.relative(SRC, f).replace(/\\/g, '/');
    if (rel === 'ui/viewModeStore.js') continue;
    const lines = fs.readFileSync(f, 'utf8').split('\n');
    for (let i = 0; i < lines.length; i++) {
      const l = lines[i];
      if (/^\s*(\/\/|\*|\/\*)/.test(l)) continue;          // 注释里提到旧键是说明，不算旁路
      if (/localStorage\.[gs]etItem\(\s*['"]viewMode['"]/.test(l)) hits.push(`${rel}:${i + 1}: ${l.trim()}`);
    }
  }
  assert.equal(hits.length, 0, '发现绕过 viewModeStore 的裸读写:\n  ' + hits.join('\n  '));
});

test('接线检查：四个原读写点都已改走 store', () => {
  const vs = read('3d/view-switcher.js'), main = read('main.js'), eld = read('modes/elderly.js');
  assert.ok(/from '\.\.\/ui\/viewModeStore\.js'/.test(vs) || /from '\.\/ui\/viewModeStore\.js'/.test(vs));
  assert.ok(/prefers3D\(/.test(main), 'main.js 未改用 prefers3D');
  assert.ok(/exit3DMode/.test(eld) && !/setItem\(\s*['"]viewMode['"]/.test(eld.split('\n').filter(l => !/^\s*\/\//.test(l)).join('\n')),
    'elderly.js 仍在写共享 viewMode');
});
