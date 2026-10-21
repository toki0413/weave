// ============ 公开分享页：本周记忆卡片访客落地 ============
// 免登录渲染；埋点 landing_viewed（匿名），注册引导写 cg_share_ref
import { el } from './components.js';
import { getSharedCard, trackEventPublic } from '../api/client.js';

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
