// ============ HEATMAP (Pure SVG / DOM) ============
// GitHub-style calendar heatmap: 30-day × 1 row

const HEAT_COLORS = [
  '#ebedf0',   // 0
  '#9be9a8',   // 1-2
  '#40c463',   // 3-5
  '#30a14e',   // 6-9
  '#216e39',   // 10+
];

function getColor(value, max) {
  if (!value || value <= 0) return HEAT_COLORS[0];
  const ratio = max > 0 ? value / max : 0;
  if (ratio <= 0.2) return HEAT_COLORS[1];
  if (ratio <= 0.4) return HEAT_COLORS[2];
  if (ratio <= 0.7) return HEAT_COLORS[3];
  return HEAT_COLORS[4];
}

export function renderHeatmap(container, sessions, options) {
  if (!container) return;
  options = options || {};
  var onClick = options.onClick;

  if (!sessions || sessions.length === 0) {
    container.innerHTML = '<div style="text-align:center;color:var(--muted);padding:20px;font-size:0.85rem;">暂无数据</div>';
    return;
  }

  const cellSize = 18;
  const gap = 4;
  const days = 30;
  const recentSessions = sessions.slice(-days);
  const maxVal = Math.max(1, ...recentSessions.map(function(s) {
    return s.value || s.nodeCount || s.narrativeLength || 1;
  }));

  const width = days * (cellSize + gap) - gap;
  const height = cellSize + 24;

  let svg = `<svg viewBox="0 0 ${width} ${height}" style="width:100%;height:auto;display:block;">`;

  recentSessions.forEach(function(s, i) {
    const val = s.value || s.nodeCount || s.narrativeLength || 0;
    const x = i * (cellSize + gap);
    const y = 0;
    const color = getColor(val, maxVal);
    const dateLabel = s.dateLabel || s.date || '';

    svg += `<rect x="${x}" y="${y}" width="${cellSize}" height="${cellSize}" rx="3" fill="${color}" stroke="rgba(0,0,0,0.05)" stroke-width="0.5" class="heatmap-cell" data-index="${i}" data-date="${dateLabel}" style="cursor:pointer"/>`;

    // Day number label below
    if (i % 5 === 0 || i === recentSessions.length - 1) {
      svg += `<text x="${x + cellSize / 2}" y="${cellSize + 14}" text-anchor="middle" font-size="9" fill="var(--muted)">${dateLabel}</text>`;
    }
  });

  svg += '</svg>';
  container.innerHTML = svg;

  // Tooltip handling via DOM events (delegation)
  container.addEventListener('mouseover', function(e) {
    const cell = e.target.closest('.heatmap-cell');
    if (!cell) return;
    const idx = parseInt(cell.getAttribute('data-index'), 10);
    const s = recentSessions[idx];
    if (!s) return;
    const tooltip = document.createElement('div');
    tooltip.id = 'heatmap-tooltip';
    tooltip.style.cssText = 'position:fixed;z-index:9999;background:rgba(31,27,22,0.9);color:#fff;padding:6px 10px;border-radius:6px;font-size:0.75rem;pointer-events:none;white-space:nowrap;';
    const val = s.value || s.nodeCount || s.narrativeLength || 0;
    tooltip.textContent = (s.dateLabel || s.date || '') + '：' + val + ' 节点';
    document.body.appendChild(tooltip);
    const rect = cell.getBoundingClientRect();
    tooltip.style.left = (rect.left + rect.width / 2 - tooltip.offsetWidth / 2) + 'px';
    tooltip.style.top = (rect.top - tooltip.offsetHeight - 6) + 'px';
  });

  container.addEventListener('mouseout', function(e) {
    if (e.target.closest('.heatmap-cell')) {
      const t = document.getElementById('heatmap-tooltip');
      if (t) t.remove();
    }
  });

  // Click handling
  if (onClick) {
    container.addEventListener('click', function(e) {
      const cell = e.target.closest('.heatmap-cell');
      if (!cell) return;
      const idx = parseInt(cell.getAttribute('data-index'), 10);
      const s = recentSessions[idx];
      if (s) onClick(s, idx);
    });
  }
}

export function generateMockHeatmapSessions(days) {
  const sessions = [];
  for (let i = 0; i < days; i++) {
    const d = new Date();
    d.setDate(d.getDate() - (days - 1 - i));
    sessions.push({
      date: (d.getMonth() + 1) + '/' + d.getDate(),
      dateLabel: (d.getMonth() + 1) + '/' + d.getDate(),
      value: Math.floor(Math.random() * 12),
      nodeCount: Math.floor(Math.random() * 12),
      narrativeLength: Math.floor(Math.random() * 200 + 50),
    });
  }
  return sessions;
}
