// ============ BASELINE SIMILARITY ============
import { computeMetrics } from './metrics.js';
import { state } from '../state.js';

export function computeBaselineSimilarity() {
  if (!state.baselineMetrics) return 1.0;
  var m = computeMetrics();
  if (!m) return 1.0;
  var b = state.baselineMetrics;
  var diffs = [
    Math.abs(m.connectivity - b.connectivity),
    Math.abs(m.clustering - b.clustering),
    Math.abs(m.centrality - b.centrality),
    Math.abs(m.entropy - b.entropy),
    Math.abs(m.density - b.density),
    Math.abs(m.globalEff - b.globalEff),
  ];
  var avgDiff = diffs.reduce(function(a, b) { return a + b; }, 0) / diffs.length;
  return Math.max(0, 1 - avgDiff * 2);
}
