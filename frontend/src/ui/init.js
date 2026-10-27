// ============ INIT ============
import { state } from '../state.js';
import { render } from './render.js';
import { loadState, handleGlobalKey } from './interactions.js';
import { getSelfNode } from '../graph/model.js';
import { getSttHealth } from '../api/client.js';
import { showOfflineToast, clearOfflineToast } from './toast.js';
import { initOfflineBanner } from './offline-banner.js';
import { applyMode, recallRole } from './mode.js';

function init() {
  // 模式类名只经 mode.js 写入。
  // 旧实现在这里无条件 add('elderly-mode')，而 main.js 的 api.getMe() 是异步的：
  //   1) 骨架屏到 getMe 返回这段时间里，家属/医生也在老人端高对比主题中；
  //   2) 更严重的是 getMe 失败 / 未知角色这条兜底路径（main.js 注释写"保留完整模式"）
  //      从未真正回到完整模式 —— 它停在了 elderly-mode 里。
  // 无缓存角色时不加任何模式类，即真正的完整模式。
  applyMode(recallRole());

  // 字号：只写倍率 --font-scale，像素基准交回 CSS。
  // 旧实现在这里写内联 --font-size / font-size，内联样式特异度高于样式表，
  // 把 styles.css 的 html.elderly-mode{font-size:calc(20px*var(--font-scale))}
  // 整个压掉，导致老人端 root 实际一直是 16px（不是设计意图的 20px）。
  var scale = parseFloat(localStorage.getItem('fontSize'));
  var safe = (!isNaN(scale) && scale > 0) ? scale : 1;
  document.documentElement.style.setProperty('--font-scale', String(safe));
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
