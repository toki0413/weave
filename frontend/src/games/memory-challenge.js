// ============ MEMORY CHALLENGE GAME ============
// 记忆训练：随机抽取历史节点，问“这是哪一天出现的？”
import { state } from '../state.js';
import { el } from '../ui/components.js';
import { saveTrainingScore } from '../api/client.js';

export function initMemoryChallenge(container) {
  if (!container) return;
  container.innerHTML = '';

  var nodes = (state.nodes || []).filter(function(n) {
    return n.type === 'person' || n.type === 'event';
  });
  if (nodes.length < 3) {
    container.appendChild(el('div', {
      style: { textAlign: 'center', padding: '40px 20px', color: 'var(--muted)', fontSize: '0.9rem' }
    }, [
      el('div', { style: { fontSize: '2rem', marginBottom: '12px' } }, '📚'),
      '需要更多记忆数据，请继续记录日常',
    ]));
    return;
  }

  // 随机抽取 3 个节点
  var shuffled = nodes.slice().sort(function() { return Math.random() - 0.5; });
  var questions = shuffled.slice(0, 3).map(function(n) {
    // 找该节点第一次出现的会话日期
    var firstDate = null;
    var firstDay = 1;
    var narrativeSnippet = '';
    if (state.sessionHistory) {
      for (var i = 0; i < state.sessionHistory.length; i++) {
        var s = state.sessionHistory[i];
        if (s.graph && s.graph.nodes) {
          var found = s.graph.nodes.find(function(gn) { return String(gn.label).trim() === String(n.label).trim(); });
          if (found && !firstDate) {
            firstDate = s.date;
            firstDay = s.dayNumber || (i + 1);
            narrativeSnippet = s.graph.nodes.map(function(gn) { return gn.label; }).join('、');
            break;
          }
        }
      }
    }
    // 如果找不到历史，用一致回退值
    if (!firstDate) {
      firstDay = state.currentDay || 1;
      firstDate = new Date().toISOString();
    }
    return {
      node: n,
      correctDay: firstDay,
      correctDate: firstDate,
      snippet: narrativeSnippet || '暂无原始片段',
    };
  });

  var currentQ = 0;
  var score = 0;
  var resultSaved = false;

  function renderQuestion() {
    container.innerHTML = '';
    var q = questions[currentQ];
    var choices = generateChoices(q.correctDay);

    var header = el('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' } }, [
      el('div', { style: { fontSize: '0.75rem', color: 'var(--muted)' } }, '第 ' + (currentQ + 1) + ' / 3 题'),
      el('div', { style: { fontSize: '0.75rem', color: 'var(--muted)' } }, '得分: ' + score),
    ]);
    container.appendChild(header);

    container.appendChild(el('div', { style: { fontSize: '1.1rem', fontWeight: '700', marginBottom: '8px', textAlign: 'center' } }, [
      '“', q.node.label, '” 是在哪一天出现的？',
    ]));

    var choicesWrap = el('div', { style: { display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '12px' } });
    choices.forEach(function(c) {
      var btn = el('button', {
        className: 'btn-secondary',
        style: { textAlign: 'left', padding: '12px 16px', fontSize: '0.95rem' },
        onclick: function() { handleAnswer(c.day === q.correctDay, q, c.day); },
      }, [
        el('span', { style: { marginRight: '8px' } }, '○'),
        '第 ' + c.day + ' 天',
      ]);
      choicesWrap.appendChild(btn);
    });
    container.appendChild(choicesWrap);
  }

  function generateChoices(correctDay) {
    var set = new Set([correctDay]);
    while (set.size < 3) {
      var fake = Math.max(1, correctDay + Math.floor(Math.random() * 5) - 2);
      if (fake !== correctDay) set.add(fake);
    }
    return Array.from(set).map(function(d) { return { day: d }; }).sort(function() { return Math.random() - 0.5; });
  }

  function handleAnswer(isCorrect, q, chosenDay) {
    container.innerHTML = '';
    if (isCorrect) {
      score += 10;
      container.appendChild(el('div', { style: { textAlign: 'center', padding: '20px' } }, [
        el('div', { style: { fontSize: '2.5rem', marginBottom: '8px' } }, '🎉'),
        el('div', { style: { fontSize: '1.1rem', fontWeight: '700', color: 'var(--accent)' } }, '答对了！'),
        el('div', { style: { fontSize: '0.85rem', color: 'var(--muted)', marginTop: '4px' } }, '第 ' + q.correctDay + ' 天'),
      ]));
    } else {
      container.appendChild(el('div', { style: { textAlign: 'center', padding: '20px' } }, [
        el('div', { style: { fontSize: '2.5rem', marginBottom: '8px' } }, '📖'),
        el('div', { style: { fontSize: '1.1rem', fontWeight: '700', color: 'var(--danger)' } }, '答错了'),
        el('div', { style: { fontSize: '0.85rem', color: 'var(--muted)', marginTop: '4px' } }, '正确答案是第 ' + q.correctDay + ' 天'),
        el('div', { style: { fontSize: '0.8rem', color: 'var(--ink2)', marginTop: '8px', background: 'var(--bg2)', padding: '8px', borderRadius: '6px' } }, [
          '原始片段：', q.snippet,
        ]),
      ]));
    }

    var nextBtn = el('button', {
      className: 'btn-primary',
      style: { width: '100%', marginTop: '16px' },
      onclick: function() {
        currentQ++;
        if (currentQ < questions.length) {
          renderQuestion();
        } else {
          showResult();
        }
      },
    }, currentQ < questions.length - 1 ? '下一题' : '查看结果');
    container.appendChild(nextBtn);
    nextBtn.focus();
  }

  function showResult() {
    if (resultSaved) return;
    resultSaved = true;
    container.innerHTML = '';
    var healthIndex = Math.min(100, Math.round((score / 30) * 100));
    container.appendChild(el('div', { style: { textAlign: 'center', padding: '20px' } }, [
      el('div', { style: { fontSize: '2.5rem', marginBottom: '8px' } }, '🏆'),
      el('div', { style: { fontSize: '1.2rem', fontWeight: '800' } }, '总分: ' + score + ' / 30'),
      el('div', { style: { fontSize: '1rem', fontWeight: '600', color: 'var(--accent)', marginTop: '8px' } }, '记忆健康指数: ' + healthIndex + '%'),
      el('div', { style: { fontSize: '0.8rem', color: 'var(--muted)', marginTop: '8px' } },
        healthIndex >= 80 ? '记忆状态良好，继续保持！' :
        healthIndex >= 50 ? '记忆状态尚可，建议多记录日常。' :
        '需要更多记忆训练，请继续记录日常。'
      ),
    ]));

    // 保存到本地状态
    if (!state.trainingScores) state.trainingScores = [];
    state.trainingScores.push({ gameType: 'memory_challenge', score: score, date: new Date().toISOString() });
    try {
      localStorage.setItem('trainingScores', JSON.stringify(state.trainingScores));
    } catch (e) {}

    // 尝试同步到后端
    try {
      saveTrainingScore('memory_challenge', score).catch(function(err) {
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

  renderQuestion();
}
