// ============ ONBOARDING 引导教程 ============
import { el } from './components.js';
import { state } from '../state.js';
import { saveState } from './interactions.js';

// 四步引导内容
var STEPS = [
  {
    title: '欢迎使用',
    body: '欢迎使用织忆·认知花园，让我们一起记录每天的回忆',
  },
  {
    title: '语音输入',
    body: '在左侧输入框说出今天发生的事，系统会自动织成记忆网',
  },
  {
    title: '织网操作',
    body: '点击空白添加节点，拖拽移动，选中节点后点击另一节点连线',
  },
  {
    title: '时序网络',
    body: '底部时间轴展示每天的记录，点击可切换查看',
  },
];

// 当前步骤的闭包变量，避免重复挂载时状态错乱
var currentStep = 0;

function renderDots(activeIdx) {
  var wrap = el('div', { className: 'onboarding-dots' });
  for (var i = 0; i < STEPS.length; i++) {
    var cls = i === activeIdx ? 'onboarding-step-dot active' : 'onboarding-step-dot';
    if (i < activeIdx) cls += ' done';
    wrap.appendChild(el('span', { className: cls, 'aria-label': '第' + (i + 1) + '步' }));
  }
  return wrap;
}

// 渲染单步卡片内容
function renderStep(idx) {
  var s = STEPS[idx];
  var isLast = idx === STEPS.length - 1;

  var card = el('div', { className: 'onboarding-card', role: 'dialog', 'aria-modal': 'true' });

  card.appendChild(el('div', { className: 'onboarding-step-tag' }, '第 ' + (idx + 1) + ' / ' + STEPS.length + ' 步'));
  card.appendChild(el('h2', { className: 'onboarding-title' }, s.title));
  card.appendChild(el('p', { className: 'onboarding-body' }, s.body));
  card.appendChild(renderDots(idx));

  var actions = el('div', { className: 'onboarding-actions' });
  actions.appendChild(el('button', {
    className: 'onboarding-btn onboarding-btn-skip',
    onclick: function() { finishOnboarding(); },
  }, '跳过'));

  var primaryLabel = isLast ? '开始使用' : '下一步';
  actions.appendChild(el('button', {
    className: 'onboarding-btn onboarding-btn-primary',
    onclick: function() {
      if (isLast) {
        finishOnboarding();
      } else {
        currentStep = idx + 1;
        rerender();
      }
    },
  }, primaryLabel));
  card.appendChild(actions);

  return card;
}

// 重新渲染当前步骤（替换卡片内容，不重建遮罩）
function rerender() {
  var overlay = document.getElementById('onboarding-overlay');
  if (!overlay) return;
  var oldCard = overlay.querySelector('.onboarding-card');
  var newCard = renderStep(currentStep);
  if (oldCard) {
    overlay.replaceChild(newCard, oldCard);
  } else {
    overlay.appendChild(newCard);
  }
}

// 完成引导：写状态、持久化、移除遮罩
function finishOnboarding() {
  state.welcomeDismissed = true;
  saveState();
  var overlay = document.getElementById('onboarding-overlay');
  if (overlay && overlay.parentNode) {
    overlay.parentNode.removeChild(overlay);
  }
  currentStep = 0;
}

// 对外入口：挂载引导覆盖层
function showOnboarding() {
  // 已经存在就不重复挂
  if (document.getElementById('onboarding-overlay')) return;
  currentStep = 0;
  var overlay = el('div', {
    className: 'onboarding-overlay',
    id: 'onboarding-overlay',
  });
  overlay.appendChild(renderStep(currentStep));
  document.body.appendChild(overlay);
}

export { showOnboarding };
