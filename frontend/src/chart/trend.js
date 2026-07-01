// ============ TREND CHART (Pure SVG) ============
// 7-day health trend line chart

export function renderTrendChart(container, data, options = {}) {
  const {
    width = 400,
    height = 200,
    margin = { top: 20, right: 20, bottom: 30, left: 40 },
    color = '#4A7C4A',
    dangerColor = '#C0392B',
  } = options;

  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;

  if (!data || data.length === 0) {
    container.innerHTML = '<div style="text-align:center;color:var(--muted);padding:40px;">暂无数据</div>';
    return;
  }

  // Scales
  const maxHealth = 100;
  const maxAnomalies = Math.max(1, ...data.map(d => d.anomalies || 0));
  const xStep = data.length > 1 ? innerWidth / (data.length - 1) : innerWidth / 2;

  function xScale(i) { return margin.left + i * xStep; }
  function yScale(h) { return margin.top + innerHeight - (h / maxHealth) * innerHeight; }
  function yScaleAnomaly(a) { return margin.top + innerHeight - (a / maxAnomalies) * innerHeight * 0.5; }

  // Build SVG
  let svg = `<svg viewBox="0 0 ${width} ${height}" style="width:100%;height:auto;">`;

  // Grid lines
  for (let i = 0; i <= 5; i++) {
    const y = margin.top + (innerHeight / 5) * i;
    const val = Math.round(100 - (100 / 5) * i);
    svg += `<line x1="${margin.left}" y1="${y}" x2="${width - margin.right}" y2="${y}" stroke="var(--rule)" stroke-width="0.5"/>`;
    svg += `<text x="${margin.left - 5}" y="${y + 4}" text-anchor="end" font-size="10" fill="var(--muted)">${val}</text>`;
  }

  // Health line
  const points = data.map((d, i) => `${xScale(i)},${yScale(d.health)}`).join(' ');
  svg += `<polyline points="${points}" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>`;

  // Anomaly bars (secondary axis)
  data.forEach((d, i) => {
    if (d.anomalies > 0) {
      const barX = xScale(i) - 3;
      const barY = yScaleAnomaly(d.anomalies);
      const barHeight = margin.top + innerHeight - barY;
      svg += `<rect x="${barX}" y="${barY}" width="6" height="${barHeight}" fill="${dangerColor}" opacity="0.3" rx="2"/>`;
    }
  });

  // Data points
  data.forEach((d, i) => {
    const cx = xScale(i);
    const cy = yScale(d.health);
    const color = d.health >= 80 ? '#4A7C4A' : d.health >= 50 ? '#F39C12' : '#C0392B';
    svg += `<circle cx="${cx}" cy="${cy}" r="5" fill="${color}" stroke="white" stroke-width="2"/>`;
  });

  // X-axis labels (dates)
  data.forEach((d, i) => {
    const label = d.day ? `D${d.day}` : (i + 1);
    svg += `<text x="${xScale(i)}" y="${height - 5}" text-anchor="middle" font-size="10" fill="var(--muted)">${label}</text>`;
  });

  // Legend
  svg += `<g transform="translate(${width - 100}, 10)">`;
  svg += `<circle cx="0" cy="0" r="4" fill="${color}"/><text x="8" y="4" font-size="10" fill="var(--text)">健康度</text>`;
  svg += `<rect x="60" y="-3" width="8" height="6" fill="${dangerColor}" opacity="0.3" rx="1"/><text x="72" y="4" font-size="10" fill="var(--text)">异常</text>`;
  svg += `</g>`;

  svg += '</svg>';
  container.innerHTML = svg;
}

// Generate mock trend data for testing
export function generateMockTrend(days = 7) {
  const trend = [];
  let health = 82;
  for (let i = 1; i <= days; i++) {
    const change = (Math.random() - 0.4) * 10;
    health = Math.max(30, Math.min(100, health + change));
    trend.push({
      day: i,
      health: Math.round(health),
      anomalies: Math.random() > 0.7 ? 1 : 0,
    });
  }
  return trend;
}
