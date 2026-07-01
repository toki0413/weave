// ============ RADAR CHART (Pure SVG) ============
// 6-dimension cognitive radar: memory, language, orientation, computation, attention, executive

const DIMENSIONS = [
  { key: 'memory', label: '记忆' },
  { key: 'language', label: '语言' },
  { key: 'orientation', label: '定向' },
  { key: 'computation', label: '计算' },
  { key: 'attention', label: '注意力' },
  { key: 'executive', label: '执行功能' },
];

const COLORS = {
  current: '#4A7C4A',
  baseline: '#3D6FA8',
  grid: '#D5CCBC',
  text: '#5C5448',
};

export function renderRadarChart(container, metrics) {
  if (!container) return;

  const width = 280;
  const height = 260;
  const cx = width / 2;
  const cy = height / 2 + 8;
  const radius = 90;
  const levels = 5;

  // Validate metrics
  const hasData = metrics && (
    metrics.current || metrics.baseline
  );
  if (!hasData) {
    container.innerHTML = '<div style="text-align:center;color:var(--muted);padding:40px;font-size:0.85rem;">暂无数据</div>';
    return;
  }

  let svg = `<svg viewBox="0 0 ${width} ${height}" style="width:100%;height:auto;display:block;">`;

  // Grid: concentric polygons
  for (let i = 1; i <= levels; i++) {
    const r = (radius / levels) * i;
    let points = '';
    for (let j = 0; j < DIMENSIONS.length; j++) {
      const angle = (Math.PI * 2 * j) / DIMENSIONS.length - Math.PI / 2;
      const x = cx + Math.cos(angle) * r;
      const y = cy + Math.sin(angle) * r;
      points += `${x},${y} `;
    }
    svg += `<polygon points="${points.trim()}" fill="none" stroke="${COLORS.grid}" stroke-width="0.5"/>`;
    // Axis value label
    svg += `<text x="${cx + 4}" y="${cy - r + 4}" font-size="9" fill="${COLORS.text}">${(100 / levels) * i}</text>`;
  }

  // Axis lines and labels
  for (let j = 0; j < DIMENSIONS.length; j++) {
    const angle = (Math.PI * 2 * j) / DIMENSIONS.length - Math.PI / 2;
    const x = cx + Math.cos(angle) * radius;
    const y = cy + Math.sin(angle) * radius;
    svg += `<line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" stroke="${COLORS.grid}" stroke-width="0.5"/>`;
    // Label
    const lx = cx + Math.cos(angle) * (radius + 20);
    const ly = cy + Math.sin(angle) * (radius + 20);
    const anchor = Math.abs(Math.cos(angle)) < 0.3 ? 'middle' : (Math.cos(angle) > 0 ? 'start' : 'end');
    svg += `<text x="${lx}" y="${ly + 4}" text-anchor="${anchor}" font-size="11" fill="var(--ink2)" font-weight="600">${DIMENSIONS[j].label}</text>`;
  }

  // Data layers
  function drawLayer(data, color, strokeWidth, fillOpacity) {
    const vals = DIMENSIONS.map(function(d) {
      const v = data[d.key];
      return typeof v === 'number' ? Math.max(0, Math.min(100, v)) : 0;
    });
    let points = '';
    for (let j = 0; j < DIMENSIONS.length; j++) {
      const angle = (Math.PI * 2 * j) / DIMENSIONS.length - Math.PI / 2;
      const r = (vals[j] / 100) * radius;
      const x = cx + Math.cos(angle) * r;
      const y = cy + Math.sin(angle) * r;
      points += `${x},${y} `;
    }
    svg += `<polygon points="${points.trim()}" fill="${color}" fill-opacity="${fillOpacity}" stroke="${color}" stroke-width="${strokeWidth}" stroke-linejoin="round"/>`;
    // Data points
    for (let j = 0; j < DIMENSIONS.length; j++) {
      const angle = (Math.PI * 2 * j) / DIMENSIONS.length - Math.PI / 2;
      const r = (vals[j] / 100) * radius;
      const x = cx + Math.cos(angle) * r;
      const y = cy + Math.sin(angle) * r;
      svg += `<circle cx="${x}" cy="${y}" r="3" fill="${color}" stroke="#fff" stroke-width="1.5"/>`;
    }
  }

  if (metrics.baseline) {
    drawLayer(metrics.baseline, COLORS.baseline, 1.5, 0.15);
  }
  if (metrics.current) {
    drawLayer(metrics.current, COLORS.current, 2, 0.25);
  }

  // Legend
  if (metrics.baseline || metrics.current) {
    let legendY = 14;
    svg += `<g transform="translate(12, ${legendY})">`;
    if (metrics.current) {
      svg += `<rect x="0" y="0" width="10" height="10" fill="${COLORS.current}" rx="2"/>`;
      svg += `<text x="14" y="9" font-size="10" fill="var(--ink2)">当前</text>`;
    }
    if (metrics.baseline) {
      svg += `<rect x="50" y="0" width="10" height="10" fill="${COLORS.baseline}" rx="2"/>`;
      svg += `<text x="64" y="9" font-size="10" fill="var(--ink2)">基线</text>`;
    }
    svg += `</g>`;
  }

  svg += '</svg>';
  container.innerHTML = svg;
}

export function generateMockRadarMetrics() {
  return {
    current: {
      memory: 72,
      language: 80,
      orientation: 65,
      computation: 55,
      attention: 78,
      executive: 60,
    },
    baseline: {
      memory: 85,
      language: 82,
      orientation: 88,
      computation: 70,
      attention: 80,
      executive: 75,
    },
  };
}
