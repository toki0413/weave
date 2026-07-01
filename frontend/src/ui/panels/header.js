// ============ HEADER PANEL ============
// 顶部栏：标题、视图切换、字号调节、天数徽标、通知铃铛
import { state, SCENARIOS } from '../../state.js';
import { el } from '../components.js';
import { render } from '../render.js';
import { createNotificationBell, refreshNotifications, destroyNotificationBell } from '../notifications.js';

import { renderViewSwitcher, getViewMode, setViewMode } from '../../3d/view-switcher.js';

// 切换视图（老人端 / 家属端 / 医生端）
function switchView(view) {
  state.view = view;
  document.documentElement.classList.remove('elderly-mode', 'family-mode', 'doctor-mode');
  document.documentElement.classList.add(view + '-mode');
  document.body.className = 'mode-' + view;
  // 切换到 elderly 时强制 2D 模式
  if (view === 'elderly') {
    localStorage.setItem('viewMode', '2d');
    import('../../3d/view-switcher.js').then(function(vs) { vs.exit3DMode(); }).catch(function() {});
  }
  render();
}

// 调整全局字号缩放
function setFontScale(s) {
  state.fontScale = s;
  var px = Math.round(s * 16);
  document.documentElement.style.setProperty('--font-scale', String(s));
  document.documentElement.style.setProperty('--font-size', px + 'px');
  localStorage.setItem('fontSize', String(s));
  render();
}

function renderHeader() {
  var header = el('div', { className: 'header' });
  var left = el('div', { className: 'header-left' });
  left.appendChild(el('div', { className: 'header-logo' }, '🌿'));
  left.appendChild(el('span', { className: 'header-title' }, '织忆'));
  left.appendChild(el('span', { className: 'header-sub' }, '认知花园'));
  header.appendChild(left);

  var right = el('div', { className: 'header-right' });

  var switcher = el('div', { className: 'view-switcher', role: 'tablist', 'aria-label': '视图切换' });
  ['elderly', 'family', 'doctor'].forEach(function(v) {
    var labels = { elderly: '老人端', family: '家属端', doctor: '医生端' };
    var btn = el('button', {
      className: 'view-btn' + (state.view === v ? ' active' : ''),
      role: 'tab',
      'aria-selected': state.view === v ? 'true' : 'false',
      'aria-label': '切换到' + labels[v],
      onclick: function() { switchView(v); }
    }, labels[v]);
    switcher.appendChild(btn);
  });
  right.appendChild(switcher);

  var fsWrap = el('div', { className: 'font-scale-wrap', role: 'group', 'aria-label': '字体大小' });
  var fsLabel = el('label', { className: 'font-scale-label', htmlFor: 'font-scale-slider' }, 'A');
  fsWrap.appendChild(fsLabel);
  var slider = el('input', {
    type: 'range',
    id: 'font-scale-slider',
    className: 'font-scale-slider',
    min: '12',
    max: '24',
    value: String(Math.round(state.fontScale * 16)),
    step: '1',
    'aria-label': '字体大小滑块',
    oninput: function() {
      var px = parseInt(this.value, 10);
      var scale = px / 16;
      setFontScale(scale);
      fsLabel.textContent = 'A';
    }
  });
  fsWrap.appendChild(slider);
  right.appendChild(fsWrap);

  // 2D/3D 切换（老人端不显示，家属端和医生端显示）
  if (state.view !== 'elderly') {
    renderViewSwitcher(right);
  }

  // 家属端显示通知铃铛
  if (state.view === 'family') {
    right.appendChild(createNotificationBell());
  } else {
    // 切到其他视图时清理铃铛的轮询定时器
    destroyNotificationBell();
  }

  right.appendChild(el('div', { className: 'day-badge' },
    '第' + (state.currentDay + 1) + '天 · ' + SCENARIOS[state.currentDay].label));
  header.appendChild(right);
  return header;
}

export { renderHeader, switchView, setFontScale };
