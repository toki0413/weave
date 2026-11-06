// 产品命名守卫：全网用户可见位置只允许「织忆」（英文语境用 Weave），
// 不允许再出现旧副名「认知花园」。内部标识（CG_ 前缀、cg-* 容器名、
// cognitive_garden 库名、~/.cognitive-garden 数据目录）不在此约束内。
//
// 运行：node --test frontend/src/tests/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const SRC = path.resolve(import.meta.dirname, '..');
const read = (p) => fs.readFileSync(path.join(SRC, p), 'utf8');

const DEPRECATED = '认知花园';

test('顶栏只显示产品名「织忆」，无副标题', () => {
  const header = read('ui/panels/header.js');
  assert.match(header, /header-title' \}, '织忆'\)/);
  assert.ok(!header.includes('header-sub'), '副标题元素应已移除');
});

test('入口页标题为「织忆」', () => {
  const html = read('index.html');
  assert.match(html, /<title>织忆<\/title>/);
});

test('PWA manifest 名称为「织忆」', () => {
  const manifest = JSON.parse(read('manifest.json'));
  assert.equal(manifest.name, '织忆');
  assert.equal(manifest.short_name, '织忆');
});

test('中文语言包标题为「织忆」，英文语境界定为 Weave', () => {
  const zh = JSON.parse(read('locales/zh.json'));
  const en = JSON.parse(read('locales/en.json'));
  assert.equal(zh.app.title, '织忆');
  assert.equal(en.app.title, 'Weave');
});

test('启动页、安装提示、引导与分享页均不出现旧副名', () => {
  const files = [
    '../public/loading.html',
    'pwa/install-prompt.js',
    'ui/onboarding.js',
    'ui/share-page.js',
    'locales/zh.json',
    'locales/en.json',
  ];
  for (const f of files) {
    const text = read(f);
    assert.ok(!text.includes(DEPRECATED), `${f} 仍含旧副名`);
  }
});

test('用户可见文案中不再出现「认知花园」', () => {
  const offenders = [];
  const walk = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === 'node_modules' || entry.name === 'tests') continue;
        walk(full);
        continue;
      }
      if (!/\.(js|json|html|css|md)$/.test(entry.name)) continue;
      const text = fs.readFileSync(full, 'utf8');
      if (text.includes(DEPRECATED)) offenders.push(path.relative(SRC, full));
    }
  };
  walk(SRC);
  assert.deepEqual(offenders, [], `以下文件仍含旧副名：${offenders.join(', ')}`);
});
