// ============ OFFLINE BANNER ============
// 监听网络状态并显示离线/恢复提示

function initOfflineBanner() {
  var banner = createBanner();
  document.body.appendChild(banner);

  function updateBanner() {
    if (!navigator.onLine) {
      banner.style.display = 'flex';
      banner.style.background = '#F5EDD5';
      banner.style.color = '#8B6914';
      banner.querySelector('.offline-banner-icon').textContent = '⚠️';
      banner.querySelector('.offline-banner-text').textContent =
        '离线模式，数据将在恢复网络后自动同步';
    } else {
      banner.style.display = 'flex';
      banner.style.background = '#DDE9DD';
      banner.style.color = '#2D5A2C';
      banner.querySelector('.offline-banner-icon').textContent = '✅';
      banner.querySelector('.offline-banner-text').textContent =
        '网络已恢复，正在同步…';
      setTimeout(function() {
        banner.style.display = 'none';
      }, 2000);
    }
  }

  window.addEventListener('offline', updateBanner);
  window.addEventListener('online', updateBanner);

  if (!navigator.onLine) {
    updateBanner();
  }
}

function createBanner() {
  var banner = document.createElement('div');
  banner.className = 'offline-banner';
  banner.style.cssText = [
    'position:fixed', 'top:0', 'left:0', 'right:0',
    'background:#F5EDD5', 'color:#8B6914', 'padding:10px 20px',
    'display:none', 'align-items:center', 'justify-content:center',
    'gap:8px', 'z-index:99999', 'font-size:0.9rem', 'font-weight:600',
    'box-shadow:0 2px 10px rgba(0,0,0,0.08)', 'transition:background 0.3s'
  ].join(';');

  var icon = document.createElement('span');
  icon.className = 'offline-banner-icon';
  icon.textContent = '⚠️';
  icon.style.fontSize = '1rem';

  var text = document.createElement('span');
  text.className = 'offline-banner-text';

  banner.appendChild(icon);
  banner.appendChild(text);
  return banner;
}

export { initOfflineBanner };
