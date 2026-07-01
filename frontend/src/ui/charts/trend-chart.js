// ============ TREND CHART (Pure SVG) ============
// Area chart with smooth curve and 7/30 day view toggle

const COLORS = {
  area: 'rgba(74, 124, 74, 0.15)',
  line: '#4A7C4A',
  grid: '#D5CCBC',
  text: '#5C5448',
  danger: '#C0392B',
  warn: '#F39C12',
};

function catmullRom2bezier(points) {
  var result = [];
  for (var i = 0; i < points.length - 1; i++) {
    var p0 = i === 0 ? points[0] : points[i - 1];
    var p1 = points[i];
    var p2 = points[i + 1];
    var p3 = i + 2 < points.length ? points[i + 2] : p2;
    var cp1x = p1.x + (p2.x - p0.x) / 6;
    var cp1y = p1.y + (p2.y - p0.y) / 6;
    var cp2x = p2.x - (p3.x - p1.x) / 6;
    var cp2y = p2.y - (p3.y - p1.y) / 6;
    result.push({ cp1: { x: cp1x, y: cp1y }, cp2: { x: cp2x, y: cp2y }, end: { x: p2.x, y: p2.y } });
  }
  return result;
}

export function renderTrendChart(container, dataPoints, options) {
  if (!container) return;

  options = options || {};
  var width = options.width || 400;
  var height = options.height || 220;
  var margin = options.margin || { top: 20, right: 20, bottom: 30, left: 40 };
  var innerWidth = width - margin.left - margin.right;
  var innerHeight = height - margin.top - margin.bottom;

  if (!dataPoints || dataPoints.length === 0) {
    container.innerHTML = '<div style="text-align:center;color:var(--muted);padding:40px;font-size:0.85rem;">暂无数据</div>';
    return;
  }

  var maxHealth = 100;
  var xStep = dataPoints.length > 1 ? innerWidth / (dataPoints.length - 1) : innerWidth / 2;

  function xScale(i) { return margin.left + i * xStep; }
  function yScale(h) { return margin.top + innerHeight - (h / maxHealth) * innerHeight; }

  var svg = '<svg viewBox="0 0 ' + width + ' ' + height + '" style="width:100%;height:auto;display:block;">';

  // Grid lines
  for (var i = 0; i <= 5; i++) {
    var y = margin.top + (innerHeight / 5) * i;
    var val = Math.round(100 - (100 / 5) * i);
    svg += '<line x1="' + margin.left + '" y1="' + y + '" x2="' + (width - margin.right) + '" y2="' + y + '" stroke="' + COLORS.grid + '" stroke-width="0.5"/>';
    svg += '<text x="' + (margin.left - 8) + '" y="' + (y + 4) + '" text-anchor="end" font-size="10" fill="' + COLORS.text + '">' + val + '</text>';
  }

  // Area path
  var points = [];
  for (var i = 0; i < dataPoints.length; i++) {
    points.push({ x: xScale(i), y: yScale(dataPoints[i].health) });
  }

  if (points.length > 1) {
    var areaPath = 'M' + points[0].x + ',' + (margin.top + innerHeight);
    var curves = catmullRom2bezier(points);
    areaPath += ' L' + points[0].x + ',' + points[0].y;
    for (var i = 0; i < curves.length; i++) {
      var c = curves[i];
      areaPath += ' C' + c.cp1.x + ',' + c.cp1.y + ' ' + c.cp2.x + ',' + c.cp2.y + ' ' + c.end.x + ',' + c.end.y;
    }
    areaPath += ' L' + points[points.length - 1].x + ',' + (margin.top + innerHeight) + ' Z';
    svg += '<path d="' + areaPath + '" fill="' + COLORS.area + '" stroke="none"/>';

    // Line path
    var linePath = 'M' + points[0].x + ',' + points[0].y;
    for (var i = 0; i < curves.length; i++) {
      var c = curves[i];
      linePath += ' C' + c.cp1.x + ',' + c.cp1.y + ' ' + c.cp2.x + ',' + c.cp2.y + ' ' + c.end.x + ',' + c.end.y;
    }
    svg += '<path d="' + linePath + '" fill="none" stroke="' + COLORS.line + '" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>';
  } else if (points.length === 1) {
    svg += '<circle cx="' + points[0].x + '" cy="' + points[0].y + '" r="4" fill="' + COLORS.line + '"/>';
  }

  // Data points
  for (var i = 0; i < dataPoints.length; i++) {
    var cx = xScale(i);
    var cy = yScale(dataPoints[i].health);
    var color = dataPoints[i].health >= 80 ? COLORS.line : dataPoints[i].health >= 50 ? COLORS.warn : COLORS.danger;
    svg += '<circle cx="' + cx + '" cy="' + cy + '" r="4" fill="' + color + '" stroke="#fff" stroke-width="2"/>';
  }

  // X-axis labels
  for (var i = 0; i < dataPoints.length; i++) {
    if (dataPoints.length <= 10 || i % Math.ceil(dataPoints.length / 6) === 0 || i === dataPoints.length - 1) {
      var label = dataPoints[i].label || dataPoints[i].day || (i + 1);
      svg += '<text x="' + xScale(i) + '" y="' + (height - 6) + '" text-anchor="middle" font-size="10" fill="' + COLORS.text + '">' + label + '</text>';
    }
  }

  svg += '</svg>';
  container.innerHTML = svg;
}

export function generateMockTrendData(days) {
  var trend = [];
  var health = 82;
  for (var i = 1; i <= days; i++) {
    var change = (Math.random() - 0.4) * 10;
    health = Math.max(30, Math.min(100, health + change));
    var d = new Date();
    d.setDate(d.getDate() - (days - i));
    trend.push({
      day: i,
      label: (d.getMonth() + 1) + '/' + d.getDate(),
      health: Math.round(health),
    });
  }
  return trend;
}

export function createTrendViewToggle(container, onChange) {
  var wrap = document.createElement('div');
  wrap.style.cssText = 'display:flex;gap:4px;justify-content:center;margin-bottom:10px;';
  var btn7 = document.createElement('button');
  btn7.textContent = '7日';
  btn7.style.cssText = 'padding:4px 10px;border:1px solid var(--rule);border-radius:100px;background:#fff;cursor:pointer;font-size:0.75rem;';
  var btn30 = document.createElement('button');
  btn30.textContent = '30日';
  btn30.style.cssText = 'padding:4px 10px;border:1px solid var(--rule);border-radius:100px;background:#fff;cursor:pointer;font-size:0.75rem;';

  function setActive(days) {
    if (days === 7) {
      btn7.style.background = 'var(--accent)';
      btn7.style.color = '#fff';
      btn7.style.borderColor = 'var(--accent)';
      btn30.style.background = '#fff';
      btn30.style.color = 'var(--ink2)';
      btn30.style.borderColor = 'var(--rule)';
    } else {
      btn30.style.background = 'var(--accent)';
      btn30.style.color = '#fff';
      btn30.style.borderColor = 'var(--accent)';
      btn7.style.background = '#fff';
      btn7.style.color = 'var(--ink2)';
      btn7.style.borderColor = 'var(--rule)';
    }
  }

  btn7.onclick = function() { setActive(7); if (onChange) onChange(7); };
  btn30.onclick = function() { setActive(30); if (onChange) onChange(30); };

  wrap.appendChild(btn7);
  wrap.appendChild(btn30);
  setActive(7);
  return wrap;
}
