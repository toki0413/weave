// story-3 连续天数验算（node:test，零依赖）
// 运行：node --test "src/tests/*.spec.mjs"
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { localDateKey, computeStreak, hasTodayRecord } from '../ui/dailyStreak.js';

function shift(days) {
  var d = new Date();
  d.setHours(12, 0, 0, 0);   // 避开夏令时/午夜边界抖动
  d.setDate(d.getDate() + days);
  return localDateKey(d);
}

test('localDateKey 用本地日历日（不是 UTC）', () => {
  var d = new Date(2026, 9, 26, 23, 30, 0);   // 本地 23:30
  assert.equal(localDateKey(d), '2026-10-26');
});

test('今天没记录 → 连续天数为 0（哪怕历史再长）', () => {
  assert.equal(computeStreak([shift(-1), shift(-2), shift(-3)], shift(0)), 0);
});

test('从今天往前数连续段', () => {
  assert.equal(computeStreak([shift(0), shift(-1), shift(-2)], shift(0)), 3);
});

test('断一天归零重计：只有今天 → 1', () => {
  assert.equal(computeStreak([shift(0), shift(-2), shift(-3)], shift(0)), 1);
});

test('乱序与重复日期键不影响结果', () => {
  assert.equal(computeStreak([shift(-1), shift(0), shift(-1), shift(0)], shift(0)), 2);
});

test('hasTodayRecord：今日完成态判定', () => {
  assert.equal(hasTodayRecord([shift(0), shift(-1)], shift(0)), true);
  assert.equal(hasTodayRecord([shift(-1)], shift(0)), false);
});
