// ============ GRAPH MODEL ============
import { state } from '../state.js';
import { saveState } from '../ui/interactions.js';

// 使用局部变量避免 vite 压缩问题
var st = state;

function addNode(label, type, x, y) {
  var id = st.nodeIdCounter++;
  var angle = Math.random() * Math.PI * 2;
  var dist = 150 + Math.random() * 200;
  var node = {
    id: id, label: label, type: type,
    x: x != null ? x : st.svgW / 2 + Math.cos(angle) * dist,
    y: y != null ? y : st.svgH / 2 + Math.sin(angle) * dist,
    vx: 0, vy: 0,
    radius: type === 'self' ? 28 : type === 'anon' ? 22 : 20,
    isAnon: type === 'anon',
    matchedTo: null,
    matchConfidence: 0,
    fixed: false,
  };
  st.nodes.push(node);
  saveState();
  return node;
}

function findNode(label, type) {
  for (var i = 0; i < st.nodes.length; i++) {
    var n = st.nodes[i];
    if (n.label === label && (!type || n.type === type)) return n;
  }
  return null;
}

function getSelfNode() {
  var self = findNode('我', 'self');
  if (!self) self = addNode('我', 'self', st.svgW / 2, st.svgH / 2);
  return self;
}

function addEdge(fromId, toId, type, weight) {
  if (fromId === toId) return;
  for (var i = 0; i < st.edges.length; i++) {
    var e = st.edges[i];
    if ((e.from === fromId && e.to === toId) || (e.from === toId && e.to === fromId)) return;
  }
  st.edges.push({ from: fromId, to: toId, type: type, weight: weight || 1 });
  saveState();
}

export { addNode, findNode, getSelfNode, addEdge };
