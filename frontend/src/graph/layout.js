// ============ FORCE LAYOUT ============
import { state, zoomPan } from '../state.js';
import { renderCanvas } from '../ui/render.js';
import { updateSVGDimensions } from '../ui/render.js';

function QuadTree(boundary, capacity) {
  this.boundary = boundary;
  this.capacity = capacity || 4;
  this.points = [];
  this.divided = false;
  this.nw = this.ne = this.sw = this.se = null;
  this.mass = 0;
  this.cx = 0;
  this.cy = 0;
}

QuadTree.prototype.insert = function(point) {
  if (!this._contains(point)) return false;
  if (!this.divided && this.points.length < this.capacity) {
    this.points.push(point);
    return true;
  }
  if (!this.divided) this._subdivide();
  if (this.nw.insert(point)) return true;
  if (this.ne.insert(point)) return true;
  if (this.sw.insert(point)) return true;
  if (this.se.insert(point)) return true;
  return false;
};

QuadTree.prototype._contains = function(point) {
  return point.x >= this.boundary.x && point.x < this.boundary.x + this.boundary.width &&
         point.y >= this.boundary.y && point.y < this.boundary.y + this.boundary.height;
};

QuadTree.prototype._subdivide = function() {
  var x = this.boundary.x, y = this.boundary.y;
  var w = this.boundary.width / 2, h = this.boundary.height / 2;
  this.nw = new QuadTree({x: x, y: y, width: w, height: h}, this.capacity);
  this.ne = new QuadTree({x: x + w, y: y, width: w, height: h}, this.capacity);
  this.sw = new QuadTree({x: x, y: y + h, width: w, height: h}, this.capacity);
  this.se = new QuadTree({x: x + w, y: y + h, width: w, height: h}, this.capacity);
  this.divided = true;
  for (var i = 0; i < this.points.length; i++) {
    var p = this.points[i];
    this.nw.insert(p) || this.ne.insert(p) || this.sw.insert(p) || this.se.insert(p);
  }
  this.points = [];
};

QuadTree.prototype.updateMass = function() {
  if (!this.divided) {
    this.mass = this.points.length;
    var sx = 0, sy = 0;
    for (var i = 0; i < this.points.length; i++) {
      sx += this.points[i].x;
      sy += this.points[i].y;
    }
    this.cx = this.mass > 0 ? sx / this.mass : this.boundary.x + this.boundary.width / 2;
    this.cy = this.mass > 0 ? sy / this.mass : this.boundary.y + this.boundary.height / 2;
    return;
  }
  this.nw.updateMass();
  this.ne.updateMass();
  this.sw.updateMass();
  this.se.updateMass();
  this.mass = this.nw.mass + this.ne.mass + this.sw.mass + this.se.mass;
  this.cx = this.mass > 0 ? (this.nw.cx * this.nw.mass + this.ne.cx * this.ne.mass + this.sw.cx * this.sw.mass + this.se.cx * this.se.mass) / this.mass : 0;
  this.cy = this.mass > 0 ? (this.nw.cy * this.nw.mass + this.ne.cy * this.ne.mass + this.sw.cy * this.sw.mass + this.se.cy * this.se.mass) / this.mass : 0;
};

QuadTree.prototype.repulsion = function(node, theta) {
  if (this.mass === 0) return;
  var dx = this.cx - node.x;
  var dy = this.cy - node.y;
  var dist = Math.sqrt(dx * dx + dy * dy) || 1;
  if (!this.divided) {
    for (var i = 0; i < this.points.length; i++) {
      var p = this.points[i];
      if (p === node) continue;
      var pdx = p.x - node.x;
      var pdy = p.y - node.y;
      var pdist = Math.sqrt(pdx * pdx + pdy * pdy);
      if (pdist < 1) { pdist = 1; pdx = Math.random() - 0.5; pdy = Math.random() - 0.5; }
      var force = 28000 / (pdist * pdist);
      var fx = (pdx / pdist) * force;
      var fy = (pdy / pdist) * force;
      node.vx -= fx; node.vy -= fy;
    }
    return;
  }
  if (this.boundary.width / dist < theta) {
    var force = 28000 * this.mass / (dist * dist);
    var fx = (dx / dist) * force;
    var fy = (dy / dist) * force;
    node.vx -= fx; node.vy -= fy;
    return;
  }
  this.nw.repulsion(node, theta);
  this.ne.repulsion(node, theta);
  this.sw.repulsion(node, theta);
  this.se.repulsion(node, theta);
};

function tickLayout() {
  var nodes = state.nodes, edges = state.edges;
  if (nodes.length === 0) return;
  var maxV = 0;

  for (var i = 0; i < nodes.length; i++) {
    var n = nodes[i];
    n.vx *= 0.94; n.vy *= 0.94;
  }

  // Repulsion (Barnes-Hut QuadTree)
  var boundary = { x: -state.svgW, y: -state.svgH, width: state.svgW * 3, height: state.svgH * 3 };
  var qt = new QuadTree(boundary, 4);
  for (var i = 0; i < nodes.length; i++) {
    qt.insert(nodes[i]);
  }
  qt.updateMass();
  for (var i = 0; i < nodes.length; i++) {
    qt.repulsion(nodes[i], 0.5);
  }

  // Collision resolution
  for (var i = 0; i < nodes.length; i++) {
    for (var j = i + 1; j < nodes.length; j++) {
      var dx = nodes[j].x - nodes[i].x;
      var dy = nodes[j].y - nodes[i].y;
      var dist = Math.sqrt(dx * dx + dy * dy) || 1;
      var minDist = nodes[i].radius + nodes[j].radius + 12;
      if (dist < minDist) {
        var overlap = (minDist - dist) * 0.5;
        var ox = (dx / dist) * overlap;
        var oy = (dy / dist) * overlap;
        if (!nodes[i].fixed) { nodes[i].x -= ox; nodes[i].y -= oy; }
        if (!nodes[j].fixed) { nodes[j].x += ox; nodes[j].y += oy; }
      }
    }
  }

  // Attraction (spring)
  edges.forEach(function(e) {
    var a = null, b = null;
    for (var i = 0; i < nodes.length; i++) {
      if (nodes[i].id === e.from) a = nodes[i];
      if (nodes[i].id === e.to) b = nodes[i];
    }
    if (!a || !b) return;
    var dx = b.x - a.x, dy = b.y - a.y;
    var dist = Math.sqrt(dx * dx + dy * dy) || 1;
    var targetDist = 180;
    var force = (dist - targetDist) * 0.03;
    var fx = (dx / dist) * force, fy = (dy / dist) * force;
    a.vx += fx; a.vy += fy;
    b.vx -= fx; b.vy -= fy;
  });

  // Center gravity
  nodes.forEach(function(n) {
    n.vx += (state.svgW / 2 - n.x) * 0.001;
    n.vy += (state.svgH / 2 - n.y) * 0.001;
  });

  // Apply
  var pad = 70;
  nodes.forEach(function(n) {
    if (n.fixed) return;
    n.x += n.vx; n.y += n.vy;
    n.x = Math.max(pad, Math.min(state.svgW - pad, n.x));
    n.y = Math.max(pad, Math.min(state.svgH - pad, n.y));
    var v = Math.sqrt(n.vx * n.vx + n.vy * n.vy);
    if (v > maxV) maxV = v;
  });

  // Convergence check
  if (maxV < 0.15) {
    state.convergeCount++;
    if (state.convergeCount > 60) {
      stopAnimation();
    }
  } else {
    state.convergeCount = 0;
  }
}

function startAnimation() {
  if (state.animRunning) return;
  state.animRunning = true;
  state.convergeCount = 0;
  function loop() {
    if (!state.animRunning) return;
    tickLayout();
    renderCanvas();
    state.animFrame = requestAnimationFrame(loop);
  }
  state.animFrame = requestAnimationFrame(loop);
}

function stopAnimation() {
  state.animRunning = false;
  if (state.animFrame) cancelAnimationFrame(state.animFrame);
}

function debounce(fn, delay) {
  var timer = null;
  return function() {
    var args = arguments;
    var self = this;
    clearTimeout(timer);
    timer = setTimeout(function() {
      fn.apply(self, args);
    }, delay);
  };
}

function throttle(fn, limit) {
  var last = 0;
  return function() {
    var now = Date.now();
    if (now - last >= limit) {
      last = now;
      fn.apply(this, arguments);
    }
  };
}

function _onWindowResize() {
  updateSVGDimensions();
  if (state.nodes.length > 0) startAnimation();
}

var onWindowResize = debounce(_onWindowResize, 200);

function applyZoomPan(svg) {
  if (!svg) return;
  var transform = 'translate(' + zoomPan.panX + ',' + zoomPan.panY + ') scale(' + zoomPan.scale + ')';
  var g = svg.querySelector('.zoom-pan-group');
  if (!g) {
    g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.setAttribute('class', 'zoom-pan-group');
    // Move all existing children into g
    while (svg.firstChild) {
      if (svg.firstChild.nodeType === 1 && svg.firstChild.tagName === 'g' && svg.firstChild.getAttribute('class') === 'zoom-pan-group') break;
      g.appendChild(svg.firstChild);
    }
    svg.appendChild(g);
  }
  g.setAttribute('transform', transform);
}

export { tickLayout, startAnimation, stopAnimation, onWindowResize, applyZoomPan, debounce, throttle };
