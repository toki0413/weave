// ============ MEMORY NEBULA 3D RENDERER ============
// Native WebGL — no Three.js. Returns controller with destroy().

import {
  createShader, createProgram, createBuffer, resizeCanvasToDisplaySize,
  BASIC_VERTEX_SHADER, BASIC_FRAGMENT_SHADER,
  LINE_VERTEX_SHADER, LINE_FRAGMENT_SHADER,
  PARTICLE_VERTEX_SHADER, PARTICLE_FRAGMENT_SHADER,
  mat4Create, mat4Perspective, mat4LookAt, mat4Multiply,
  mat4Invert, mat4Transpose, mat4FromTranslation, mat4FromScaling,
  createIcosahedron,
  degToRad, lerp, clamp
} from './webgl-utils.js';

// Node type colors (RGBA 0-1)
var TYPE_COLORS = {
  person: [0.24, 0.44, 0.66, 1.0],   // 蓝色
  event:  [0.29, 0.49, 0.29, 1.0],   // 绿色
  place:  [0.72, 0.42, 0.30, 1.0],   // 橙色
  time:   [0.48, 0.33, 0.58, 1.0],   // 紫色
  item:   [0.55, 0.48, 0.44, 1.0],   // 棕色
  self:   [0.18, 0.35, 0.17, 1.0],   // 深绿
  anon:   [0.72, 0.53, 0.04, 1.0],   // 金色
};

var EMOTION_COLORS = {
  positive: [0.29, 0.49, 0.29, 1.0], // 绿色
  negative: [0.78, 0.36, 0.36, 1.0], // 红色
  neutral:  [0.55, 0.48, 0.44, 1.0], // 棕色
};

var DAYS_MS = 24 * 60 * 60 * 1000;

export function initMemoryNebula(container, rawNodes, sessions) {
  // ====== Feature detection & graceful degradation ======
  var canvas = document.createElement('canvas');
  canvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;display:block;';
  var gl = canvas.getContext('webgl', { antialias: true, alpha: false, preserveDrawingBuffer: false });
  if (!gl) {
    console.warn('WebGL not supported, falling back to 2D');
    return null;
  }

  container.style.position = 'relative';
  container.appendChild(canvas);

  // ====== Data preparation ======
  var now = Date.now();
  var nodes = buildNodeData(rawNodes, sessions, now);
  var edges = buildEdges(nodes);

  // ====== Shader programs ======
  var sphereProg = createProgram(gl,
    createShader(gl, gl.VERTEX_SHADER, BASIC_VERTEX_SHADER),
    createShader(gl, gl.FRAGMENT_SHADER, BASIC_FRAGMENT_SHADER)
  );
  var lineProg = createProgram(gl,
    createShader(gl, gl.VERTEX_SHADER, LINE_VERTEX_SHADER),
    createShader(gl, gl.FRAGMENT_SHADER, LINE_FRAGMENT_SHADER)
  );
  var particleProg = createProgram(gl,
    createShader(gl, gl.VERTEX_SHADER, PARTICLE_VERTEX_SHADER),
    createShader(gl, gl.FRAGMENT_SHADER, PARTICLE_FRAGMENT_SHADER)
  );

  if (!sphereProg || !lineProg || !particleProg) {
    console.error('Shader compilation failed');
    return null;
  }

  // ====== Geometry ======
  var sphereGeo = createIcosahedron(1.0);
  var spherePosBuf = createBuffer(gl, sphereGeo.positions);
  var sphereNormBuf = createBuffer(gl, sphereGeo.normals);
  var sphereCount = sphereGeo.count;

  // Line buffer (dynamic, updated each frame if edges change)
  var linePositions = new Float32Array(Math.max(edges.length * 6, 12));
  var lineBuf = createBuffer(gl, linePositions, gl.ARRAY_BUFFER, gl.DYNAMIC_DRAW);

  // Particle background
  var particleCount = 800;
  var particlePositions = new Float32Array(particleCount * 3);
  var particleSizes = new Float32Array(particleCount);
  for (var i = 0; i < particleCount; i++) {
    particlePositions[i*3]   = (Math.random() - 0.5) * 200;
    particlePositions[i*3+1] = (Math.random() - 0.5) * 120;
    particlePositions[i*3+2] = (Math.random() - 0.5) * 150 - 30;
    particleSizes[i] = 1.5 + Math.random() * 3;
  }
  var particlePosBuf = createBuffer(gl, particlePositions);
  var particleSizeBuf = createBuffer(gl, particleSizes);

  // ====== Camera / Orbit state ======
  var camera = {
    distance: 70,
    theta: 0.8,
    phi: 0.5,
    target: [0, 0, -30],
    minD: 15,
    maxD: 120,
    fovy: degToRad(60),
    near: 0.1,
    far: 300,
  };

  var projMatrix = mat4Create();
  var viewMatrix = mat4Create();
  var modelMatrix = mat4Create();
  var modelViewMatrix = mat4Create();
  var normalMatrix = mat4Create();
  var tempMatrix = mat4Create();

  // ====== Interaction state ======
  var isDragging = false;
  var lastMouse = { x: 0, y: 0 };
  var mouseDownPos = { x: 0, y: 0 };
  var isFlying = false;
  var flyProgress = 0;
  var flySpeed = 0.0003;
  var selectedNode = null;
  var hoverNode = null;
  var emotionMode = false; // green/red based on emotion
  var timeFilter = 'all'; // '7', '30', 'all'
  var onNodeClick = null; // external callback

  // FPS counter
  var fps = { value: 0, frames: 0, lastTime: performance.now() };
  var fpsEl = document.createElement('div');
  fpsEl.style.cssText = 'position:absolute;top:8px;left:8px;font-size:11px;font-family:monospace;color:rgba(255,255,255,0.5);pointer-events:none;z-index:10;';
  container.appendChild(fpsEl);

  // ====== Render helpers ======
  function updateCamera() {
    var eye = [
      camera.target[0] + camera.distance * Math.sin(camera.phi) * Math.cos(camera.theta),
      camera.target[1] + camera.distance * Math.cos(camera.phi),
      camera.target[2] + camera.distance * Math.sin(camera.phi) * Math.sin(camera.theta)
    ];
    mat4LookAt(viewMatrix, eye, camera.target, [0, 1, 0]);
  }

  function updateProjection() {
    var aspect = canvas.width / canvas.height;
    mat4Perspective(projMatrix, camera.fovy, aspect, camera.near, camera.far);
  }

  function setMatrices(program, modelMat) {
    var glP = gl;
    mat4Multiply(modelViewMatrix, viewMatrix, modelMat);
    glP.uniformMatrix4fv(glP.getUniformLocation(program, 'uModelViewMatrix'), false, modelViewMatrix);
    glP.uniformMatrix4fv(glP.getUniformLocation(program, 'uProjectionMatrix'), false, projMatrix);
    // Normal matrix: transpose(inverse(modelView))
    mat4Invert(tempMatrix, modelViewMatrix);
    if (tempMatrix) {
      mat4Transpose(normalMatrix, tempMatrix);
      glP.uniformMatrix4fv(glP.getUniformLocation(program, 'uNormalMatrix'), false, normalMatrix);
    }
  }

  function getFilteredNodes() {
    if (timeFilter === 'all') return nodes;
    var days = parseInt(timeFilter, 10);
    var cutoff = now - days * DAYS_MS;
    return nodes.filter(function(n) { return n.date >= cutoff; });
  }

  function getNodeColor(n) {
    if (emotionMode && n.emotion) {
      var ec = EMOTION_COLORS[n.emotion] || EMOTION_COLORS.neutral;
      return ec;
    }
    return TYPE_COLORS[n.type] || TYPE_COLORS.item;
  }

  function drawSphere(x, y, z, radius, color, opacity) {
    mat4FromTranslation(modelMatrix, [x, y, z]);
    mat4FromScaling(tempMatrix, [radius, radius, radius]);
    mat4Multiply(modelMatrix, modelMatrix, tempMatrix);
    setMatrices(sphereProg, modelMatrix);

    gl.uniform4f(gl.getUniformLocation(sphereProg, 'uColor'), color[0], color[1], color[2], color[3]);
    gl.uniform3f(gl.getUniformLocation(sphereProg, 'uLightDirection'), 0.5, 1.0, 0.5);
    gl.uniform1f(gl.getUniformLocation(sphereProg, 'uFogNear'), 40);
    gl.uniform1f(gl.getUniformLocation(sphereProg, 'uFogFar'), 120);
    gl.uniform3f(gl.getUniformLocation(sphereProg, 'uFogColor'), 0.04, 0.035, 0.03);
    gl.uniform1f(gl.getUniformLocation(sphereProg, 'uOpacity'), opacity);

    gl.bindBuffer(gl.ARRAY_BUFFER, spherePosBuf);
    var aPos = gl.getAttribLocation(sphereProg, 'aPosition');
    gl.enableVertexAttribArray(aPos);
    gl.vertexAttribPointer(aPos, 3, gl.FLOAT, false, 0, 0);

    gl.bindBuffer(gl.ARRAY_BUFFER, sphereNormBuf);
    var aNorm = gl.getAttribLocation(sphereProg, 'aNormal');
    gl.enableVertexAttribArray(aNorm);
    gl.vertexAttribPointer(aNorm, 3, gl.FLOAT, false, 0, 0);

    gl.drawArrays(gl.TRIANGLES, 0, sphereCount);

    gl.disableVertexAttribArray(aPos);
    gl.disableVertexAttribArray(aNorm);
  }

  function drawLines(visibleNodes) {
    if (edges.length === 0) return;
    var idx = 0;
    var nodeSet = {};
    for (var i = 0; i < visibleNodes.length; i++) { nodeSet[visibleNodes[i].id] = true; }

    for (var e = 0; e < edges.length; e++) {
      var edge = edges[e];
      if (!nodeSet[edge.from] || !nodeSet[edge.to]) continue;
      var n1 = nodes.find(function(n) { return n.id === edge.from; });
      var n2 = nodes.find(function(n) { return n.id === edge.to; });
      if (!n1 || !n2) continue;
      linePositions[idx++] = n1.x; linePositions[idx++] = n1.y; linePositions[idx++] = n1.z;
      linePositions[idx++] = n2.x; linePositions[idx++] = n2.y; linePositions[idx++] = n2.z;
    }
    if (idx === 0) return;

    gl.useProgram(lineProg);
    gl.uniformMatrix4fv(gl.getUniformLocation(lineProg, 'uProjectionMatrix'), false, projMatrix);
    gl.uniformMatrix4fv(gl.getUniformLocation(lineProg, 'uModelViewMatrix'), false, viewMatrix);

    gl.bindBuffer(gl.ARRAY_BUFFER, lineBuf);
    gl.bufferData(gl.ARRAY_BUFFER, linePositions.subarray(0, idx), gl.DYNAMIC_DRAW);
    var aPos = gl.getAttribLocation(lineProg, 'aPosition');
    gl.enableVertexAttribArray(aPos);
    gl.vertexAttribPointer(aPos, 3, gl.FLOAT, false, 0, 0);

    // Draw all lines with a subtle color
    gl.uniform4f(gl.getUniformLocation(lineProg, 'uColor'), 0.6, 0.55, 0.5, 0.25);
    gl.uniform1f(gl.getUniformLocation(lineProg, 'uOpacity'), 0.6);
    gl.drawArrays(gl.LINES, 0, idx / 3);
    gl.disableVertexAttribArray(aPos);
  }

  function drawParticles() {
    gl.useProgram(particleProg);
    gl.uniformMatrix4fv(gl.getUniformLocation(particleProg, 'uProjectionMatrix'), false, projMatrix);
    gl.uniformMatrix4fv(gl.getUniformLocation(particleProg, 'uModelViewMatrix'), false, viewMatrix);
    gl.uniform4f(gl.getUniformLocation(particleProg, 'uColor'), 0.9, 0.85, 0.75, 0.35);

    gl.bindBuffer(gl.ARRAY_BUFFER, particlePosBuf);
    var aPos = gl.getAttribLocation(particleProg, 'aPosition');
    gl.enableVertexAttribArray(aPos);
    gl.vertexAttribPointer(aPos, 3, gl.FLOAT, false, 0, 0);

    gl.bindBuffer(gl.ARRAY_BUFFER, particleSizeBuf);
    var aSize = gl.getAttribLocation(particleProg, 'aSize');
    gl.enableVertexAttribArray(aSize);
    gl.vertexAttribPointer(aSize, 1, gl.FLOAT, false, 0, 0);

    gl.drawArrays(gl.POINTS, 0, particleCount);

    gl.disableVertexAttribArray(aPos);
    gl.disableVertexAttribArray(aSize);
  }

  // ====== Ray picking ======
  function getRay(x, y) {
    // NDC -> clip -> eye -> world ray
    var nx = (x / canvas.width) * 2 - 1;
    var ny = -((y / canvas.height) * 2 - 1);
    var invProj = mat4Create();
    mat4Invert(invProj, projMatrix);
    var invView = mat4Create();
    mat4Invert(invView, viewMatrix);
    if (!invProj || !invView) return null;

    var eye = [invView[12], invView[13], invView[14]];
    var p1 = [nx, ny, -1, 1];
    var p2 = [nx, ny, 1, 1];
    // unproject p1
    var u1 = [invProj[0]*p1[0]+invProj[4]*p1[1]+invProj[8]*p1[2]+invProj[12]*p1[3],
              invProj[1]*p1[0]+invProj[5]*p1[1]+invProj[9]*p1[2]+invProj[13]*p1[3],
              invProj[2]*p1[0]+invProj[6]*p1[1]+invProj[10]*p1[2]+invProj[14]*p1[3],
              invProj[3]*p1[0]+invProj[7]*p1[1]+invProj[11]*p1[2]+invProj[15]*p1[3]];
    u1[0] /= u1[3]; u1[1] /= u1[3]; u1[2] /= u1[3];
    var w1 = [invView[0]*u1[0]+invView[4]*u1[1]+invView[8]*u1[2]+invView[12],
              invView[1]*u1[0]+invView[5]*u1[1]+invView[9]*u1[2]+invView[13],
              invView[2]*u1[0]+invView[6]*u1[1]+invView[10]*u1[2]+invView[14]];
    var u2 = [invProj[0]*p2[0]+invProj[4]*p2[1]+invProj[8]*p2[2]+invProj[12]*p2[3],
              invProj[1]*p2[0]+invProj[5]*p2[1]+invProj[9]*p2[2]+invProj[13]*p2[3],
              invProj[2]*p2[0]+invProj[6]*p2[1]+invProj[10]*p2[2]+invProj[14]*p2[3],
              invProj[3]*p2[0]+invProj[7]*p2[1]+invProj[11]*p2[2]+invProj[15]*p2[3]];
    u2[0] /= u2[3]; u2[1] /= u2[3]; u2[2] /= u2[3];
    var w2 = [invView[0]*u2[0]+invView[4]*u2[1]+invView[8]*u2[2]+invView[12],
              invView[1]*u2[0]+invView[5]*u2[1]+invView[9]*u2[2]+invView[13],
              invView[2]*u2[0]+invView[6]*u2[1]+invView[10]*u2[2]+invView[14]];
    var dir = [w2[0]-w1[0], w2[1]-w1[1], w2[2]-w1[2]];
    var dlen = Math.sqrt(dir[0]*dir[0]+dir[1]*dir[1]+dir[2]*dir[2]);
    if (dlen > 0) { dir[0] /= dlen; dir[1] /= dlen; dir[2] /= dlen; }
    return { origin: eye, dir: dir };
  }

  function pickNode(ndcX, ndcY) {
    var ray = getRay(ndcX, ndcY);
    if (!ray) return null;
    var visible = getFilteredNodes();
    var best = null;
    var bestT = Infinity;
    for (var i = 0; i < visible.length; i++) {
      var n = visible[i];
      var oc = [ray.origin[0]-n.x, ray.origin[1]-n.y, ray.origin[2]-n.z];
      var b = 2 * (oc[0]*ray.dir[0] + oc[1]*ray.dir[1] + oc[2]*ray.dir[2]);
      var c = oc[0]*oc[0] + oc[1]*oc[1] + oc[2]*oc[2] - n.radius*n.radius;
      var disc = b*b - 4*c;
      if (disc >= 0) {
        var t = (-b - Math.sqrt(disc)) / 2;
        if (t > 0 && t < bestT) { bestT = t; best = n; }
      }
    }
    return best;
  }

  // ====== Animation loop ======
  var animId = null;
  var lastFrameTime = performance.now();
  var time = 0;

  function renderFrame() {
    var nowTime = performance.now();
    var dt = nowTime - lastFrameTime;
    lastFrameTime = nowTime;
    time += dt * 0.001;

    // FPS
    fps.frames++;
    if (nowTime - fps.lastTime >= 1000) {
      fps.value = fps.frames;
      fps.frames = 0;
      fps.lastTime = nowTime;
      fpsEl.textContent = 'FPS: ' + fps.value;
    }

    // Resize
    if (resizeCanvasToDisplaySize(canvas, 2)) {
      gl.viewport(0, 0, canvas.width, canvas.height);
      updateProjection();
    }

    // Flying animation
    if (isFlying) {
      flyProgress += dt * flySpeed;
      if (flyProgress >= 1) {
        flyProgress = 0;
        isFlying = false;
      }
      // Fly from near (z=0) to far (z=-100)
      var flyZ = lerp(0, -100, flyProgress);
      camera.target[2] = flyZ;
      camera.distance = lerp(50, 80, Math.sin(flyProgress * Math.PI));
      // Pause at key nodes
      if (onNodeClick) {
        for (var i = 0; i < nodes.length; i++) {
          var n = nodes[i];
          if (Math.abs(n.z - flyZ) < 5 && n.narrative && !n._shown) {
            n._shown = true;
            onNodeClick(n);
          }
        }
      }
    }

    // Clear
    gl.clearColor(0.04, 0.035, 0.03, 1.0);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.enable(gl.DEPTH_TEST);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

    updateCamera();

    var visibleNodes = getFilteredNodes();

    // Draw particles (background nebula)
    gl.disable(gl.DEPTH_TEST);
    drawParticles();
    gl.enable(gl.DEPTH_TEST);

    // Draw edges
    drawLines(visibleNodes);

    // Draw nodes
    gl.useProgram(sphereProg);
    var useLOD = visibleNodes.length > 100;
    for (var i = 0; i < visibleNodes.length; i++) {
      var n = visibleNodes[i];
      // Distance-based opacity & LOD
      var distToCam = Math.sqrt(
        (n.x - camera.target[0])*(n.x - camera.target[0]) +
        (n.y - camera.target[1])*(n.y - camera.target[1]) +
        (n.z - camera.target[2])*(n.z - camera.target[2])
      );
      var opacity = 1.0;
      if (distToCam > 60) {
        opacity = lerp(1.0, 0.2, clamp((distToCam - 60) / 60, 0, 1));
      }
      // Far nodes: smaller
      var radius = n.radius;
      if (useLOD && distToCam > 80) {
        radius *= 0.6;
      }
      var color = getNodeColor(n);
      if (n === selectedNode) {
        color = [1.0, 0.9, 0.5, 1.0]; // highlight gold
      } else if (n === hoverNode) {
        color = [color[0]*1.2, color[1]*1.2, color[2]*1.2, 1.0];
      }
      drawSphere(n.x, n.y, n.z, radius, color, opacity);
    }

    animId = requestAnimationFrame(renderFrame);
  }

  // ====== Event handlers ======
  function onMouseDown(e) {
    isDragging = true;
    lastMouse.x = e.clientX;
    lastMouse.y = e.clientY;
    mouseDownPos.x = e.clientX;
    mouseDownPos.y = e.clientY;
  }

  function onMouseMove(e) {
    var rect = canvas.getBoundingClientRect();
    var mx = e.clientX - rect.left;
    var my = e.clientY - rect.top;
    if (isDragging) {
      var dx = e.clientX - lastMouse.x;
      var dy = e.clientY - lastMouse.y;
      camera.theta += dx * 0.005;
      camera.phi = clamp(camera.phi - dy * 0.005, 0.1, Math.PI - 0.1);
      lastMouse.x = e.clientX;
      lastMouse.y = e.clientY;
    } else {
      // Hover detection
      var pick = pickNode(mx * (canvas.width / rect.width), my * (canvas.height / rect.height));
      hoverNode = pick || null;
      canvas.style.cursor = hoverNode ? 'pointer' : 'grab';
    }
  }

  function onMouseUp(e) {
    isDragging = false;
    var dx = e.clientX - mouseDownPos.x;
    var dy = e.clientY - mouseDownPos.y;
    if (Math.abs(dx) < 5 && Math.abs(dy) < 5) {
      // Click: node selection
      var rect = canvas.getBoundingClientRect();
      var mx = e.clientX - rect.left;
      var my = e.clientY - rect.top;
      var pick = pickNode(mx * (canvas.width / rect.width), my * (canvas.height / rect.height));
      if (pick) {
        selectedNode = pick;
        if (onNodeClick) onNodeClick(pick);
      } else {
        selectedNode = null;
      }
    }
  }

  function onWheel(e) {
    e.preventDefault();
    var delta = e.deltaY * 0.05;
    camera.distance = clamp(camera.distance + delta, camera.minD, camera.maxD);
  }

  var touchState = { dist: 0, lastX: 0, lastY: 0 };

  function onTouchStart(e) {
    if (e.touches.length === 1) {
      lastMouse.x = e.touches[0].clientX;
      lastMouse.y = e.touches[0].clientY;
      mouseDownPos.x = e.touches[0].clientX;
      mouseDownPos.y = e.touches[0].clientY;
      isDragging = true;
    } else if (e.touches.length === 2) {
      var dx = e.touches[0].clientX - e.touches[1].clientX;
      var dy = e.touches[0].clientY - e.touches[1].clientY;
      touchState.dist = Math.sqrt(dx*dx + dy*dy);
      isDragging = false;
    }
  }

  function onTouchMove(e) {
    e.preventDefault();
    if (e.touches.length === 1 && isDragging) {
      var dx = e.touches[0].clientX - lastMouse.x;
      var dy = e.touches[0].clientY - lastMouse.y;
      camera.theta += dx * 0.005;
      camera.phi = clamp(camera.phi - dy * 0.005, 0.1, Math.PI - 0.1);
      lastMouse.x = e.touches[0].clientX;
      lastMouse.y = e.touches[0].clientY;
    } else if (e.touches.length === 2) {
      var dx = e.touches[0].clientX - e.touches[1].clientX;
      var dy = e.touches[0].clientY - e.touches[1].clientY;
      var dist = Math.sqrt(dx*dx + dy*dy);
      if (touchState.dist > 0) {
        var scale = touchState.dist / dist;
        camera.distance = clamp(camera.distance * scale, camera.minD, camera.maxD);
      }
      touchState.dist = dist;
    }
  }

  function onTouchEnd(e) {
    if (e.touches.length === 0) {
      isDragging = false;
      var dx = lastMouse.x - mouseDownPos.x;
      var dy = lastMouse.y - mouseDownPos.y;
      if (Math.abs(dx) < 5 && Math.abs(dy) < 5) {
        var rect = canvas.getBoundingClientRect();
        var mx = mouseDownPos.x - rect.left;
        var my = mouseDownPos.y - rect.top;
        var pick = pickNode(mx * (canvas.width / rect.width), my * (canvas.height / rect.height));
        if (pick) {
          selectedNode = pick;
          if (onNodeClick) onNodeClick(pick);
        } else {
          selectedNode = null;
        }
      }
    } else if (e.touches.length === 1) {
      touchState.dist = 0;
      lastMouse.x = e.touches[0].clientX;
      lastMouse.y = e.touches[0].clientY;
      isDragging = true;
    }
  }

  canvas.addEventListener('mousedown', onMouseDown);
  canvas.addEventListener('mousemove', onMouseMove);
  canvas.addEventListener('mouseup', onMouseUp);
  canvas.addEventListener('mouseleave', onMouseUp);
  canvas.addEventListener('wheel', onWheel, { passive: false });
  canvas.addEventListener('touchstart', onTouchStart, { passive: false });
  canvas.addEventListener('touchmove', onTouchMove, { passive: false });
  canvas.addEventListener('touchend', onTouchEnd, { passive: false });

  // Start loop
  gl.viewport(0, 0, canvas.width, canvas.height);
  updateProjection();
  updateCamera();
  animId = requestAnimationFrame(renderFrame);

  // ====== Controller API ======
  return {
    canvas: canvas,
    setOnNodeClick: function(cb) { onNodeClick = cb; },
    startFly: function() {
      isFlying = true;
      flyProgress = 0;
      nodes.forEach(function(n) { n._shown = false; });
    },
    stopFly: function() { isFlying = false; flyProgress = 0; },
    setTimeFilter: function(filter) { timeFilter = String(filter); },
    setEmotionMode: function(enabled) { emotionMode = enabled; },
    setNodes: function(newNodes, newSessions) {
      nodes = buildNodeData(newNodes, newSessions || sessions, Date.now());
      edges = buildEdges(nodes);
    },
    destroy: function() {
      if (animId) cancelAnimationFrame(animId);
      canvas.removeEventListener('mousedown', onMouseDown);
      canvas.removeEventListener('mousemove', onMouseMove);
      canvas.removeEventListener('mouseup', onMouseUp);
      canvas.removeEventListener('mouseleave', onMouseUp);
      canvas.removeEventListener('wheel', onWheel);
      canvas.removeEventListener('touchstart', onTouchStart);
      canvas.removeEventListener('touchmove', onTouchMove);
      canvas.removeEventListener('touchend', onTouchEnd);
      if (fpsEl && fpsEl.parentNode) fpsEl.parentNode.removeChild(fpsEl);
      if (canvas.parentNode) canvas.parentNode.removeChild(canvas);
      // Clean up WebGL resources
      gl.deleteProgram(sphereProg);
      gl.deleteProgram(lineProg);
      gl.deleteProgram(particleProg);
      gl.deleteBuffer(spherePosBuf);
      gl.deleteBuffer(sphereNormBuf);
      gl.deleteBuffer(lineBuf);
      gl.deleteBuffer(particlePosBuf);
      gl.deleteBuffer(particleSizeBuf);
    }
  };
}

// ====== Data builders ======

function buildNodeData(rawNodes, sessions, now) {
  if (!rawNodes || rawNodes.length === 0) {
    // Generate demo nodes if empty
    return generateDemoNodes();
  }

  var nodeMap = {};
  var result = [];

  // Map sessions by node id or create mapping
  var sessionMap = {};
  if (sessions) {
    sessions.forEach(function(s) {
      if (s.node_id != null) sessionMap[s.node_id] = s;
      else if (s.id != null) sessionMap[s.id] = s;
    });
  }

  for (var i = 0; i < rawNodes.length; i++) {
    var n = rawNodes[i];
    var sess = sessionMap[n.id] || null;
    var date = sess && (sess.date || sess.created_at) ? new Date(sess.date || sess.created_at).getTime() : now - Math.random() * 60 * DAYS_MS;
    var daysAgo = (now - date) / DAYS_MS;
    var z = daysAgo < 7 ? (Math.random() - 0.5) * 5 : -daysAgo * 2 - Math.random() * 10;
    z = Math.max(-100, Math.min(5, z));

    var emotion = null;
    if (sess && sess.emotion) {
      var score = typeof sess.emotion === 'number' ? sess.emotion : (sess.emotion.score || 0);
      emotion = score > 0.2 ? 'positive' : score < -0.2 ? 'negative' : 'neutral';
    }

    var node = {
      id: n.id,
      label: n.label || n.name || '节点',
      type: n.type || 'item',
      x: n.x != null ? (n.x - 400) * 0.3 : (Math.random() - 0.5) * 60,
      y: n.y != null ? (n.y - 250) * 0.3 : (Math.random() - 0.5) * 40,
      z: z,
      radius: n.type === 'self' ? 3.5 : (n.type === 'anon' ? 2.2 : 2.0),
      date: date,
      narrative: sess ? (sess.narrative_text || sess.text || '') : '',
      emotion: emotion,
      _shown: false,
    };
    result.push(node);
    nodeMap[n.id] = node;
  }

  return result;
}

function buildEdges(nodes) {
  var edges = [];
  var added = {};
  for (var i = 0; i < nodes.length; i++) {
    var n1 = nodes[i];
    for (var j = i + 1; j < nodes.length; j++) {
      var n2 = nodes[j];
      // Connect by time proximity and type relation
      var timeDist = Math.abs(n1.date - n2.date) / DAYS_MS;
      var spatialDist = Math.sqrt((n1.x-n2.x)*(n1.x-n2.x) + (n1.y-n2.y)*(n1.y-n2.y) + (n1.z-n2.z)*(n1.z-n2.z));
      if (timeDist < 3 && spatialDist < 25 && n1.type !== n2.type) {
        var key = n1.id < n2.id ? (n1.id + '-' + n2.id) : (n2.id + '-' + n1.id);
        if (!added[key]) {
          edges.push({ from: n1.id, to: n2.id, type: 'custom' });
          added[key] = true;
        }
      }
    }
  }
  return edges;
}

function generateDemoNodes() {
  var types = ['person', 'event', 'place', 'time'];
  var nodes = [];
  for (var i = 0; i < 30; i++) {
    var daysAgo = Math.random() * 60;
    var z = daysAgo < 7 ? (Math.random() - 0.5) * 3 : -daysAgo * 1.5 - Math.random() * 5;
    nodes.push({
      id: i,
      label: '记忆 ' + (i + 1),
      type: types[i % 4],
      x: (Math.random() - 0.5) * 60,
      y: (Math.random() - 0.5) * 40,
      z: z,
      radius: 2.0,
      date: Date.now() - daysAgo * DAYS_MS,
      narrative: '这是关于 ' + types[i % 4] + ' 的叙事片段...',
      emotion: Math.random() > 0.6 ? 'positive' : (Math.random() > 0.5 ? 'negative' : 'neutral'),
      _shown: false,
    });
  }
  return nodes;
}
