// ============ 公开分享页：本周记忆卡片访客落地 ============
// 免登录渲染；埋点 landing_viewed（匿名），注册引导写 cg_share_ref
// U2 微信分流：落地页微信内可看（只读无碍），但录音须系统浏览器——
// 微信内在注册 CTA 上方显示"用浏览器打开"引导块。
import { el } from './components.js';
import { getSharedCard, trackEventPublic } from '../api/client.js';
import { isWeChatBrowser, copyToClipboard } from '../env.js';

export function isShareRoute() {
  return /^#\/share\/card\/[\w-]+$/.test(location.hash || '');
}

export function shareCardId() {
  var m = (location.hash || '').match(/^#\/share\/card\/([\w-]+)$/);
  return m ? m[1] : null;
}

export function renderSharePage(container) {
  var cardId = shareCardId();
  container.innerHTML = '';
  document.body.className = 'mode-share';

  var wrap = el('div', {
    style: {
      maxWidth: '480px', margin: '40px auto', padding: '24px',
      fontFamily: 'inherit',
    }
  });

  var loading = el('div', { style: { color: 'var(--muted)', textAlign: 'center', padding: '60px 0' } }, '卡片加载中…');
  wrap.appendChild(loading);

  var goRegister = el('a', {
    href: '#/register',
    style: { display: 'none' },
  });
  wrap.appendChild(goRegister);

  getSharedCard(cardId).then(function(res) {
    var p = (res && res.payload) || {};
    loading.remove();

    var card = el('div', {
      style: {
        background: 'var(--bg2, #EDE7DA)',
        borderRadius: '16px',
        padding: '28px 24px',
        boxShadow: '0 4px 24px rgba(0,0,0,0.08)',
      }
    });
    card.appendChild(el('div', {
      style: { fontSize: '0.8rem', color: 'var(--muted, #5C5448)', marginBottom: '4px' }
    }, '织忆 · 认知花园'));
    card.appendChild(el('h1', {
      style: { fontSize: '1.4rem', color: 'var(--ink, #1F1B16)', margin: '0 0 4px' }
    }, (p.elderly_name || '家人') + '的' + (p.week_label || '本周') + '记忆'));
    card.appendChild(el('div', {
      style: { fontSize: '0.85rem', color: 'var(--muted, #5C5448)', marginBottom: '16px' }
    }, '记录是大脑最好的体操'));

    var stats = el('div', { style: { display: 'flex', gap: '10px', flexWrap: 'wrap', marginBottom: '12px' } });
    [['记录', (p.record_count || 0) + ' 次'], ['活跃', (p.active_days || 0) + ' 天'],
     ['字数', String(p.total_chars || 0)], ['状态', p.trend_level || '—']].forEach(function(pair) {
      stats.appendChild(el('div', {
        style: {
          background: 'var(--bg, #F7F4EE)', borderRadius: '10px',
          padding: '8px 14px', textAlign: 'center', flex: '1',
        }
      }, [
        el('div', { style: { fontSize: '1.15rem', fontWeight: '700', color: 'var(--accent, #4A7C4A)' } }, pair[1]),
        el('div', { style: { fontSize: '0.72rem', color: 'var(--muted, #5C5448)' } }, pair[0]),
      ]));
    });
    card.appendChild(stats);

    if (p.top_entities && p.top_entities.length) {
      card.appendChild(el('div', {
        style: { fontSize: '0.85rem', color: 'var(--ink2, #3D362E)', marginBottom: '4px' }
      }, '常提起：' + p.top_entities.map(function(e) { return e.label; }).join('、')));
    }

    wrap.appendChild(card);

    // U2：微信内浏览器引导（放在注册 CTA 上方，录音前置条件讲清楚）
    if (isWeChatBrowser()) {
      var guide = el('div', { style: {
        background: '#FFF8E6', border: '1px solid #E8D9A0',
        borderRadius: '12px', padding: '14px 16px', marginTop: '20px',
      } });
      guide.appendChild(el('div', {
        style: { fontSize: '0.9rem', fontWeight: '700', color: '#6B5B1E', marginBottom: '6px' }
      }, '微信里看卡片没问题，录音要用浏览器'));
      guide.appendChild(el('div', {
        style: { fontSize: '0.85rem', color: '#6B5B1E', lineHeight: '1.7', marginBottom: '10px' }
      }, '点右上角「···」选择「在浏览器打开」，就能正常录音了。也可以先复制链接：'));
      var copyBtn = el('button', {
        style: {
          width: '100%', padding: '10px', fontSize: '0.9rem', cursor: 'pointer',
          border: '1px solid #E8D9A0', borderRadius: '10px',
          background: '#fff', color: '#6B5B1E',
        },
        onclick: function() {
          copyToClipboard(location.href).then(function(ok) {
            copyBtn.textContent = ok ? '已复制 ✓ 去浏览器粘贴打开' : '复制失败，请手动全选地址栏';
          });
        }
      }, '复制链接');
      guide.appendChild(copyBtn);
      wrap.appendChild(guide);
    }

    // 注册引导：记录归因后跳注册
    var cta = el('button', {
      className: 'btn-primary',
      style: {
        width: '100%', marginTop: '20px', padding: '14px',
        fontSize: '1rem', border: 'none', borderRadius: '12px',
        background: 'var(--accent, #4A7C4A)', color: '#fff', cursor: 'pointer',
      },
      onclick: function() {
        try { localStorage.setItem('cg_share_ref', cardId); } catch (e) {}
        location.href = location.origin + location.pathname + '#/register';
        location.reload();
      }
    }, '也给爸妈建一座记忆花园');
    wrap.appendChild(cta);
    wrap.appendChild(el('div', {
      style: { textAlign: 'center', fontSize: '0.75rem', color: 'var(--muted, #5C5448)', marginTop: '10px' }
    }, '每天 60 秒，用故事守护记忆'));

    // 匿名落地埋点（K 因子第一环）
    trackEventPublic('landing_viewed', { card_id: cardId });
  }).catch(function() {
    loading.textContent = '卡片不存在或已失效';
  });

  container.appendChild(wrap);
}
