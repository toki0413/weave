import { describe, it, expect } from 'vitest';
import {
  computeHealth,
  computeHealthV1,
  computeStructuralScore,
  computeContentualScore,
  computeTrendScore,
} from '../graph/metrics.js';

// 模拟 D1 正常认知场景的 metrics
const D1_METRICS = {
  connectivity: 1.0,
  clustering: 0.72,
  centrality: 1.0,
  entropy: 0.69,
  density: 0.36,
  avgPathLen: 1.78,
  globalEff: 0.85,
  smallWorld: 2.5,
  nodeCount: 8,
  edgeCount: 10,
  anonCount: 0,
  typeCounts: { emotion: 3, spatial: 4, temporal: 2, association: 1 },
};

// 模拟 MCI 碎片化场景
const MCI_METRICS = {
  connectivity: 0.4,
  clustering: 0.1,
  centrality: 0.5,
  entropy: 0.3,
  density: 0.1,
  avgPathLen: 3.5,
  globalEff: 0.3,
  smallWorld: 0.5,
  nodeCount: 6,
  edgeCount: 2,
  anonCount: 2,
  typeCounts: { emotion: 1, spatial: 1 },
};

describe('三层健康度模型', () => {
  describe('computeStructuralScore', () => {
    it('正常认知的结构分应在 0.8 以上', () => {
      const s = computeStructuralScore(D1_METRICS);
      expect(s).toBeGreaterThan(0.8);
    });

    it('MCI 的结构分应显著低于正常', () => {
      const s = computeStructuralScore(MCI_METRICS);
      expect(s).toBeLessThan(0.5);
    });

    it('结构分范围应在 [0, 1]', () => {
      expect(computeStructuralScore(D1_METRICS)).toBeLessThanOrEqual(1);
      expect(computeStructuralScore({ connectivity: 0, clustering: 0, globalEff: 0 })).toBe(0);
    });
  });

  describe('computeContentualScore', () => {
    it('无异常、无匿名时应接近 1', () => {
      const c = computeContentualScore(D1_METRICS, [], 0);
      expect(c).toBeGreaterThan(0.9);
    });

    it('异常越多惩罚越重', () => {
      const c1 = computeContentualScore(D1_METRICS, [{ severity: 'warn' }], 0);
      const c2 = computeContentualScore(D1_METRICS, [{ severity: 'warn' }, { severity: 'warn' }], 0);
      expect(c2).toBeLessThan(c1);
    });

    it('匿名比例 33% 时应严重惩罚', () => {
      const c = computeContentualScore(D1_METRICS, [], 0.33);
      expect(c).toBeLessThan(0.1);
    });
  });

  describe('computeTrendScore', () => {
    it('无基准时应返回 1', () => {
      expect(computeTrendScore(D1_METRICS, null, [])).toBe(1);
    });

    it('与基准一致时应接近 1', () => {
      const t = computeTrendScore(D1_METRICS, D1_METRICS, []);
      expect(t).toBeGreaterThan(0.9);
    });

    it('连续 3 天下降时应惩罚', () => {
      const history = [80, 75, 70];
      const t = computeTrendScore(D1_METRICS, D1_METRICS, history);
      expect(t).toBeLessThan(0.75); // 0.7 * driftScore
    });
  });

  describe('computeHealth (完整三层模型)', () => {
    it('D1 正常认知 health ≥ 80', () => {
      const h = computeHealth(D1_METRICS, [], null, []);
      expect(h).toBeGreaterThanOrEqual(80);
      expect(h).toBeLessThanOrEqual(100);
    });

    it('MCI 场景 health < 60', () => {
      const anomalies = [
        { event: '打太极', severity: 'danger' },
        { event: '做饭', severity: 'warn' },
      ];
      const h = computeHealth(MCI_METRICS, anomalies, null, []);
      expect(h).toBeLessThan(60);
    });

    it('健康度有界 [0, 100]', () => {
      const h = computeHealth({ nodeCount: 1, edgeCount: 0, anonCount: 0, connectivity: 0, clustering: 0, globalEff: 0, typeCounts: {} }, [], null, []);
      expect(h).toBe(0);
    });

    it('异常增加 → health 单调下降', () => {
      const h1 = computeHealth(D1_METRICS, [{ severity: 'warn' }], null, []);
      const h2 = computeHealth(D1_METRICS, [{ severity: 'warn' }, { severity: 'warn' }], null, []);
      expect(h2).toBeLessThan(h1);
    });

    it('v1 与 v2 公式差异：MCI 场景 v2 更敏感', () => {
      const anomalies = [{ severity: 'danger' }];
      const h1 = computeHealthV1(MCI_METRICS);
      const h2 = computeHealth(MCI_METRICS, anomalies, null, []);
      // v2 引入异常惩罚，应该比 v1 更严格
      expect(h2).toBeLessThan(h1);
    });
  });
});
