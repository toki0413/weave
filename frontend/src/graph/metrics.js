// ============ GRAPH METRICS ============
// 三层健康度模型：结构 x 内容 x 趋势
import { state } from '../state.js';

export function computeMetrics() {
  var nodes = state.nodes, edges = state.edges;
  var n = nodes.length, e = edges.length;
  if (n === 0) return null;

  var adj = {};
  nodes.forEach(function(nd) { adj[nd.id] = []; });
  edges.forEach(function(ed) {
    if (!adj[ed.from]) adj[ed.from] = [];
    if (!adj[ed.to]) adj[ed.to] = [];
    adj[ed.from].push(ed.to);
    adj[ed.to].push(ed.from);
  });

  // Connectivity
  var visited = {}, components = 0, maxComp = 0;
  nodes.forEach(function(nd) {
    if (visited[nd.id]) return;
    components++;
    var stack = [nd.id], size = 0;
    while (stack.length) {
      var id = stack.pop();
      if (visited[id]) continue;
      visited[id] = true; size++;
      (adj[id] || []).forEach(function(nid) { if (!visited[nid]) stack.push(nid); });
    }
    if (size > maxComp) maxComp = size;
  });
  var connectivity = maxComp / n;

  // Degrees
  var degrees = nodes.map(function(nd) { return (adj[nd.id] || []).length; });
  var avgDeg = degrees.reduce(function(a, b) { return a + b; }, 0) / n;

  // Clustering
  var ccList = [];
  nodes.forEach(function(nd) {
    var neigh = adj[nd.id] || [];
    var k = neigh.length;
    if (k < 2) return;
    var tri = 0;
    for (var i = 0; i < k; i++)
      for (var j = i + 1; j < k; j++)
        if ((adj[neigh[i]] || []).indexOf(neigh[j]) >= 0) tri++;
    ccList.push((2 * tri) / (k * (k - 1)));
  });
  var clustering = ccList.length > 0 ? ccList.reduce(function(a, b) { return a + b; }, 0) / ccList.length : 0;

  // Centrality
  var selfNode = nodes.find(function(nd) { return nd.type === 'self'; });
  var selfDeg = selfNode ? (adj[selfNode.id] || []).length : 0;
  var centrality = n > 1 ? selfDeg / (n - 1) : 0;

  // Entropy
  var typeCounts = {};
  edges.forEach(function(ed) { typeCounts[ed.type] = (typeCounts[ed.type] || 0) + 1; });
  var entropy = 0;
  Object.keys(typeCounts).forEach(function(k) {
    var p = typeCounts[k] / e;
    entropy -= p * Math.log2(p);
  });
  var entropyNorm = e > 0 ? entropy / Math.log2(4) : 0;

  // Density
  var density = n > 1 ? (2 * e) / (n * (n - 1)) : 0;

  // Shortest paths (BFS from each node)
  var sumDist = 0, distCount = 0, effSum = 0;
  nodes.forEach(function(src) {
    var d = {};
    nodes.forEach(function(nd) { d[nd.id] = Infinity; });
    d[src.id] = 0;
    var q = [src.id], qi = 0;
    while (qi < q.length) {
      var u = q[qi++];
      (adj[u] || []).forEach(function(v) {
        if (d[v] === Infinity) { d[v] = d[u] + 1; q.push(v); }
      });
    }
    nodes.forEach(function(nd) {
      if (d[nd.id] !== Infinity && d[nd.id] > 0) {
        sumDist += d[nd.id]; distCount++;
        effSum += 1 / d[nd.id];
      }
    });
  });
  var avgPathLen = distCount > 0 ? sumDist / distCount : 0;
  var globalEff = n > 1 ? effSum / (n * (n - 1)) : 0;

  // Small-world
  var randCC = avgDeg > 1 ? avgDeg / n : 0;
  var randPL = avgDeg > 0 ? Math.log(n) / Math.log(avgDeg) : 0;
  var smallWorld = (randCC > 0 && randPL > 0) ? (clustering / randCC) / (avgPathLen / randPL) : 0;

  return {
    connectivity: connectivity,
    clustering: clustering,
    centrality: centrality,
    entropy: entropyNorm,
    density: density,
    avgPathLen: avgPathLen,
    globalEff: globalEff,
    smallWorld: smallWorld,
    nodeCount: n,
    edgeCount: e,
    anonCount: nodes.filter(function(nd) { return nd.isAnon; }).length,
    typeCounts: typeCounts,
  };
}

// 旧公式 v1.0（保留用于对比测试）
export function computeHealthV1(m) {
  if (!m) return 0;
  var s = m.connectivity * 0.2 + m.clustering * 0.15 + m.centrality * 0.15 +
          m.entropy * 0.1 + m.density * 0.1 + m.globalEff * 0.15 +
          Math.min(m.smallWorld, 2) * 0.5 * 0.15;
  return Math.round(Math.min(100, s * 100));
}

// ===== 三层模型 =====

export function computeStructuralScore(m) {
  return m.connectivity * 0.35 + m.clustering * 0.35 + m.globalEff * 0.30;
}

export function computeContentualScore(m, anomalies, anonRatio) {
  var anomalyPenalty = Math.pow(0.85, anomalies.length);
  var anonPenalty = Math.max(0, 1 - anonRatio * 3);
  var typeCounts = m.typeCounts || {};
  var coverage = m.edgeCount > 0 ? Math.min(1, Object.keys(typeCounts).length / 4) : 0;
  return anomalyPenalty * anonPenalty * (0.6 + 0.4 * coverage);
}

export function computeTrendScore(current, baseline, history) {
  if (!baseline) return 1.0;
  var drift = Math.abs(current.connectivity - baseline.connectivity) +
              Math.abs(current.clustering - baseline.clustering) +
              Math.abs(current.globalEff - baseline.globalEff);
  var driftScore = Math.exp(-drift * 3);
  if (history && history.length >= 3) {
    var last3 = history.slice(-3);
    var declining = last3[0] > last3[1] && last3[1] > last3[2];
    if (declining) return driftScore * 0.7;
  }
  return driftScore;
}

export function computeAudioScore(audio) {
  if (!audio) return 1.0;
  var wpm = audio.words_per_minute || 0;
  var speechRatio = audio.speech_ratio || 0;

  // 语速异常扣分：过慢（找词困难）或过快（焦虑/冲动）
  var wpmScore = 1.0;
  if (wpm > 0 && wpm < 60) wpmScore = 0.75;
  else if (wpm >= 60 && wpm < 80) wpmScore = 0.9;
  else if (wpm > 200) wpmScore = 0.85;

  // 语音占比过低：可能存在大量犹豫、停顿
  var ratioScore = 1.0;
  if (speechRatio > 0 && speechRatio < 0.4) ratioScore = 0.75;
  else if (speechRatio >= 0.4 && speechRatio < 0.6) ratioScore = 0.9;

  return wpmScore * ratioScore;
}


export function computeHealth(m, anomalies, baseline, history) {
  if (!m) return 0;
  anomalies = anomalies || [];
  var anonRatio = m.nodeCount > 0 ? m.anonCount / m.nodeCount : 0;
  var s = computeStructuralScore(m);
  var c = computeContentualScore(m, anomalies, anonRatio);
  var t = computeTrendScore(m, baseline, history);
  var a = computeAudioScore(m.audio);
  return Math.round(100 * s * c * t * a);
}
