// ============ tier → 家属可读文案（story-9） ============
// 纯映射、零依赖：后端 tier 引擎的结论在这里翻译成不说黑话的话。
// 红线：z-score / 基线 / 小世界系数等术语不出现在家属可见文案里；
// 每一种颜色（含红色）都必须带"可以做的事"，只报忧不给出路是伤害。

export const TIER_META = {
  green:  { tone: 'ok',     title: '本周记录平稳',     advice: '继续保持现在的记录节奏就好。' },
  amber:  { tone: 'warn',   title: '有些变化，值得关注', advice: '接下来两周多陪老人聊聊过去的事，留意变化是否持续。' },
  red:    { tone: 'danger', title: '变化比较明显，建议行动', advice: '建议带老人做一次专业评估——早了解，早安心。' },
  insufficient_data: { tone: 'muted', title: '记录还不够', advice: '多陪爸妈录几天，小结会自动长出来。' },
};

// 信号名 → 生活语言（键与后端 weekly_baseline.SIGNAL_DIRECTIONS 对齐）
export const SIGNAL_LABELS = {
  entity_density: '话里提到的人名、地点变少了',
  avg_sentence_len: '句子变短了',
  audio_duration_sec: '每天说的话变短了',
  audio_speech_ratio: '录音里真正说话的时间变少了',
  audio_words_per_minute: '说话的速度变了',
  node_delta: '这周新出现的记忆人物/地点变少了',
  edge_delta: '这周新连起来的记忆关系变少了',
  anon_ratio: '更多用"那个人""那个地方"来代替具体的名字',
  avg_filler_rate: '语气词、"那个那个"变多了',
  repetition_events: '同样的事反复讲',
  audio_pause_count: '说话中间的停顿变多了',
  anon_delta: '这周"说不清名字"的情况比平时多',
};

export const SEVERITY_LABELS = {
  normal: '平稳',
  warning: '有些变化',
  danger: '明显变化',
  indeterminate: '数据还不够',
};

// 后端 tier_reason / signal.reason 是工程师语言（z_score、基线、σ…），
// 家属端一律不直接渲染——含术语的 reason 清空，只保留生活化的 label。
var JARGON_RE = /z[-\s]?score|基线|标准差|小世界|系数|σ|sigma|n\s*=/i;
function humanize(reason) {
  var s = reason ? String(reason) : '';
  return JARGON_RE.test(s) ? '' : s;
}

/**
 * 把 /decline/analysis 的 tier 字段整理成卡片渲染所需的一切。
 * 未知/缺失 tier 一律按"数据不足"处理——绝不猜一个颜色吓家属。
 */
export function tierDisplay(analysis) {
  var a = analysis || {};
  var tier = a.tier && TIER_META[a.tier] ? a.tier : 'insufficient_data';
  var meta = TIER_META[tier];
  var lines = (a.tier_signals || [])
    .filter(function(s) {
      var sev = s && s.severity ? String(s.severity).toLowerCase() : '';
      return sev === 'warning' || sev === 'danger';
    })
    .map(function(s) {
      var sev = String(s.severity).toLowerCase();
      return {
        name: s.name,
        label: SIGNAL_LABELS[s.name] || s.name,
        severity: sev,
        severityLabel: SEVERITY_LABELS[sev] || '',
        reason: humanize(s.reason),
      };
    });
  var next = a.next_step && typeof a.next_step === 'object' ? a.next_step : null;
  return {
    tier: tier,
    tone: meta.tone,
    title: meta.title,
    advice: (next && next.label) ? humanize(next.label) || next.label : meta.advice,
    reason: humanize(a.tier_reason),
    signals: lines,
    nextStepCode: next ? (next.code || '') : '',
    insufficient: tier === 'insufficient_data',
    validWeeks: a.valid_weeks || 0,
    maxAttainableZ: a.max_attainable_z || 0,
    // 产品定位决策：tier 是"附带的趋势观察"，机制未标定——对外材料必须带这句
    configVersion: a.tier_config_version || '',
    calibrationNote: '趋势观察 · 机制未标定，不构成任何诊断',
  };
}
