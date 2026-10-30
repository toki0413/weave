// ============ FAMILY MODE (3D Nebula Immersive) ============
// 家属端：默认 3D 星云浏览，飞行漫游，时间筛选，情感色彩
import { el } from '../ui/components.js';
import { listSessions, getHealthTrend, getNotifications, getLatestGraph, sendWebSocketCare, generateMemoryCard, getLatestMemoryCard, trackEvent, getFamilyMembers, linkFamilyMember, invalidateCache } from '../api/client.js';
import { connect as wsConnect, send as wsSend, isConnected, isUsingSSE } from '../services/websocket.js';
import { getToken } from '../api/client.js';

export function renderFamilyMode(container, elderlyData) {
  container.innerHTML = '';
  document.documentElement.classList.remove('elderly-mode', 'doctor-mode');
  document.documentElement.classList.add('family-mode');
  document.body.className = 'mode-family';

  var data = elderlyData || {};
  // story-11：无数据不再回落假分数 85——null 走"未记录"诚实显示
  var healthScore = data.healthScore != null ? data.healthScore : null;
  var anomalies = data.anomalies || [];
  var memories = data.memories || [];
  var unreadCount = data.unreadCount || 0;
  var graphNodes = data.graphNodes || [];
  var graphEdges = data.graphEdges || [];

  var color = healthScore == null ? 'var(--muted)'
    : healthScore >= 80 ? '#4A7C4A' : healthScore >= 60 ? '#B8860B' : '#C75B5B';
  var bg = healthScore == null ? 'rgba(128,128,128,0.12)'
    : healthScore >= 80 ? 'rgba(74,124,74,0.15)' : healthScore >= 60 ? 'rgba(184,134,11,0.15)' : 'rgba(199,91,91,0.15)';

  var app = el('div', {
    className: 'family-app',
    style: {
      display: 'flex',
      flexDirection: 'column',
      height: '100vh',
      padding: '20px',
      gap: '12px',
      overflow: 'hidden',
    }
  });

  // 顶部栏：实时同步指示器 + 未读徽章
  var headerBar = el('div', {
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingBottom: '8px',
      borderBottom: '1px solid var(--rule)',
      flexShrink: 0,
    }
  });
  var syncIndicator = el('div', {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: '8px',
      fontSize: '0.85rem',
      color: 'var(--muted)',
    }
  });
  var syncDot = el('span', {
    style: {
      display: 'inline-block',
      width: '10px',
      height: '10px',
      borderRadius: '50%',
      background: '#ccc',
    }
  });
  syncIndicator.appendChild(syncDot);
  syncIndicator.appendChild(document.createTextNode('同步中…'));
  headerBar.appendChild(syncIndicator);

  var badge = el('div', {
    style: {
      background: 'var(--danger)',
      color: '#fff',
      borderRadius: '12px',
      padding: '2px 10px',
      fontSize: '0.8rem',
      fontWeight: '700',
      display: unreadCount > 0 ? 'block' : 'none',
      cursor: 'pointer',
    },
    title: '点击查看通知',
    onclick: openNoticeSheet,
  }, String(unreadCount));
  headerBar.appendChild(badge);
  app.appendChild(headerBar);

  // ---------- 家属-老人绑定闭环（audit-5 前置 + audit-24 漏录提醒） ----------
  // 此前 linkFamilyMember API 零调用、注册硬编码老人角色，导致关怀永远死锁
  // （elderlyId 恒 undefined）。这里补绑定入口，并把 elderlyId 真正接给关怀发送。
  var _links = [];
  var _linkIndex = 0;
  var linksWrap = el('div', { style: { flexShrink: '0' } });
  app.appendChild(linksWrap);

  function currentElderly() {
    if (!_links.length) return null;
    if (_linkIndex >= _links.length) _linkIndex = 0;
    return _links[_linkIndex];
  }

  function refreshLinks() {
    return getFamilyMembers().then(function(list) {
      _links = list || [];
      renderLinks();
    }).catch(function() {
      _links = [];
      renderLinks();
    });
  }

  function renderLinks() {
    linksWrap.innerHTML = '';
    var cur = currentElderly();
    data.elderlyId = cur ? cur.elderly_user_id : '';
    if (!_links.length) {
      linksWrap.appendChild(buildBindCard());
      return;
    }
    if (_links.length > 1) linksWrap.appendChild(buildElderlySwitcher());

    var name = (cur && cur.elderly_name) || '老人';
    var line = null;
    if (cur && cur.last_session_at == null) {
      line = { tone: 'muted', text: name + '还没有过记录，先陪他/她说完今天这一条。' };
    } else if (cur && cur.missing_days != null && cur.missing_days >= 2) {
      line = { tone: 'warn', text: name + '已经 ' + cur.missing_days + ' 天没有新的回忆了。' };
    }
    if (line) {
      var box = el('div', {
        style: {
          background: line.tone === 'warn' ? 'rgba(184,134,11,0.12)' : 'var(--bg2)',
          border: '1px solid ' + (line.tone === 'warn' ? '#B8860B' : 'var(--rule)'),
          borderRadius: '10px', padding: '10px 12px', marginBottom: '8px',
          display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap',
        }
      });
      box.appendChild(el('span', {
        style: { fontSize: '0.9rem', color: 'var(--ink)', flex: 1, minWidth: '160px' }
      }, line.text));
      box.appendChild(el('button', {
        className: 'btn-secondary',
        style: { padding: '6px 12px', fontSize: '0.85rem' },
        onclick: function() {
          var ci = document.querySelector('textarea[placeholder^="输入文字关怀"]');
          if (ci) { ci.focus(); ci.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
        }
      }, '发条关怀'));
      linksWrap.appendChild(box);
    }
  }

  function buildBindCard() {
    var card = el('div', {
      style: {
        background: 'var(--bg2)', border: '2px solid var(--accent)',
        borderRadius: '12px', padding: '14px', marginBottom: '10px',
      }
    });
    card.appendChild(el('div', {
      style: { fontWeight: '700', fontSize: '0.98rem', marginBottom: '6px', color: 'var(--ink)' }
    }, '还没有关联老人'));
    card.appendChild(el('div', {
      style: { fontSize: '0.85rem', color: 'var(--muted)', marginBottom: '10px', lineHeight: 1.6 }
    }, '输入老人注册时填的手机号或姓名，关联后就能看到他/她的记录与健康小结。'));
    var who = el('input', {
      style: { width: '100%', padding: '10px', borderRadius: '8px', border: '1px solid var(--rule)', fontSize: '0.95rem', marginBottom: '8px', boxSizing: 'border-box' },
      placeholder: '老人的手机号或姓名',
    });
    var rel = el('input', {
      style: { width: '100%', padding: '10px', borderRadius: '8px', border: '1px solid var(--rule)', fontSize: '0.95rem', marginBottom: '8px', boxSizing: 'border-box' },
      placeholder: '关系（可选）：子女 / 配偶 / 其他',
    });
    var err = el('div', { style: { color: 'var(--danger)', fontSize: '0.85rem', minHeight: '1.2em', marginBottom: '6px' } });
    var btn = el('button', {
      className: 'btn-primary',
      style: { width: '100%', padding: '10px' },
      onclick: function() {
        var id = who.value.trim();
        if (!id) { err.textContent = '请先填写老人的手机号或姓名'; who.focus(); return; }
        btn.disabled = true; btn.textContent = '关联中…';
        linkFamilyMember(id, rel.value.trim() || null).then(function() {
          invalidateCache('/notification/family-members');
          return refreshLinks();
        }).catch(function(e) {
          err.textContent = (e && e.message) || '关联失败，请核对手机号或姓名';
          btn.disabled = false; btn.textContent = '关联';
        });
      }
    }, '关联');
    card.appendChild(who);
    card.appendChild(rel);
    card.appendChild(err);
    card.appendChild(btn);
    return card;
  }

  function buildElderlySwitcher() {
    var row = el('div', { style: { display: 'flex', gap: '8px', marginBottom: '8px', flexWrap: 'wrap' } });
    _links.forEach(function(l, i) {
      row.appendChild(el('button', {
        className: i === _linkIndex ? 'btn-primary' : 'btn-secondary',
        style: { padding: '6px 12px', fontSize: '0.85rem' },
        onclick: function() { _linkIndex = i; renderLinks(); }
      }, l.elderly_name || ('老人' + (i + 1))));
    });
    return row;
  }

  function openNoticeSheet() {
    var old = document.getElementById('family-notice-sheet');
    if (old && old.parentNode) old.parentNode.removeChild(old);
    var overlay = el('div', {
      id: 'family-notice-sheet',
      style: { position: 'fixed', inset: 0, background: 'rgba(31,27,22,0.5)', zIndex: 9000, display: 'flex', alignItems: 'flex-end', justifyContent: 'center' },
      onclick: function(e) { if (e.target === overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay); }
    });
    var sheet = el('div', {
      style: { background: 'var(--bg)', borderRadius: '16px 16px 0 0', width: '100%', maxWidth: '560px', maxHeight: '70vh', overflowY: 'auto', padding: '16px' }
    });
    var head = el('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' } });
    head.appendChild(el('strong', { style: { fontSize: '1rem' } }, '通知'));
    head.appendChild(el('button', {
      style: { border: 'none', background: 'transparent', fontSize: '1.2rem', cursor: 'pointer', color: 'var(--muted)' },
      'aria-label': '关闭',
      onclick: function() { if (overlay.parentNode) overlay.parentNode.removeChild(overlay); }
    }, '✕'));
    sheet.appendChild(head);
    var list = el('div', { style: { color: 'var(--muted)', fontSize: '0.9rem' } }, '加载中…');
    sheet.appendChild(list);
    overlay.appendChild(sheet);
    document.body.appendChild(overlay);
    getNotifications().then(function(items) {
      list.innerHTML = '';
      if (!items || !items.length) { list.textContent = '暂无通知'; return; }
      items.slice(0, 30).forEach(function(n) {
        var row = el('div', {
          style: { background: 'var(--bg2)', borderRadius: '10px', padding: '10px 12px', marginBottom: '8px' }
        });
        row.appendChild(el('div', { style: { fontSize: '0.9rem', color: 'var(--ink)' } }, n.message || n.title || '通知'));
        if (n.created_at) {
          row.appendChild(el('div', { style: { fontSize: '0.75rem', color: 'var(--muted)', marginTop: '2px' } },
            new Date(n.created_at).toLocaleString('zh-CN')));
        }
        list.appendChild(row);
      });
    }).catch(function() { list.textContent = '加载失败，请稍后再试'; });
  }

  refreshLinks();

  // 首屏：健康分大数字（紧凑）
  var hero = el('div', {
    style: {
      background: bg,
      borderRadius: '12px',
      padding: '12px 16px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      flexShrink: 0,
    }
  });
  hero.appendChild(el('div', {
    style: { fontSize: '0.85rem', color: 'var(--muted)' }
  }, '今日健康分'));
  hero.appendChild(el('div', {
    style: { fontSize: '2rem', fontWeight: '800', color: color }
  }, healthScore == null ? '—' : String(healthScore)));
  if (healthScore == null) {
    hero.appendChild(el('div', {
      style: { fontSize: '0.78rem', color: 'var(--muted)', marginTop: '2px' }
    }, '今天还没有记录'));
  }
  app.appendChild(hero);

  // story-9：脑健康小结卡——tier 引擎结论直达家属端专属模式（AC4：
  // 任意形态都有入口，旧版只有完整模式医生分支里藏着按钮）
  var tierSlot = el('div', { style: { flexShrink: '0' } });
  app.appendChild(tierSlot);
  Promise.all([
    import('../api/client.js'),
    import('../ui/decline.js'),
  ]).then(function(mods) {
    mods[0].getDeclineAnalysis(7).then(function(a) {
      mods[1].renderTierInto(tierSlot, a);
    }).catch(function() {});
  }).catch(function() {});

  // 今日异常提醒（紧凑）
  if (anomalies.length > 0) {
    var alertBox = el('div', {
      style: {
        background: 'var(--danger-l)',
        borderRadius: '10px',
        padding: '10px 14px',
        color: 'var(--danger)',
        fontSize: '0.85rem',
        flexShrink: 0,
      }
    });
    alertBox.appendChild(el('span', { style: { fontWeight: '700' } }, '⚠️ '));
    alertBox.appendChild(document.createTextNode(anomalies.map(function(a) { return a.message || String(a); }).join(' · ')));
    app.appendChild(alertBox);
  }

  // 3D 星云视口
  var nebulaWrap = el('div', {
    style: {
      flex: 1,
      position: 'relative',
      borderRadius: '12px',
      overflow: 'hidden',
      background: '#0a0908',
      minHeight: '0',
    }
  });

  // 浮动控制面板
  var controls = el('div', {
    style: {
      position: 'absolute',
      top: '10px',
      left: '10px',
      zIndex: 20,
      display: 'flex',
      flexDirection: 'column',
      gap: '8px',
      background: 'rgba(15,14,12,0.75)',
      backdropFilter: 'blur(8px)',
      borderRadius: '12px',
      padding: '10px',
      border: '1px solid rgba(255,255,255,0.08)',
    }
  });

  // 飞行漫游按钮
  var flyBtn = el('button', {
    style: {
      padding: '8px 14px',
      borderRadius: '8px',
      border: '1px solid rgba(255,255,255,0.15)',
      background: 'rgba(74,124,74,0.25)',
      color: '#fff',
      fontSize: '0.8rem',
      fontWeight: '600',
      cursor: 'pointer',
      transition: 'all 0.2s',
      whiteSpace: 'nowrap',
    },
    onclick: function() {
      if (_nebulaController) {
        _nebulaController.startFly();
        flyBtn.textContent = '✈️ 漫游中…';
        flyBtn.style.background = 'rgba(184,134,11,0.3)';
        setTimeout(function() {
          flyBtn.textContent = '✈️ 飞行漫游';
          flyBtn.style.background = 'rgba(74,124,74,0.25)';
        }, 5000);
      }
    }
  }, '✈️ 飞行漫游');
  controls.appendChild(flyBtn);

  // 时间筛选
  var timeFilterWrap = el('div', {
    style: { display: 'flex', flexDirection: 'column', gap: '4px' }
  });
  timeFilterWrap.appendChild(el('div', {
    style: { fontSize: '0.7rem', color: 'rgba(255,255,255,0.5)' }
  }, '时间筛选'));
  var timeSlider = el('input', {
    type: 'range',
    min: '0',
    max: '2',
    value: '2',
    step: '1',
    style: {
      width: '100px',
      accentColor: '#4A7C4A',
    },
    oninput: function() {
      var val = parseInt(this.value, 10);
      var filter = val === 0 ? '7' : val === 1 ? '30' : 'all';
      if (_nebulaController) _nebulaController.setTimeFilter(filter);
    }
  });
  timeFilterWrap.appendChild(timeSlider);
  var timeLabel = el('div', {
    style: { fontSize: '0.7rem', color: 'rgba(255,255,255,0.6)', textAlign: 'center' }
  }, '全部');
  timeFilterWrap.appendChild(timeLabel);
  timeSlider.oninput = function() {
    var val = parseInt(this.value, 10);
    var filter = val === 0 ? '7' : val === 1 ? '30' : 'all';
    var label = val === 0 ? '近 7 天' : val === 1 ? '近 30 天' : '全部';
    timeLabel.textContent = label;
    if (_nebulaController) _nebulaController.setTimeFilter(filter);
  };
  controls.appendChild(timeFilterWrap);

  // 情感色彩开关
  var emotionToggleWrap = el('div', {
    style: { display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }
  });
  var emotionToggle = el('input', {
    type: 'checkbox',
    id: 'family-emotion-toggle',
    style: { accentColor: '#4A7C4A', cursor: 'pointer' },
    onchange: function() {
      if (_nebulaController) _nebulaController.setEmotionMode(this.checked);
    }
  });
  emotionToggleWrap.appendChild(emotionToggle);
  emotionToggleWrap.appendChild(el('label', {
    htmlFor: 'family-emotion-toggle',
    style: { fontSize: '0.75rem', color: 'rgba(255,255,255,0.7)', cursor: 'pointer' }
  }, '情感色彩'));
  controls.appendChild(emotionToggleWrap);

  nebulaWrap.appendChild(controls);

  // 叙事片段弹出面板（右侧）
  var narrativePanel = el('div', {
    id: 'family-narrative-panel',
    style: {
      position: 'absolute',
      top: '10px',
      right: '10px',
      bottom: '10px',
      width: '260px',
      background: 'rgba(15,14,12,0.85)',
      backdropFilter: 'blur(12px)',
      borderRadius: '12px',
      padding: '16px',
      border: '1px solid rgba(255,255,255,0.08)',
      color: '#fff',
      zIndex: 20,
      display: 'none',
      flexDirection: 'column',
      gap: '10px',
      overflowY: 'auto',
    }
  });

  var narrativeHeader = el('div', {
    style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid rgba(255,255,255,0.1)', paddingBottom: '8px' }
  });
  var narrativeTitle = el('div', { style: { fontWeight: '700', fontSize: '0.95rem' } }, '记忆片段');
  narrativeHeader.appendChild(narrativeTitle);
  var closeNarrative = el('button', {
    style: {
      background: 'none', border: 'none', color: 'rgba(255,255,255,0.5)',
      fontSize: '1.1rem', cursor: 'pointer', lineHeight: '1'
    },
    onclick: function() { narrativePanel.style.display = 'none'; }
  }, '✕');
  narrativeHeader.appendChild(closeNarrative);
  narrativePanel.appendChild(narrativeHeader);

  var narrativeType = el('div', { style: { fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)', marginTop: '4px' } }, '—');
  narrativePanel.appendChild(narrativeType);
  var narrativeDate = el('div', { style: { fontSize: '0.75rem', color: 'rgba(255,255,255,0.4)', marginBottom: '4px' } }, '—');
  narrativePanel.appendChild(narrativeDate);
  var narrativeContent = el('div', {
    style: { fontSize: '0.9rem', lineHeight: '1.6', color: 'rgba(255,255,255,0.85)', flex: 1 }
  }, '点击星云中的节点查看记忆叙事。');
  narrativePanel.appendChild(narrativeContent);

  nebulaWrap.appendChild(narrativePanel);
  app.appendChild(nebulaWrap);

  // 本周记忆卡片（分享回路：生成→复制链接→微信转发；内容只含聚合数据）
  var cardSection = el('div', {
    className: 'memory-card-section',
    style: {
      borderTop: '1px solid var(--rule)',
      paddingTop: '10px',
      flexShrink: 0,
    }
  });
  cardSection.appendChild(el('div', {
    style: { fontWeight: '700', marginBottom: '6px', fontSize: '0.9rem' }
  }, '本周记忆卡片'));
  var cardBody = el('div', { style: { fontSize: '0.85rem', color: 'var(--ink2)' } });
  cardBody.appendChild(el('div', { style: { color: 'var(--muted)' } }, '加载中…'));
  cardSection.appendChild(cardBody);
  app.appendChild(cardSection);

  function renderCardPayload(payload, cardId) {
    cardBody.innerHTML = '';
    var statRow = el('div', {
      style: { display: 'flex', gap: '12px', flexWrap: 'wrap', marginBottom: '6px' }
    });
    [['记录', payload.record_count + ' 次'], ['活跃', payload.active_days + ' 天'],
     ['字数', payload.total_chars], ['状态', payload.trend_level]].forEach(function(pair) {
      statRow.appendChild(el('span', {
        style: {
          background: 'var(--bg2)', borderRadius: '8px',
          padding: '4px 10px', fontSize: '0.8rem',
        }
      }, pair[0] + ' ' + pair[1]));
    });
    cardBody.appendChild(statRow);
    if (payload.top_entities && payload.top_entities.length) {
      cardBody.appendChild(el('div', {
        style: { color: 'var(--muted)', fontSize: '0.8rem', marginBottom: '6px' }
      }, '常提起：' + payload.top_entities.map(function(e) { return e.label; }).join('、')));
    }
    cardBody.appendChild(el('button', {
      className: 'btn-secondary',
      style: { padding: '6px 14px', fontSize: '0.85rem' },
      onclick: function() {
        var url = location.origin + location.pathname + '#/share/card/' + cardId;
        var done = function() { trackEvent('memory_card_shared', { card_id: cardId }); };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(url).then(done).catch(function() { prompt('复制分享链接：', url); });
        } else {
          prompt('复制分享链接：', url);
        }
      }
    }, '复制分享链接'));
  }

  getLatestMemoryCard().then(function(res) {
    if (res && res.card) {
      renderCardPayload(res.card.payload, res.card.id);
    } else {
      cardBody.innerHTML = '';
      cardBody.appendChild(el('button', {
        className: 'btn-primary',
        style: { padding: '6px 14px', fontSize: '0.85rem' },
        onclick: function() {
          generateMemoryCard(7).then(function(data) {
            renderCardPayload(data.payload, data.id);
          }).catch(function() {
            cardBody.innerHTML = '';
            cardBody.appendChild(el('span', { style: { color: 'var(--muted)', fontSize: '0.8rem' } }, '卡片生成失败，请稍后重试'));
          });
        }
      }, '生成本周卡片'));
    }
  }).catch(function() {
    cardBody.innerHTML = '';
    cardBody.appendChild(el('span', { style: { color: 'var(--muted)', fontSize: '0.8rem' } }, '记忆卡片不可用'));
  });

  // 发送关怀区域
  var careSection = el('div', {
    style: {
      borderTop: '1px solid var(--rule)',
      paddingTop: '10px',
      flexShrink: 0,
    }
  });
  careSection.appendChild(el('div', {
    style: { fontWeight: '700', marginBottom: '6px', fontSize: '0.9rem' }
  }, '发送关怀'));
  var careInput = el('textarea', {
    style: {
      width: '100%',
      minHeight: '48px',
      borderRadius: '10px',
      border: '1px solid var(--rule)',
      padding: '8px',
      fontSize: '0.9rem',
      resize: 'vertical',
      boxSizing: 'border-box',
      marginBottom: '6px',
    },
    placeholder: '输入文字关怀，或发送语音留言…'
  });
  careSection.appendChild(careInput);

  var careBtnRow = el('div', {
    style: { display: 'flex', gap: '8px' }
  });
  careBtnRow.appendChild(el('button', {
    className: 'btn-primary',
    style: { flex: 1, padding: '8px' },
    onclick: function() {
      var text = careInput.value.trim();
      if (!text) return;
      var elderlyId = data.elderlyId || '';
      if (!elderlyId) {
        alert('请先在上方关联老人');
        return;
      }
      var delivered = isConnected();
      var msg = sendWebSocketCare(elderlyId, text, null);
      wsSend(msg);
      careInput.value = '';
      // 断线时入队但尚未送达——不谎报"已发送"（此前是无条件 alert 成功）
      alert(delivered ? '已发送给老人' : '网络断了，这条会先存着，等连上再发');
    }
  }, '发送文字'));
  careBtnRow.appendChild(el('button', {
    className: 'btn-secondary',
    style: { flex: 1, padding: '8px' },
    onclick: function() {
      alert('语音留言功能：请使用录音按钮录制后发送');
    }
  }, '发送语音'));
  careSection.appendChild(careBtnRow);
  app.appendChild(careSection);

  // 底部操作栏
  var bar = el('div', {
    style: {
      display: 'flex',
      gap: '10px',
      paddingTop: '8px',
      borderTop: '1px solid var(--rule)',
      flexShrink: 0,
    }
  });
  bar.appendChild(el('button', {
    className: 'btn-secondary',
    style: { flex: 1 },
    onclick: function() {
      import('../ui/scale.js').then(function(mod) { mod.openScalePanel(); });
    }
  }, '查看量表'));
  bar.appendChild(el('button', {
    className: 'btn-secondary',
    style: { flex: 1 },
    onclick: function() {
      alert('历史记录功能开发中');
    }
  }, '查看历史'));
  app.appendChild(bar);

  container.appendChild(app);

  // 初始化 3D 星云
  var _nebulaController = null;
  function showNarrative(node) {
    narrativePanel.style.display = 'flex';
    narrativeTitle.textContent = node.label || '记忆节点';
    var typeLabels = { person: '人物', event: '事件', place: '地点', time: '时间', item: '物品', self: '自我', anon: '匿名' };
    narrativeType.textContent = (typeLabels[node.type] || '节点') + (node.emotion ? ' · ' + (node.emotion === 'positive' ? '积极' : node.emotion === 'negative' ? '消极' : '中性') : '');
    var d = new Date(node.date);
    narrativeDate.textContent = isNaN(d.getTime()) ? '—' : d.toLocaleDateString('zh-CN');
    narrativeContent.textContent = node.narrative || '暂无叙事内容';
  }

  if (!graphNodes.length) {
    // story-11：空图谱不再让 nebula 生成 30 个假"记忆"节点——显示诚实引导
    nebulaWrap.style.background = 'var(--bg2)';
    nebulaWrap.appendChild(el('div', {
      style: {
        position: 'absolute', top: '50%', left: '50%',
        transform: 'translate(-50%, -50%)',
        textAlign: 'center', color: 'var(--muted)',
        fontSize: '0.95rem', lineHeight: 1.9, padding: '0 24px',
        whiteSpace: 'pre-line',
      }
    }, '还没有记忆之星\n每陪老人记录一天，这里就多一颗星'));
  } else {
    import('../3d/memory-nebula.js').then(function(mod) {
      _nebulaController = mod.initMemoryNebula(nebulaWrap, graphNodes, memories);
      if (_nebulaController) {
        _nebulaController.setOnNodeClick(showNarrative);
      } else {
        // WebGL 不支持：回退到记忆列表
        nebulaWrap.innerHTML = '';
        nebulaWrap.style.background = 'var(--bg2)';
        nebulaWrap.style.padding = '16px';
        nebulaWrap.style.overflowY = 'auto';
        memories.slice(0, 10).forEach(function(m) {
          var card = el('div', {
            style: {
              background: 'var(--bg)',
              borderRadius: '10px',
              padding: '12px',
              marginBottom: '8px',
            }
          });
          var dateStr = m.date || m.created_at ? new Date(m.date || m.created_at).toLocaleDateString('zh-CN') : '今天';
          card.appendChild(el('div', { style: { fontSize: '0.75rem', color: 'var(--muted)', marginBottom: '4px' } }, dateStr));
          card.appendChild(el('div', { style: { fontSize: '0.9rem', lineHeight: '1.5', color: 'var(--ink)' } }, m.narrative_text || m.text || '—'));
          nebulaWrap.appendChild(card);
        });
      }
    }).catch(function(err) {
      console.error('3D module load failed:', err);
    });
  }

  // 启动 WebSocket 连接
  var token = getToken();
  if (token) {
    wsConnect(token, function(msg) {
      if (msg.type === 'new_session' || msg.type === 'new_scale') {
        try {
          var audio = new Audio('/notification.mp3');
          audio.volume = 0.3;
          audio.play().catch(function() {});
        } catch (e) {}
        unreadCount++;
        badge.textContent = String(unreadCount);
        badge.style.display = 'block';
      }
      if (msg.type === 'read_receipt') {
        console.log('老人已读消息', msg.payload);
      }
    });
  }

  // 同步指示器更新
  function updateSyncIndicator() {
    if (isConnected()) {
      syncDot.style.background = '#4A7C4A';
      syncIndicator.lastChild.textContent = isUsingSSE() ? '已连接 (SSE)' : '已连接';
    } else {
      syncDot.style.background = '#C75B5B';
      syncIndicator.lastChild.textContent = '未连接';
    }
  }
  updateSyncIndicator();
  var indicatorInterval = setInterval(updateSyncIndicator, 3000);
  container._cleanup = function() { clearInterval(indicatorInterval); if (_nebulaController) _nebulaController.destroy(); };
}

// 辅助函数：供 main.js 调用以获取老人数据
export function fetchFamilyData() {
  return Promise.all([
    listSessions(10).catch(function() { return []; }),
    getHealthTrend(1).catch(function() { return null; }),
    getNotifications().catch(function() { return []; }),
    getLatestGraph().catch(function() { return null; })
  ]).then(function(results) {
    var sessions = results[0] || [];
    var trend = results[1] || {};
    var notifications = results[2] || [];
    var graph = results[3] || null;
    return {
      healthScore: trend.score != null ? trend.score : (sessions[0] && sessions[0].health_score ? sessions[0].health_score : 85),
      anomalies: trend.anomalies || notifications.slice(0, 3).map(function(n) {
        return { message: n.message || n.title || '异常提醒' };
      }),
      memories: sessions,
      unreadCount: notifications.filter(function(n) { return !n.is_read; }).length,
      graphNodes: graph && graph.nodes ? graph.nodes : [],
      graphEdges: graph && graph.edges ? graph.edges : [],
    };
  });
}
