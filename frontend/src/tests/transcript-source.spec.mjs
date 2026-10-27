// story-7 转写来源决策表的验算（node:test，零依赖）
// 运行：node --test frontend/src/tests/  或  node frontend/src/tests/transcript-source.spec.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { planRecording } from '../audio/transcript-source.js';

test('Chrome/Edge（SR+MediaRecorder 都有）→ dual：SR 仅预览，音频走后端链', () => {
  assert.equal(planRecording(true, true), 'dual');
});

test('Firefox 等（仅 MediaRecorder）→ recorder：无预览但音频照走后端链', () => {
  assert.equal(planRecording(false, true), 'recorder');
});

test('SR-only（录不了音频）→ manual：诚实降级，绝不伪装成识别成功入库', () => {
  assert.equal(planRecording(true, false), 'manual');
});

test('全不支持 → manual：给出打字路径而非死按钮', () => {
  assert.equal(planRecording(false, false), 'manual');
});
