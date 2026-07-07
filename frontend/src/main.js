// ============ MAIN ENTRY ============
import './styles.css';
import { init } from './ui/init.js';
import { initI18n } from './i18n.js';
import * as vs from './3d/view-switcher.js';
import * as api from './api/client.js';

// 初始化国际化
initI18n().catch(function() {});

// 初始化字体大小（从 localStorage 读取）
(function initFontSize() {
  var saved = localStorage.getItem('fontSize');
  if (saved) {
    var scale = parseFloat(saved);
    if (!isNaN(scale) && scale > 0) {
      var px = Math.round(scale * 16);
      document.documentElement.style.setProperty('--font-scale', String(scale));
      document.documentElement.style.setProperty('--font-size', px + 'px');
    }
  }
})();

// 初始化 PWA 安装提示
import('./pwa/install-prompt.js').then(function(mod) {
  mod.initPWAInstall();
}).catch(function() {});

// ============ Sentry 错误追踪 ============
try {
  if (import.meta.env && import.meta.env.VITE_SENTRY_DSN) {
    import('@sentry/browser').then(function(Sentry) {
      Sentry.init({
        dsn: import.meta.env.VITE_SENTRY_DSN,
        environment: import.meta.env.MODE || 'production',
        release: 'cognitive-garden@2.1.0',
        integrations: [Sentry.browserTracingIntegration()],
        tracesSampleRate: 0.1,
      });
    }).catch(function() {
      console.warn('Sentry failed to load');
    });
  } else {
    throw new Error('no sentry');
  }
} catch (e) {
  // 备用：捕获全局错误和未处理 Promise 拒绝，上报到自定义端点或控制台
  window.addEventListener('error', function(e) {
    console.error('[Global Error]', e.message, e.filename, e.lineno, e.colno, e.error);
  });
  window.addEventListener('unhandledrejection', function(e) {
    console.error('[Unhandled Promise]', e.reason);
  });
}

// 懒加载非关键模块
var showFatalError = function(title, msg, stack) {
  console.error(title, msg, stack);
};
import('./ui/error-boundary.js').then(function(mod) {
  showFatalError = mod.showFatalError;
});

// Register Service Worker
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js')
      .then(reg => console.log('SW registered'))
      .catch(err => console.log('SW registration failed:', err));
  });
}

(function boot() {
  let initStarted = false;

  function safeInit() {
    if (initStarted) return;
    initStarted = true;
    try {
      var result = init();
      window.__init_called__ = true;

      function fadeSkeleton() {
        var skeleton = document.getElementById('skeleton');
        if (skeleton) {
          skeleton.classList.add('fade-out');
          setTimeout(function() { skeleton.remove(); }, 500);
        }
      }

      if (result && typeof result.then === 'function') {
        result.then(fadeSkeleton).catch(function(e) {
          window.__init_error__ = e.message;
          window.__init_stack__ = e.stack;
          console.error('init error:', e);
          showFatalError('应用启动失败', e.message, e.stack);
        });
      } else {
        fadeSkeleton();
      }

      // 暗黑模式：监听系统偏好
      if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
        if (localStorage.getItem('cg-theme') === null) {
          document.documentElement.setAttribute('data-theme', 'dark');
        }
      }
      window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function(e) {
        if (localStorage.getItem('cg-theme') === null) {
          document.documentElement.setAttribute('data-theme', e.matches ? 'dark' : 'light');
        }
      });

      // 如果 localStorage 保存了 3D 模式，在完整模式（有 canvas-wrap）下自动加载
      if (localStorage.getItem('viewMode') === '3d') {
        import('./state.js').then(function(st) {
          setTimeout(function() {
            var canvasWrap = document.getElementById('canvas-wrap');
            if (canvasWrap && vs.enter3DMode) {
              vs.enter3DMode(
                st.state.nodes || [],
                st.state.sessionHistory || []
              );
            }
          }, 300);
        }).catch(function() {});
      }

      // 角色路由：根据后端用户角色渲染对应视图
      api.getMe().then(function(user) {
        window.current_user = user;
        var role = user && user.role ? user.role : '';
        var app = document.getElementById('app');
        if (!app) return;
        if (role === 'elderly') {
          import('./modes/elderly.js').then(function(mod) {
            mod.renderElderlyMode(app);
          });
        } else if (role === 'family') {
          import('./modes/family.js').then(function(mod) {
            mod.fetchFamilyData().then(function(data) {
              mod.renderFamilyMode(app, data);
            }).catch(function() {
              mod.renderFamilyMode(app, {});
            });
          });
        } else if (role === 'doctor') {
          import('./modes/doctor.js').then(function(mod) {
            mod.renderDoctorMode(app);
          });
        }
        // 未知角色：保留 init() 渲染的完整模式（向后兼容）
      }).catch(function() {
        // 获取用户信息失败，保留完整模式
      });
    } catch (e) {
      window.__init_error__ = e.message;
      window.__init_stack__ = e.stack;
      console.error('init error:', e);
      showFatalError('应用启动失败', e.message, e.stack);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', safeInit);
  } else {
    safeInit();
  }
})();

// ============ 暗黑模式切换 ============
export function toggleDarkMode() {
  var current = document.documentElement.getAttribute('data-theme');
  var next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('cg-theme', next);
}

// 初始化保存的主题
(function initTheme() {
  var saved = localStorage.getItem('cg-theme');
  if (saved) {
    document.documentElement.setAttribute('data-theme', saved);
  }
})();
