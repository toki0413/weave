// story-9 tier 文案映射验算（node:test，零依赖）
// 运行：node --test "src/tests/*.spec.mjs"
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { tierDisplay, SIGNAL_LABELS, TIER_META } from '../ui/tier-copy.js';

const JARGON = /z[-\s]?score|基线|标准差|小世界|系数|匿名节点|n\s*=|sigma|σ/i;

test('三色 + 数据不足的标题都有，且每种颜色自带建议（红线：只报忧不给出路是伤害）', () => {
  for (const t of ['green', 'amber', 'red', 'insufficient_data']) {
    const d = tierDisplay({ tier: t, next_step: null });
    assert.equal(d.tier, t);
    assert.ok(d.title.length > 0);
    assert.ok(d.advice.length > 0, t + ' 必须有 advice');
  }
});

test('家属可见文案不出现统计黑话（标题/建议/信号行全查）', () => {
  const analysis = {
    tier: 'amber',
    tier_reason: '句子长度 z=-2.1，基线 n=11',
    tier_signals: [
      { name: 'avg_sentence_len', severity: 'warning', reason: '偏离基线 -2.1σ' },
      { name: 'anon_ratio', severity: 'danger', reason: 'z-score 超过阈值' },
    ],
    next_step: { code: 'short_interval_rescreen', label: '建议两周后复测观察' },
  };
  const d = tierDisplay(analysis);
  const texts = [d.title, d.advice].concat(d.signals.map(s => s.label + ' ' + s.severityLabel));
  for (const t of texts) assert.ok(!JARGON.test(t), '黑话泄漏: ' + t);
  // reason 含 z-score 时不得进入展示行（后端 reason 是工程师语言）
  assert.ok(!d.signals.some(s => JARGON.test(s.reason || '')), 'reason 黑话泄漏');
});

test('reason 含术语时前端兜底清空该字段（不渲染工程师语言）', () => {
  const d = tierDisplay({
    tier: 'red',
    tier_signals: [{ name: 'audio_pause_count', severity: 'danger', reason: 'z_score=3.2 超阈值' }],
  });
  const s = d.signals[0];
  // 展示用的 label 走映射表，不引用 reason 里的术语
  assert.equal(s.label, SIGNAL_LABELS.audio_pause_count);
  assert.ok(!JARGON.test(s.label));
});

test('未知/缺失 tier 一律按数据不足，绝不猜颜色吓家属', () => {
  assert.equal(tierDisplay({ tier: 'chartreuse' }).tier, 'insufficient_data');
  assert.equal(tierDisplay({}).tier, 'insufficient_data');
  assert.equal(tierDisplay(null).tier, 'insufficient_data');
  assert.equal(tierDisplay(null).insufficient, true);
});

test('信号列表只保留 warning/danger，normal 与 indeterminate 不骚扰', () => {
  const d = tierDisplay({
    tier: 'green',
    tier_signals: [
      { name: 'entity_density', severity: 'normal' },
      { name: 'avg_sentence_len', severity: 'warning' },
      { name: 'anon_ratio', severity: 'indeterminate' },
      { name: 'repetition_events', severity: 'danger' },
    ],
  });
  assert.deepEqual(d.signals.map(s => s.name).sort(), ['avg_sentence_len', 'repetition_events']);
});

test('next_step 有 label 时优先于默认建议；12 个信号键全覆盖映射', () => {
  const d = tierDisplay({ tier: 'red', next_step: { code: 'memory_clinic_within_1_week', label: '建议一周内到记忆门诊评估' } });
  assert.equal(d.advice, '建议一周内到记忆门诊评估');
  assert.equal(d.nextStepCode, 'memory_clinic_within_1_week');
  const keys = Object.keys(SIGNAL_LABELS);
  assert.ok(keys.length >= 12, '信号映射应覆盖 weekly_baseline 的全部 12 个键');
});
