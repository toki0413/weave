import { describe, it, expect, beforeEach } from 'vitest';
import { computeMetrics, computeHealth, computeStructuralScore, computeContentualScore, computeTrendScore, computeAudioScore } from '../graph/metrics.js';
import { state } from '../state.js';

// 图谱指标计算测试：覆盖连通性、密度、聚类系数、中心性、类型熵
describe('图谱指标 computeMetrics', () => {
  beforeEach(() => {
    // 每个用例前重置状态，避免历史数据干扰
    state.nodes = [];
    state.edges = [];
    state.nodeIdCounter = 0;
  });

  it('空图谱应返回 null', () => {
    expect(computeMetrics()).toBeNull();
  });

  it('单个自我节点：connectivity=1, density=0', () => {
    state.nodes = [{ id: 0, label: '我', type: 'self' }];
    state.edges = [];
    const m = computeMetrics();
    expect(m.connectivity).toBe(1);
    expect(m.density).toBe(0);
    expect(m.nodeCount).toBe(1);
    expect(m.edgeCount).toBe(0);
  });

  it('两个相连节点：connectivity=1, density=1', () => {
    state.nodes = [
      { id: 0, label: '我', type: 'self' },
      { id: 1, label: '老张', type: 'person' },
    ];
    state.edges = [{ from: 0, to: 1, type: 'emotion' }];
    const m = computeMetrics();
    expect(m.connectivity).toBe(1);
    expect(m.density).toBe(1);
  });

  it('三角形：clustering=1', () => {
    state.nodes = [
      { id: 0, label: '我', type: 'self' },
      { id: 1, label: '老张', type: 'person' },
      { id: 2, label: '公园', type: 'place' },
    ];
    state.edges = [
      { from: 0, to: 1, type: 'emotion' },
      { from: 1, to: 2, type: 'space' },
      { from: 0, to: 2, type: 'space' },
    ];
    const m = computeMetrics();
    expect(m.clustering).toBe(1);
  });

  it('自我节点中心性：连接所有其他节点时 centrality=1', () => {
    state.nodes = [
      { id: 0, label: '我', type: 'self' },
      { id: 1, label: '老张', type: 'person' },
      { id: 2, label: '公园', type: 'place' },
    ];
    state.edges = [
      { from: 0, to: 1, type: 'emotion' },
      { from: 0, to: 2, type: 'space' },
    ];
    const m = computeMetrics();
    // selfDeg=2, n=3, centrality = 2/(3-1) = 1
    expect(m.centrality).toBe(1);
  });

  it('自我节点中心性：仅连接一个节点时 centrality=0.5', () => {
    state.nodes = [
      { id: 0, label: '我', type: 'self' },
      { id: 1, label: '老张', type: 'person' },
      { id: 2, label: '公园', type: 'place' },
    ];
    state.edges = [
      { from: 0, to: 1, type: 'emotion' },
      { from: 1, to: 2, type: 'space' },
    ];
    const m = computeMetrics();
    // selfDeg=1, n=3, centrality = 1/(3-1) = 0.5
    expect(m.centrality).toBe(0.5);
  });

  it('类型熵：单一类型熵为 0', () => {
    state.nodes = [
      { id: 0, label: '我', type: 'self' },
      { id: 1, label: '老张', type: 'person' },
      { id: 2, label: '公园', type: 'place' },
    ];
    state.edges = [
      { from: 0, to: 1, type: 'emotion' },
      { from: 0, to: 2, type: 'emotion' },
    ];
    const m = computeMetrics();
    expect(m.entropy).toBe(0);
  });

  it('类型熵：两种类型均匀分布熵为 0.5', () => {
    state.nodes = [
      { id: 0, label: '我', type: 'self' },
      { id: 1, label: '老张', type: 'person' },
      { id: 2, label: '公园', type: 'place' },
    ];
    state.edges = [
      { from: 0, to: 1, type: 'emotion' },
      { from: 0, to: 2, type: 'space' },
    ];
    const m = computeMetrics();
    // entropy = 1 bit, 归一化除以 log2(4)=2 → 0.5
    expect(m.entropy).toBeCloseTo(0.5);
  });
});


describe('健康度 computeHealth', () => {
  it('空图谱健康度为 0', () => {
    expect(computeHealth(null)).toBe(0);
  });

  it('无异常无匿名节点时健康度较高', () => {
    const m = {
      connectivity: 1,
      clustering: 1,
      globalEff: 1,
      edgeCount: 4,
      typeCounts: { emotion: 1, space: 1, time: 1, custom: 1 },
      nodeCount: 3,
      anonCount: 0,
    };
    const h = computeHealth(m, []);
    expect(h).toBeGreaterThan(80);
  });

  it('异常和匿名节点会降低健康度', () => {
    const m = {
      connectivity: 1,
      clustering: 1,
      globalEff: 1,
      edgeCount: 1,
      typeCounts: { emotion: 1 },
      nodeCount: 4,
      anonCount: 2,
    };
    const h = computeHealth(m, [{ event: '人物-活动错置' }]);
    expect(h).toBeLessThan(computeHealth({ ...m, anonCount: 0 }, []));
  });

  it('连续下降历史会降低健康度', () => {
    const current = { connectivity: 0.8, clustering: 0.8, globalEff: 0.8 };
    const baseline = { connectivity: 0.9, clustering: 0.9, globalEff: 0.9 };
    const history = [85, 80, 75];
    expect(computeHealth(current, [], baseline, history)).toBeLessThan(
      computeHealth(current, [], baseline, [75, 80, 85])
    );
  });
});


describe('三层分数', () => {
  it('结构分：完全连通图为 1', () => {
    const m = { connectivity: 1, clustering: 1, globalEff: 1 };
    expect(computeStructuralScore(m)).toBeCloseTo(1);
  });

  it('内容分：异常惩罚生效', () => {
    const m = { edgeCount: 2, typeCounts: { emotion: 1, space: 1 }, nodeCount: 4, anonCount: 0 };
    expect(computeContentualScore(m, [], 0)).toBeGreaterThan(
      computeContentualScore(m, [{}, {}], 0)
    );
  });

  it('趋势分：无基线时返回 1', () => {
    expect(computeTrendScore({}, null, [])).toBe(1);
  });
});


describe('语音指标 computeAudioScore', () => {
  it('无音频指标时返回 1', () => {
    expect(computeAudioScore(null)).toBe(1);
  });

  it('正常语速和语音占比返回 1', () => {
    expect(computeAudioScore({ words_per_minute: 100, speech_ratio: 0.8 })).toBe(1);
  });

  it('语速过慢会扣分', () => {
    expect(computeAudioScore({ words_per_minute: 50, speech_ratio: 0.8 })).toBeLessThan(1);
  });

  it('语音占比过低会扣分', () => {
    expect(computeAudioScore({ words_per_minute: 100, speech_ratio: 0.3 })).toBeLessThan(1);
  });

  it('健康度计算会纳入音频维度', () => {
    const m = {
      connectivity: 1, clustering: 1, globalEff: 1,
      edgeCount: 4, typeCounts: { emotion: 1, space: 1, time: 1, custom: 1 },
      nodeCount: 3, anonCount: 0,
    };
    const hNormal = computeHealth(m, []);
    const hSlow = computeHealth({ ...m, audio: { words_per_minute: 50, speech_ratio: 0.8 } }, []);
    expect(hSlow).toBeLessThan(hNormal);
  });
});
