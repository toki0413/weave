// W2 词典导入解析验算（node:test，零依赖）
// 钉住两点：中文类型别名可用；识别不了的类型不再被静默改成 item。
// 运行：node --test "src/tests/*.spec.mjs"
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseImportText, normalizeWordType } from '../ui/lexicon-import.js';

test('中文类型别名归一为后端同源枚举', () => {
  assert.equal(normalizeWordType('人名'), 'person');
  assert.equal(normalizeWordType('地点'), 'place');
  assert.equal(normalizeWordType('事件'), 'event');
  assert.equal(normalizeWordType('物品'), 'item');
  assert.equal(normalizeWordType('PERSON'), 'person');
});

test('导入行支持中文类型与全角逗号', () => {
  const items = parseImportText('小明,人名\n社区医院，地点\n跳广场舞,event');
  assert.equal(items.length, 3);
  assert.deepEqual(items[0], { word: '小明', word_type: 'person' });
  assert.deepEqual(items[1], { word: '社区医院', word_type: 'place' });
  assert.deepEqual(items[2], { word: '跳广场舞', word_type: 'event' });
  assert.deepEqual(items.bad, []);
});

test('类型未填时保留默认 item（用户没表达意图，不算错）', () => {
  const items = parseImportText('老花镜');
  assert.deepEqual([...items], [{ word: '老花镜', word_type: 'item' }]);
});

test('识别不了的类型进 bad，绝不静默降级成 item', () => {
  const items = parseImportText('旺财,动物\n老花镜,物品');
  assert.deepEqual([...items], [{ word: '老花镜', word_type: 'item' }],
    '可识别的行要正常导入');
  assert.deepEqual(items.bad, ['旺财,动物'],
    '不可识别的行必须被报出，而不是偷偷按 item 入库');
});

test('空行与空文本不产生条目', () => {
  const items = parseImportText('\n  \n\n');
  assert.equal(items.length, 0);
  assert.deepEqual(items.bad, []);
  assert.equal(parseImportText('').length, 0);
});
