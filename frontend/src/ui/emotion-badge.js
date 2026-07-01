// ============ EMOTION BADGE ============
// 情绪标签组件：显示积极/中性/消极，带颜色与悬停提示

import { el } from './components.js';

var EMOTION_META = {
  positive: { icon: '😊', label: '积极', color: '#4A7C4A', bg: '#E8F5E9' },
  neutral:  { icon: '😐', label: '中性', color: '#837A6E', bg: '#F5F5F5' },
  negative: { icon: '😟', label: '消极', color: '#C0392B', bg: '#FFEBEE' },
};

export function renderEmotionBadge(container, emotion) {
  if (!container) return;
  container.innerHTML = '';

  if (!emotion || !emotion.overall) {
    container.appendChild(el('div', {
      style: { fontSize: '0.75rem', color: 'var(--muted)' }
    }, '暂无情绪数据'));
    return;
  }

  var meta = EMOTION_META[emotion.overall] || EMOTION_META.neutral;
  var words = emotion.words || { positive: [], negative: [] };

  // 构建悬停提示内容
  var tooltipLines = [];
  if (words.positive && words.positive.length > 0) {
    tooltipLines.push('积极词：' + words.positive.join('、'));
  }
  if (words.negative && words.negative.length > 0) {
    tooltipLines.push('消极词：' + words.negative.join('、'));
  }
  if (tooltipLines.length === 0) {
    tooltipLines.push('未检测到情绪关键词');
  }
  tooltipLines.push('分数：' + (emotion.score !== undefined ? emotion.score : '—'));

  var badge = el('div', {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: '4px',
      padding: '4px 10px',
      borderRadius: '100px',
      background: meta.bg,
      color: meta.color,
      fontSize: '0.8rem',
      fontWeight: '600',
      cursor: 'help',
      position: 'relative',
    },
    title: tooltipLines.join('\n'),
  }, [
    el('span', {}, meta.icon),
    el('span', {}, meta.label),
  ]);

  container.appendChild(badge);
}

export function getEmotionFromSession(session) {
  /* 从 session 对象提取 emotion 结构 */
  if (!session) return null;
  if (session.emotion) return session.emotion;
  if (session.emotion_label) {
    return {
      overall: session.emotion_label,
      score: session.emotion_score !== undefined ? session.emotion_score : 0,
      words: { positive: [], negative: [] },
    };
  }
  return null;
}
