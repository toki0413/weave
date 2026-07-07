// ============ 文本解析 ============
import { fmmSegment } from './fmm.js';
import { extractEntities } from './entity.js';
import { checkSemanticAnomalies } from './anomaly.js';
import { state } from '../state.js';
import { addNode, findNode, getSelfNode, addEdge } from '../graph/model.js';
import { saveState } from '../ui/interactions.js';
import { createSession } from '../api/client.js';

// 匿名节点模糊匹配：编辑距离 + 历史频率 + 上下文加权
function matchAnon(features, contextEnt) {
  var best = null, bestScore = 0;
  state.nodes.forEach(function(n) {
    if (n.type !== 'person') return;
    var score = 0;
    features.forEach(function(f) {
      // 子串匹配
      if (n.label.indexOf(f) >= 0 || f.indexOf(n.label) >= 0) score += 2;
      // 编辑距离相似度
      else if (editDistance(n.label, f) <= 2) score += 1;
    });
    // 上下文加权：如果该节点与当前句中的事件/地点有共同连接，加分
    if (contextEnt) {
      contextEnt.events.forEach(function(ev) {
        var evNode = findNode(ev, 'event');
        if (evNode && state.edges.some(function(e) {
          return (e.from === n.id && e.to === evNode.id) || (e.to === n.id && e.from === evNode.id);
        })) score += 0.5;
      });
      contextEnt.places.forEach(function(pl) {
        var plNode = findNode(pl, 'place');
        if (plNode && state.edges.some(function(e) {
          return (e.from === n.id && e.to === plNode.id) || (e.to === n.id && e.from === plNode.id);
        })) score += 0.5;
      });
    }
    // 历史频率加权：出现次数越多越可能是同一个人
    var freq = n._freq || 1;
    score = score * (1 + Math.log(freq) * 0.1);
    if (score > bestScore) { bestScore = score; best = n; }
  });
  if (best && bestScore >= 1) {
    return { label: best.label, confidence: Math.min(95, Math.round(bestScore * 25 + 35)) };
  }
  return null;
}

function editDistance(a, b) {
  var m = a.length, n = b.length;
  var dp = [];
  for (var i = 0; i <= m; i++) { dp[i] = [i]; }
  for (var j = 0; j <= n; j++) { dp[0][j] = j; }
  for (var i = 1; i <= m; i++) {
    for (var j = 1; j <= n; j++) {
      dp[i][j] = a[i-1] === b[j-1] ? dp[i-1][j-1] : Math.min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1]) + 1;
    }
  }
  return dp[m][n];
}

// 检查是否已登录（不自动注册）
function isLoggedIn() {
  return !!localStorage.getItem('cg_token');
}

async function parseText(text) {
  // 优先使用后端 API（仅在已登录时）
  if (isLoggedIn()) {
    try {
      var result = await createSession(state.currentDay + 1, text, 'mandarin', state.lastAudioMetrics);
      state.lastAudioMetrics = null;  // 用过后清空，避免重复用于手动输入
      state.nodes = result.graph.nodes.map(function(n) {
        return {
          id: n.id, label: n.label, type: n.type,
          x: n.x || state.svgW / 2 + (Math.random() - 0.5) * 200,
          y: n.y || state.svgH / 2 + (Math.random() - 0.5) * 200,
          vx: 0, vy: 0,
          radius: n.type === 'self' ? 28 : n.type === 'anon' ? 22 : 20,
          isAnon: n.type === 'anon',
          matchedTo: n.matchedTo || null,
          matchConfidence: n.matchConfidence || 0, fixed: false,
        };
      });
      state.edges = result.graph.edges || [];
      state.anomalies = result.anomalies || [];
      state.daySnapshots[state.currentDay] = {
        graph: result.graph, metrics: result.metrics, health: result.health_score, anomalies: result.anomalies,
      };
      // 保存情绪数据到状态
      state.lastEmotion = {
        overall: result.emotion_label || 'neutral',
        score: result.emotion_score !== undefined ? result.emotion_score : 0,
        words: { positive: [], negative: [] },
      };
      return { tokens: [], relations: [], anonNode: null, fromApi: true, emotion: state.lastEmotion };
    } catch (err) {
      console.warn('API 解析失败，降级到本地:', err.message || err);
    }
  }
  // 本地解析（离线默认模式）
  return parseTextLocal(text);
}

function parseTextLocal(text) {
  // 预处理：去掉"了"等语气词干扰
  text = text.replace(/([聊吃看打听读买做散浇下])了(.)/g, function(_, v, o) { return v + o; });
  text = text.replace(/量了血压/g, '量血压');
  text = text.replace(/聊了天/g, '聊天');

  var tokens = fmmSegment(text);
  var ent = { persons: [], places: [], events: [], items: [] };
  tokens.forEach(function(t) {
    var cat = t.type + 's';
    if (ent[cat] && ent[cat].indexOf(t.word) < 0) ent[cat].push(t.word);
  });

  // 匿名节点检测："那个...的"
  var anonNode = null;
  var anonMatch = text.match(/那个(.+?)的(?=[，。！？]|$)/) || text.match(/那个(.+)的/);
  if (anonMatch && ent.persons.length === 0) {
    var features = anonMatch[1].split(/[、，和]/).map(function(f) { return f.replace(/的/g, '').trim(); }).filter(function(f) { return f.length > 0; });
    var matched = matchAnon(features, ent);
    if (matched) {
      anonNode = addNode('?X', 'anon');
      anonNode.matchedTo = matched.label;
      anonNode.matchConfidence = matched.confidence;
    }
  }

  var selfNode = getSelfNode();
  ['persons','places','events','items'].forEach(function(cat) {
    var typeKey = cat.substring(0, cat.length - 1);
    ent[cat].forEach(function(word) {
      var existing = findNode(word, typeKey);
      if (!existing) {
        addNode(word, typeKey);
      } else {
        // 更新频率计数
        existing._freq = (existing._freq || 1) + 1;
      }
    });
  });

  var relations = [];
  var m;
  // 在...碰见/遇见... → 空间关系
  if (m = text.match(/在(.+?)(碰见|遇见|遇到|碰到)(.+?)(?:，|。|然后|一起)/)) {
    var p1 = ent.places.find(function(p) { return m[1].indexOf(p) >= 0; });
    var p2 = ent.persons.find(function(p) { return m[3].indexOf(p) >= 0; });
    if (p1 && p2) relations.push({ type: 'space', from: p2, to: p1 });
  }
  // 一起... → 情感关系
  if (m = text.match(/一起(.+?)(?:，|。|然后|去|回)/)) {
    var ev = ent.events.find(function(e) { return m[1].indexOf(e) >= 0; });
    var ps = ent.persons[0];
    if (ps && ev) relations.push({ type: 'emotion', from: ps, to: ev });
  }
  // 然后/之后 → 时间关系
  if (text.match(/然后|之后|接着/) && ent.events.length >= 2) {
    relations.push({ type: 'time', from: ent.events[0], to: ent.events[1] });
  }
  // 去...买... → 空间+关联
  if (m = text.match(/去(.+?)(?:买|取|拿)(了)?(.+?)(?:，|。|然后|回家)/)) {
    var pl = ent.places.find(function(p) { return m[1].indexOf(p) >= 0; });
    var it = ent.items.find(function(p) { return m[3].indexOf(p) >= 0; });
    if (pl) relations.push({ type: 'space', from: 'SELF', to: pl });
    if (it) relations.push({ type: 'custom', from: 'SELF', to: it });
  }
  // ...陪我去... → 情感+空间
  if (m = text.match(/(.+?)陪(我|他|她)?去(.+?)(?:看|买|量|复诊|检查)/)) {
    var pp = ent.persons.find(function(p) { return m[1].indexOf(p) >= 0; });
    var pl2 = ent.places.find(function(p) { return m[3].indexOf(p) >= 0; });
    if (pp) relations.push({ type: 'emotion', from: 'SELF', to: pp });
    if (pp && pl2) relations.push({ type: 'space', from: pp, to: pl2 });
  }
  // 在...(打/做/看/...) → 空间关系
  if (m = text.match(/在(.+?)(打|做|看|吃|聊|下|散|浇|听|读|买|锻炼|休息|起床)/)) {
    var pl3 = ent.places.find(function(p) { return m[1].indexOf(p) >= 0; });
    var ev3 = ent.events.find(function(e) { return m[0].indexOf(e) >= 0; });
    if (pl3 && ev3) relations.push({ type: 'space', from: ev3, to: pl3 });
  }
  // 和/跟/与...一起 → 情感关系
  if (m = text.match(/(和|跟|与)(.+?)(?:一起|聊天|散步|下棋|打牌|吃饭|逛街)/)) {
    var pp2 = ent.persons.find(function(p) { return m[2].indexOf(p) >= 0; });
    if (pp2) relations.push({ type: 'emotion', from: 'SELF', to: pp2 });
  }
  // ...给/帮... → 情感关系（帮助行为）
  if (m = text.match(/(.+?)(给|帮|替)(我|他|她|老伴|儿子|女儿)(.+?)(?:，|。|然后)/)) {
    var helper = ent.persons.find(function(p) { return m[1].indexOf(p) >= 0; });
    if (helper) relations.push({ type: 'emotion', from: helper, to: 'SELF' });
  }
  // ...带...去... → 情感+空间
  if (m = text.match(/(.+?)带(我|他|她|老伴|儿子|女儿)?去(.+?)(?:看|买|检查|复诊|玩|逛)/)) {
    var leader = ent.persons.find(function(p) { return m[1].indexOf(p) >= 0; });
    var pl4 = ent.places.find(function(p) { return m[3].indexOf(p) >= 0; });
    if (leader) relations.push({ type: 'emotion', from: 'SELF', to: leader });
    if (leader && pl4) relations.push({ type: 'space', from: leader, to: pl4 });
  }
  // ...叫/让...来... → 情感关系
  if (m = text.match(/(叫|让|请)(.+?)(?:来|过来|帮忙)(?:，|。|然后)/)) {
    var pp3 = ent.persons.find(function(p) { return m[2].indexOf(p) >= 0; });
    if (pp3) relations.push({ type: 'emotion', from: 'SELF', to: pp3 });
  }
  // ...遇到/碰见... → 情感关系（偶遇）
  if (m = text.match(/(遇到|碰见|遇见|碰到)(.+?)(?:，|。|然后|在|一起)/)) {
    var pp4 = ent.persons.find(function(p) { return m[2].indexOf(p) >= 0; });
    if (pp4) relations.push({ type: 'emotion', from: 'SELF', to: pp4 });
  }

  relations.forEach(function(rel) {
    var fn = rel.from === 'SELF' ? selfNode : findNode(rel.from);
    var tn = rel.to === 'SELF' ? selfNode : findNode(rel.to);
    if (fn && tn) addEdge(fn.id, tn.id, rel.type);
  });

  // 自我节点与所有实体建立初始连接
  ent.persons.forEach(function(p) { var n = findNode(p, 'person'); if (n) addEdge(selfNode.id, n.id, 'emotion'); });
  ent.events.forEach(function(e) { var n = findNode(e, 'event'); if (n) addEdge(selfNode.id, n.id, 'time'); });
  ent.places.forEach(function(p) { var n = findNode(p, 'place'); if (n) addEdge(selfNode.id, n.id, 'space'); });
  ent.items.forEach(function(i) { var n = findNode(i, 'item'); if (n) addEdge(selfNode.id, n.id, 'custom'); });

  if (anonNode) {
    ent.events.forEach(function(e) { var n = findNode(e, 'event'); if (n) addEdge(anonNode.id, n.id, 'emotion'); });
    ent.places.forEach(function(p) { var n = findNode(p, 'place'); if (n) addEdge(anonNode.id, n.id, 'space'); });
    addEdge(selfNode.id, anonNode.id, 'emotion');
  }

  state.anomalies = checkSemanticAnomalies(text, ent);
  return { tokens: tokens, relations: relations, anonNode: anonNode, fromApi: false };
}

export { parseText, parseTextLocal, isLoggedIn };
