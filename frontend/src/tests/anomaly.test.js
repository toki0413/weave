import { describe, it, expect } from 'vitest';
import { checkSemanticAnomalies } from '../nlp/anomaly.js';

// 语义异常检测测试：事件-地点 + 事件-时间
describe('语义异常检测 checkSemanticAnomalies', () => {
  it('正常场景不应报警：在公园打太极', () => {
    const anomalies = checkSemanticAnomalies('在公园打太极', {
      persons: [], places: ['公园'], events: ['打太极'], items: [],
    });
    expect(anomalies.length).toBe(0);
  });

  it('人物活动地点不匹配应报警：在公园做饭', () => {
    const anomalies = checkSemanticAnomalies('在公园做饭', {
      persons: [], places: ['公园'], events: ['做饭'], items: [],
    });
    expect(anomalies.length).toBeGreaterThan(0);
    expect(anomalies[0].event).toBe('做饭');
    // 同一句中出现非预期地点，应升级为 danger
    expect(anomalies[0].severity).toBe('danger');
  });

  it('事件缺少预期地点应报警：做饭无地点', () => {
    const anomalies = checkSemanticAnomalies('做饭', {
      persons: [], places: [], events: ['做饭'], items: [],
    });
    expect(anomalies.length).toBeGreaterThan(0);
    expect(anomalies[0].event).toBe('做饭');
    expect(anomalies[0].severity).toBe('warn');
  });

  it('正常地点不应报警：在医院看病', () => {
    const anomalies = checkSemanticAnomalies('在医院看病', {
      persons: [], places: ['医院'], events: ['看病'], items: [],
    });
    expect(anomalies.length).toBe(0);
  });

  it('事件-时间不匹配应报警：凌晨打太极', () => {
    const anomalies = checkSemanticAnomalies('凌晨去打太极', {
      persons: [], places: [], events: ['打太极'], items: [],
    });
    const timeAnom = anomalies.find(a => a.type === 'event-time-mismatch');
    expect(timeAnom).toBeTruthy();
    expect(timeAnom.event).toBe('打太极');
    expect(timeAnom.unexpectedTimes).toContain('凌晨');
  });

  it('事件-时间匹配不应报警：早上打太极', () => {
    const anomalies = checkSemanticAnomalies('早上去打太极', {
      persons: [], places: [], events: ['打太极'], items: [],
    });
    const timeAnom = anomalies.find(a => a.type === 'event-time-mismatch');
    expect(timeAnom).toBeUndefined();
  });

  it('事件-时间不匹配应报警：半夜起床', () => {
    const anomalies = checkSemanticAnomalies('半夜起床', {
      persons: [], places: [], events: ['起床'], items: [],
    });
    const timeAnom = anomalies.find(a => a.type === 'event-time-mismatch');
    expect(timeAnom).toBeTruthy();
    expect(timeAnom.event).toBe('起床');
  });
});
