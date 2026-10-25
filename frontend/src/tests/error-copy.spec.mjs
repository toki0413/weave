// story-10 错误文案归一化验算（node:test，零依赖）
// 运行：node --test "src/tests/*.spec.mjs"
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { normalizeErrorDetail } from '../api/error-copy.js';

test('FastAPI 422 数组 detail 不再显示成 [object Object]', () => {
  const detail = [
    { loc: ['body', 'day_number'], msg: 'value is not a valid integer', type: 'type_error.integer' },
    { loc: ['body', 'narrative_input'], msg: 'field required', type: 'value_error.missing' },
  ];
  const out = normalizeErrorDetail(detail, 422);
  assert.ok(out.startsWith('提交的信息有误：'));
  assert.ok(out.includes('value is not a valid integer'));
  assert.ok(out.includes('；'));
  assert.ok(!out.includes('[object Object]'));
});

test('已知英文 detail 映射为中文', () => {
  assert.equal(normalizeErrorDetail('Could not validate credentials', 401), '登录状态已失效，请重新登录');
  assert.equal(normalizeErrorDetail('Invalid credentials', 401), '手机号或密码不正确');
});

test('空 detail 给出状态码相关的人话兜底', () => {
  assert.equal(normalizeErrorDetail(null, 401), '请先登录');
  assert.equal(normalizeErrorDetail('', 500), '请求失败（500），请稍后再试');
});

test('已是中文的 detail 原样透传（后端是人话就不再加工）', () => {
  assert.equal(normalizeErrorDetail('没听清，请再试一次；多次不行请稍后再试', 503),
               '没听清，请再试一次；多次不行请稍后再试');
});
