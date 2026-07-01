import { describe, it, expect } from 'vitest';
import { fmmSegment } from '../nlp/fmm.js';
import { extractEntities } from '../nlp/entity.js';
import { checkSemanticAnomalies } from '../nlp/anomaly.js';

describe('FMM 分词', () => {
  it('应正确识别常见实体', () => {
    const tokens = fmmSegment('今天去公园和老张下棋');
    const words = tokens.map(t => t.word);
    expect(words).toContain('公园');
    expect(words).toContain('老张');
    expect(words).toContain('下棋');
  });

  it('应处理无匹配文本', () => {
    const tokens = fmmSegment('abcdefg');
    expect(tokens.length).toBe(0);
  });
});

describe('实体提取', () => {
  it('应提取人物、地点、事件', () => {
    const ent = extractEntities('今天去公园和老张下棋');
    expect(ent.places).toContain('公园');
    expect(ent.persons).toContain('老张');
    expect(ent.events).toContain('下棋');
  });

  it('无匹配时应返回空数组', () => {
    const ent = extractEntities('今天天气很好');
    expect(ent.places.length).toBe(0);
    expect(ent.persons.length).toBe(0);
  });
});

describe('语义异常检测', () => {
  it('应检测地点异常', () => {
    const anomalies = checkSemanticAnomalies('在医院打太极', {
      persons: [], places: ['医院'], events: ['打太极'], items: [],
    });
    expect(anomalies.length).toBeGreaterThan(0);
    expect(anomalies[0].event).toBe('打太极');
  });

  it('正常地点不应报警', () => {
    const anomalies = checkSemanticAnomalies('在公园打太极', {
      persons: [], places: ['公园'], events: ['打太极'], items: [],
    });
    expect(anomalies.length).toBe(0);
  });

  it('应去重同一事件', () => {
    const anomalies = checkSemanticAnomalies('在医院打太极，又在医院打太极', {
      persons: [], places: ['医院'], events: ['打太极'], items: [],
    });
    const unique = {};
    anomalies.forEach(a => { unique[a.event] = a; });
    expect(Object.keys(unique).length).toBe(1);
  });
});
