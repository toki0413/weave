// ============ INIT ============
import { state } from '../state.js';
import { render } from './render.js';
import { loadState, handleGlobalKey } from './interactions.js';
import { getSelfNode } from '../graph/model.js';
import { getSttHealth } from '../api/client.js';
import { showOfflineToast, clearOfflineToast } from './toast.js';
import { initOfflineBanner } from './offline-banner.js';

function init() {
  document.documentElement.classList.add('elderly-mode');
  document.body.classList.add('mode-elderly');
  var savedScale = localStorage.getItem('fontSize');
  if (savedScale) {
    var scale = parseFloat(savedScale);
    if (!isNaN(scale) && scale > 0) {
      document.documentElement.style.setProperty('--font-scale', String(scale));
      document.documentElement.style.setProperty('--font-size', Math.round(scale * 16) + 'px');
    } else {
      document.documentElement.style.setProperty('--font-scale', '1');
      document.documentElement.style.setProperty('--font-size', '16px');
    }
  } else {
    document.documentElement.style.setProperty('--font-scale', '1');
    document.documentElement.style.setProperty('--font-size', '16px');
  }
  loadState();
  getSelfNode();

  // 更新骨架屏提示
  var skeletonText = document.getElementById('skeleton-text');
  if (skeletonText) skeletonText.textContent = '正在编织记忆网络…';

  document.addEventListener('keydown', handleGlobalKey);

  // 初始化离线横幅
  initOfflineBanner();

  // 动态加载 graph 模块，实现按需加载
  return import('../graph/layout.js').then(function(graph) {
    window.__graphApis = graph;
    render();
    graph.startAnimation();
    window.addEventListener('resize', graph.onWindowResize);

    // 启动时检测 STT 服务可用性，失败后前端显式降级为手动输入
    getSttHealth()
      .then(function(d) {
        state.sttAvailable = !!d.available;
        render();
      })
      .catch(function() {
        state.sttAvailable = false;
        render();
      });

    // 启动时检查网络状态，离线显示提示
    if (!navigator.onLine) {
      showOfflineToast('离线模式，数据将在恢复网络后同步');
    }
    window.addEventListener('online', function() {
      clearOfflineToast();
    });
    window.addEventListener('offline', function() {
      showOfflineToast('离线模式，数据将在恢复网络后同步');
    });
  });
}

export { init };
