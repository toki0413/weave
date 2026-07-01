// ============ NUMBER LINK GAME ============
// 数字连线：按时间顺序点击记忆节点（从最早到最近）
import { state } from '../state.js';
import { el } from '../ui/components.js';
import { saveTrainingScore } from '../api/client.js';

export function initNumberLink(container) {
  if (!container) return;
  container.innerHTML = '';

  var sessions = state.sessionHistory || [];
  var gridSize = sessions.length >= 5 ? 5 : (sessions.length >= 3 ? 3 : 0);
  if (gridSize === 0) {
    container.appendChild(el('div', {
      style: { textAlign: 'center', padding: '40px 20px', color: 'var(--muted)', fontSize: '0.9rem' }
    }, [
      el('div', { style: { fontSize: '2rem', marginBottom: '12px' } }, '📚'),
      '需要更多记忆数据，请继续记录日常',
    ]));
    return;
  }

  // 从 sessionHistory 中提取节点标签，按时间顺序
  var allLabels = [];
  sessions.forEach(function(s) {
    if (s.graph && s.graph.nodes) {
      s.graph.nodes.forEach(function(n) {
        if (n.label != null && allLabels.indexOf(n.label) < 0) {
          allLabels.push(n.label);
        }
      });
    }
  });

  // 取 gridSize * gridSize 个节点（如果不够，随机填充一些已有节点）
  var needed = gridSize * gridSize;
  var maxAttempts = needed * 10;
  var attempts = 0;
  while (allLabels.length < needed && attempts < maxAttempts) {
    attempts++;
    var rand = sessions[Math.floor(Math.random() * sessions.length)];
    if (rand && rand.graph && rand.graph.nodes) {
      var randNode = rand.graph.nodes[Math.floor(Math.random() * rand.graph.nodes.length)];
      if (randNode && randNode.label != null) {
        allLabels.push(randNode.label);
      }
    }
  }
  allLabels = allLabels.slice(0, needed);

  // 打乱位置，但保留原始时间顺序作为“正确顺序”
  var correctOrder = allLabels.slice(); // 按出现时间顺序
  var shuffledPositions = allLabels.slice().sort(function() { return Math.random() - 0.5; });

  var clickedOrder = [];
  var score = 0;
  var errorCount = 0;
  var lives = 3;
  var isCompleted = false;

  var header = el('div', { style: { textAlign: 'center', marginBottom: '12px' } }, [
    el('div', { style: { fontSize: '1rem', fontWeight: '700' } }, '按时间顺序点击节点'),
    el('div', { style: { fontSize: '0.75rem', color: 'var(--muted)', marginTop: '4px' } }, '从最早出现的记忆节点开始'),
  ]);
  container.appendChild(header);

  var status = el('div', { style: { textAlign: 'center', fontSize: '0.85rem', marginBottom: '12px', minHeight: '24px' } });
  container.appendChild(status);

  var grid = el('div', {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(' + gridSize + ', 1fr)',
      gap: '8px',
      maxWidth: '320px',
      margin: '0 auto',
    },
  });

  var cells = [];
  shuffledPositions.forEach(function(label, idx) {
    var cell = el('button', {
      className: 'btn-secondary',
      style: {
        aspectRatio: '1',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        textAlign: 'center',
        padding: '4px',
        fontSize: '0.75rem',
        fontWeight: '600',
        wordBreak: 'break-all',
        transition: 'all 0.2s ease',
      },
      onclick: function() { handleCellClick(label, idx, cell); },
    }, label != null ? String(label) : '');
    cells.push(cell);
    grid.appendChild(cell);
  });
  container.appendChild(grid);

  function handleCellClick(label, idx, cell) {
    if (isCompleted || cell.disabled) return;

    var expected = correctOrder[clickedOrder.length];
    if (label === expected) {
      clickedOrder.push(label);
      cell.style.background = 'var(--accent)';
      cell.style.color = '#fff';
      cell.style.borderColor = 'var(--accent)';
      cell.disabled = true;
      status.textContent = '✓ 正确！进度 ' + clickedOrder.length + ' / ' + correctOrder.length;
      status.style.color = 'var(--accent)';

      if (clickedOrder.length === correctOrder.length) {
        isCompleted = true;
        showSuccess();
      }
    } else {
      errorCount++;
      lives--;
      cell.style.background = '#FFEBEE';
      cell.style.color = '#C0392B';
      status.textContent = '✗ 顺序不对，剩余机会 ' + lives + ' / 3';
      status.style.color = '#C0392B';
      setTimeout(function() {
        cell.style.background = '';
        cell.style.color = '';
        if (lives > 0) {
          status.textContent = '';
        }
      }, 2000);
      if (lives <= 0) {
        isCompleted = true;
        showGameOver();
      }
    }
  }

  function showGameOver() {
    container.innerHTML = '';
    container.appendChild(el('div', { style: { textAlign: 'center', padding: '20px' } }, [
      el('div', { style: { fontSize: '2.5rem', marginBottom: '8px' } }, '💔'),
      el('div', { style: { fontSize: '1.2rem', fontWeight: '800', color: '#C0392B' } }, '机会用完了'),
      el('div', { style: { fontSize: '1rem', fontWeight: '600', color: 'var(--muted)', marginTop: '8px' } }, '已正确连接 ' + clickedOrder.length + ' / ' + correctOrder.length + ' 个节点'),
    ]));

    var closeBtn = el('button', {
      className: 'btn-primary',
      style: { width: '100%', marginTop: '16px' },
      onclick: function() {
        var overlay = document.getElementById('game-modal-overlay');
        if (overlay) overlay.remove();
      },
    }, '关闭');
    container.appendChild(closeBtn);
    closeBtn.focus();
  }

  function showSuccess() {
    score = Math.max(0, Math.round(100 - errorCount * 10));
    var healthIndex = score;

    container.innerHTML = '';
    container.appendChild(el('div', { style: { textAlign: 'center', padding: '20px' } }, [
      el('div', { style: { fontSize: '2.5rem', marginBottom: '8px' } }, '🎉'),
      el('div', { style: { fontSize: '1.2rem', fontWeight: '800' } }, '完成！'),
      el('div', { style: { fontSize: '1rem', fontWeight: '600', color: 'var(--accent)', marginTop: '8px' } }, '记忆健康指数: ' + healthIndex + '%'),
    ]));

    // 成功动画：画一条线连接所有节点（纯 CSS 动画）
    var animationWrap = el('div', { style: { position: 'relative', height: '60px', marginTop: '16px' } });
    var dotContainer = el('div', { style: { display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '12px' } });
    clickedOrder.forEach(function(_, i) {
      var dot = el('div', {
        style: {
          width: '12px',
          height: '12px',
          borderRadius: '50%',
          background: 'var(--accent)',
          transform: 'scale(0)',
          animation: 'numberLinkPop 0.3s ease forwards',
          animationDelay: (i * 0.1) + 's',
        },
      });
      dotContainer.appendChild(dot);
    });
    animationWrap.appendChild(dotContainer);
    container.appendChild(animationWrap);

    // 添加动画 keyframes
    if (!document.getElementById('number-link-animations')) {
      var style = el('style', { id: 'number-link-animations' });
      style.textContent = '@keyframes numberLinkPop { 0% { transform: scale(0); } 80% { transform: scale(1.2); } 100% { transform: scale(1); } }';
      document.head.appendChild(style);
    }

    // 保存到本地状态
    if (!state.trainingScores) state.trainingScores = [];
    state.trainingScores.push({ gameType: 'number_link', score: score, date: new Date().toISOString() });
    try {
      localStorage.setItem('trainingScores', JSON.stringify(state.trainingScores));
    } catch (e) {}

    // 尝试同步到后端
    try {
      saveTrainingScore('number_link', score).catch(function(err) {
        console.warn('同步训练分数到服务器失败，已保存到本地', err);
      });
    } catch (e) {}

    var closeBtn = el('button', {
      className: 'btn-primary',
      style: { width: '100%', marginTop: '16px' },
      onclick: function() {
        var overlay = document.getElementById('game-modal-overlay');
        if (overlay) overlay.remove();
      },
    }, '关闭');
    container.appendChild(closeBtn);
    closeBtn.focus();
  }
}
