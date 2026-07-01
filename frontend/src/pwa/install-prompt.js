// ============ PWA INSTALL PROMPT ============
// 拦截 beforeinstallprompt 并提供自定义安装横幅

function initPWAInstall() {
  // 保存浏览器原生的安装提示事件
  window.addEventListener('beforeinstallprompt', function(e) {
    e.preventDefault();
    window.__deferredPrompt__ = e;
    showInstallBanner();
  });

  // 已安装后隐藏横幅
  window.addEventListener('appinstalled', function() {
    hideInstallBanner();
    window.__deferredPrompt__ = null;
  });

  // 如果已经作为 PWA 运行（standalone 或 fullscreen），不显示
  if (isStandalone()) {
    return;
  }

  // 延迟检查：如果已安装（通过 getInstalledRelatedApps）也隐藏
  if ('getInstalledRelatedApps' in navigator) {
    navigator.getInstalledRelatedApps().then(function(apps) {
      if (apps && apps.length > 0) {
        hideInstallBanner();
      }
    }).catch(function() {});
  }
}

function isStandalone() {
  return (
    window.matchMedia('(display-mode: standalone)').matches ||
    window.matchMedia('(display-mode: fullscreen)').matches ||
    window.matchMedia('(display-mode: minimal-ui)').matches ||
    navigator.standalone === true
  );
}

function showInstallBanner() {
  if (document.getElementById('pwa-install-banner')) return;

  var banner = document.createElement('div');
  banner.id = 'pwa-install-banner';
  banner.style.cssText = [
    'position:fixed', 'bottom:0', 'left:0', 'right:0',
    'background:#5C8D5A', 'color:#fff', 'padding:14px 20px',
    'display:flex', 'align-items:center', 'justify-content:space-between',
    'gap:12px', 'z-index:9999', 'box-shadow:0 -4px 20px rgba(0,0,0,0.15)',
    'font-size:0.95rem', 'transition:transform 0.3s ease',
    'transform:translateY(0)'
  ].join(';');

  var text = document.createElement('span');
  text.textContent = '将「织忆·认知花园」添加到桌面，离线也能使用';
  text.style.flex = '1';
  text.style.lineHeight = '1.4';

  var btn = document.createElement('button');
  btn.textContent = '添加到桌面';
  btn.style.cssText = [
    'background:#fff', 'color:#5C8D5A', 'border:none',
    'border-radius:8px', 'padding:8px 16px', 'font-weight:700',
    'font-size:0.9rem', 'cursor:pointer', 'flex-shrink:0',
    'font-family:inherit', 'transition:transform 0.1s'
  ].join(';');
  btn.onmouseenter = function() { btn.style.transform = 'translateY(-1px)'; };
  btn.onmouseleave = function() { btn.style.transform = 'translateY(0)'; };
  btn.onclick = function() {
    if (!window.__deferredPrompt__) {
      hideInstallBanner();
      return;
    }
    window.__deferredPrompt__.prompt();
    window.__deferredPrompt__.userChoice.then(function(choice) {
      if (choice && choice.outcome === 'accepted') {
        console.log('[PWA] User accepted install');
      } else {
        console.log('[PWA] User dismissed install');
      }
      window.__deferredPrompt__ = null;
      hideInstallBanner();
    }).catch(function() {
      window.__deferredPrompt__ = null;
      hideInstallBanner();
    });
  };

  var close = document.createElement('button');
  close.textContent = '✕';
  close.style.cssText = [
    'background:transparent', 'border:none', 'color:#fff',
    'font-size:1.1rem', 'cursor:pointer', 'padding:4px 8px',
    'opacity:0.8', 'flex-shrink:0'
  ].join(';');
  close.onclick = function() { hideInstallBanner(); };

  banner.appendChild(text);
  banner.appendChild(btn);
  banner.appendChild(close);
  document.body.appendChild(banner);
}

function hideInstallBanner() {
  var banner = document.getElementById('pwa-install-banner');
  if (!banner) return;
  banner.style.transform = 'translateY(100%)';
  setTimeout(function() {
    if (banner && banner.parentNode) banner.remove();
  }, 300);
}

export { initPWAInstall };
