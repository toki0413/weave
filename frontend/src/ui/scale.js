// ============ 认知量表 UI ============
import { el } from './components.js';
import { listScales, getScaleDetail, submitScale } from '../api/client.js';
import { trapFocus } from './interactions.js';

// 当前量表会话状态
var session = {
  overlay: null,
  scale: null,        // 量表详情
  questions: [],      // 题目列表
  currentIdx: 0,      // 当前题号
  answers: [],        // 已答题目 [{ question_id, score }]
  _savedFocus: null,
  _restoreFocus: null,
};

// 打开量表面板（入口）
export function openScalePanel() {
  closeScalePanel();
  session._savedFocus = document.activeElement;
  var overlay = el('div', {
    className: 'scale-overlay',
    id: 'scale-overlay',
    role: 'dialog',
    'aria-modal': 'true',
    'aria-label': '认知量表评估',
  });
  document.body.appendChild(overlay);
  session.overlay = overlay;
  renderScaleList();
  session._restoreFocus = trapFocus(overlay, session._savedFocus);
}

// 关闭量表面板
export function closeScalePanel() {
  if (session.overlay && session.overlay.parentNode) {
    session.overlay.parentNode.removeChild(session.overlay);
  }
  if (session._restoreFocus) {
    session._restoreFocus();
    session._restoreFocus = null;
  }
  session.overlay = null;
  session.scale = null;
  session.questions = [];
  session.currentIdx = 0;
  session.answers = [];
}

// 渲染量表选择页
function renderScaleList() {
  var container = el('div', { className: 'scale-modal' });
  container.appendChild(el('div', { className: 'scale-modal-header' }, [
    el('h2', { className: 'scale-modal-title' }, '认知量表评估'),
    el('button', {
      className: 'scale-close-btn',
      'aria-label': '关闭',
      onclick: closeScalePanel,
    }, '✕'),
  ]));

  var body = el('div', { className: 'scale-modal-body' });
  body.appendChild(el('p', { className: 'scale-modal-desc' },
    '选择量表开始认知功能筛查。量表建议每季度评估一次，频繁测试会影响结果准确性。'));

  var grid = el('div', { className: 'scale-card-grid' });

  // 占位卡片，等接口返回后填充
  grid.appendChild(el('div', { className: 'scale-loading' }, '正在加载量表…'));
  body.appendChild(grid);
  container.appendChild(body);
  session.overlay.innerHTML = '';
  session.overlay.appendChild(container);

  listScales().then(function(scales) {
    grid.innerHTML = '';
    scales.forEach(function(s) {
      grid.appendChild(buildScaleCard(s));
    });
  }).catch(function(err) {
    grid.innerHTML = '';
    grid.appendChild(el('div', { className: 'scale-error' },
      '加载失败：' + (err.offline ? '无法连接服务器，请检查网络' : err.message)));
  });
}

// 构建量表选择卡片
function buildScaleCard(scale) {
  var card = el('div', {
    className: 'scale-card',
    role: 'button',
    tabindex: '0',
    onclick: function() { startScale(scale.id); },
    onkeydown: function(e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); startScale(scale.id); }
    },
  }, [
    el('div', { className: 'scale-card-name' }, scale.name),
    el('div', { className: 'scale-card-desc' }, scale.description),
    el('div', { className: 'scale-card-meta' }, [
      el('span', {}, '共 ' + scale.question_count + ' 题'),
      el('span', {}, '满分 ' + scale.total_score + ' 分'),
      el('span', {}, '约 ' + scale.duration_min + ' 分钟'),
    ]),
  ]);

  // 频率说明
  if (scale.recommended_frequency) {
    card.appendChild(el('div', { className: 'scale-card-frequency' }, [
      el('span', { className: 'scale-card-freq-label' }, '建议频率'),
      el('span', {}, scale.recommended_frequency),
    ]));
  }
  if (scale.who_fills) {
    card.appendChild(el('div', { className: 'scale-card-who' }, scale.who_fills));
  }

  card.appendChild(el('div', { className: 'scale-card-btn' }, '开始评估 →'));
  return card;
}

// 开始某个量表的答题流程
function startScale(scaleId) {
  var container = el('div', { className: 'scale-modal' });
  container.appendChild(el('div', { className: 'scale-modal-header' }, [
    el('button', {
      className: 'scale-back-btn',
      onclick: renderScaleList,
    }, '← 返回'),
    el('h2', { className: 'scale-modal-title' }, '加载中…'),
    el('button', {
      className: 'scale-close-btn',
      'aria-label': '关闭',
      onclick: closeScalePanel,
    }, '✕'),
  ]));
  var body = el('div', { className: 'scale-modal-body' });
  body.appendChild(el('div', { className: 'scale-loading' }, '正在加载题目…'));
  container.appendChild(body);
  session.overlay.innerHTML = '';
  session.overlay.appendChild(container);

  getScaleDetail(scaleId).then(function(scale) {
    session.scale = scale;
    session.questions = scale.questions;
    session.currentIdx = 0;
    session.answers = [];
    renderQuestion();
  }).catch(function(err) {
    body.innerHTML = '';
    body.appendChild(el('div', { className: 'scale-error' },
      '加载失败：' + (err.offline ? '无法连接服务器' : err.message)));
  });
}

// 渲染当前题目
function renderQuestion() {
  var scale = session.scale;
  var idx = session.currentIdx;
  var q = session.questions[idx];
  var total = session.questions.length;
  var progress = Math.round((idx / total) * 100);

  var container = el('div', { className: 'scale-modal' });
  container.appendChild(el('div', { className: 'scale-modal-header' }, [
    el('button', {
      className: 'scale-back-btn',
      onclick: function() {
        if (idx > 0) {
          session.currentIdx--;
          session.answers.pop();
          renderQuestion();
        } else {
          renderScaleList();
        }
      },
    }, '← ' + (idx > 0 ? '上一题' : '返回')),
    el('h2', { className: 'scale-modal-title' }, scale.name),
    el('button', {
      className: 'scale-close-btn',
      'aria-label': '关闭',
      onclick: closeScalePanel,
    }, '✕'),
  ]));

  var body = el('div', { className: 'scale-modal-body' });

  // 进度条
  body.appendChild(el('div', { className: 'scale-progress-wrap' }, [
    el('div', { className: 'scale-progress-bar' }, [
      el('div', { className: 'scale-progress-fill', style: { width: progress + '%' } }),
    ]),
    el('div', { className: 'scale-progress-text' },
      '第 ' + (idx + 1) + ' / ' + total + ' 题'),
  ]));

  // 维度标签
  body.appendChild(el('div', { className: 'scale-dimension-tag' }, q.dimension));

  // 题目文本
  body.appendChild(el('div', { className: 'scale-question-text' }, q.text));

  // 选项列表
  var optionsWrap = el('div', { className: 'scale-options' });
  q.options.forEach(function(opt) {
    var isSelected = session.answers[idx] && session.answers[idx].score === opt.score;
    optionsWrap.appendChild(el('div', {
      className: 'scale-option' + (isSelected ? ' selected' : ''),
      role: 'button',
      tabindex: '0',
      onclick: function() { selectAnswer(opt.score); },
      onkeydown: function(e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); selectAnswer(opt.score); }
      },
    }, [
      el('div', { className: 'scale-option-score' }, String(opt.score) + '分'),
      el('div', { className: 'scale-option-label' }, opt.label),
    ]));
  });
  body.appendChild(optionsWrap);

  container.appendChild(body);
  session.overlay.innerHTML = '';
  session.overlay.appendChild(container);
}

// 选择答案后进入下一题或提交
function selectAnswer(score) {
  var idx = session.currentIdx;
  var q = session.questions[idx];

  // 记录或更新答案
  session.answers[idx] = { question_id: q.id, score: score };

  if (idx < session.questions.length - 1) {
    session.currentIdx++;
    renderQuestion();
  } else {
    submitAnswers();
  }
}

// 提交所有答案
function submitAnswers() {
  var scale = session.scale;
  var container = el('div', { className: 'scale-modal' });
  container.appendChild(el('div', { className: 'scale-modal-header' }, [
    el('h2', { className: 'scale-modal-title' }, scale.name),
    el('button', {
      className: 'scale-close-btn',
      'aria-label': '关闭',
      onclick: closeScalePanel,
    }, '✕'),
  ]));
  var body = el('div', { className: 'scale-modal-body' });
  body.appendChild(el('div', { className: 'scale-loading' }, '正在提交答卷…'));
  container.appendChild(body);
  session.overlay.innerHTML = '';
  session.overlay.appendChild(container);

  submitScale(scale.id, session.answers).then(function(result) {
    renderResult(result);
  }).catch(function(err) {
    body.innerHTML = '';
    body.appendChild(el('div', { className: 'scale-error' },
      '提交失败：' + (err.offline ? '无法连接服务器' : err.message)));
    body.appendChild(el('button', {
      className: 'btn-secondary',
      style: { marginTop: '16px' },
      onclick: renderQuestion,
    }, '返回修改'));
  });
}

// 渲染评估结果
function renderResult(result) {
  var scale = session.scale;
  var level = result.interpretation;
  // 根据解读等级判断颜色
  var statusClass = 'ok';
  if (level.indexOf('重度') >= 0 || level.indexOf('需进一步') >= 0) {
    statusClass = 'danger';
  } else if (level.indexOf('中度') >= 0 || level.indexOf('轻度') >= 0) {
    statusClass = 'warn';
  }

  var container = el('div', { className: 'scale-modal' });
  container.appendChild(el('div', { className: 'scale-modal-header' }, [
    el('h2', { className: 'scale-modal-title' }, '评估结果'),
    el('button', {
      className: 'scale-close-btn',
      'aria-label': '关闭',
      onclick: closeScalePanel,
    }, '✕'),
  ]));

  var body = el('div', { className: 'scale-modal-body' });

  // 分数展示
  body.appendChild(el('div', { className: 'scale-result-score ' + statusClass }, [
    el('div', { className: 'scale-result-num' }, String(result.total_score)),
    el('div', { className: 'scale-result-total' }, '/ ' + scale.total_score + ' 分'),
  ]));

  // 解读等级
  body.appendChild(el('div', { className: 'scale-result-level ' + statusClass }, level));

  // 详细说明
  body.appendChild(el('div', { className: 'scale-result-detail' }, result.detail));

  // 量表名称
  body.appendChild(el('div', { className: 'scale-result-scale-name' }, scale.name));

  // 操作按钮
  body.appendChild(el('div', { className: 'scale-result-actions' }, [
    el('button', {
      className: 'btn-secondary',
      onclick: renderScaleList,
    }, '再做一次评估'),
    el('button', {
      className: 'btn-primary',
      onclick: closeScalePanel,
    }, '完成'),
  ]));

  container.appendChild(body);
  session.overlay.innerHTML = '';
  session.overlay.appendChild(container);
}
