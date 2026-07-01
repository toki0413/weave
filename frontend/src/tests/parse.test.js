import { describe, it, expect, beforeEach } from 'vitest';
import { parseTextLocal } from '../nlp/parse.js';
import { state } from '../state.js';
import { addNode } from '../graph/model.js';

// 文本解析测试：实体识别、关系抽取、匿名节点、新增关系模式
describe('文本解析 parseTextLocal', () => {
  beforeEach(() => {
    // 每个用例前清空状态，确保解析从干净环境开始
    state.nodes = [];
    state.edges = [];
    state.nodeIdCounter = 0;
    state.anomalies = [];
    state.daySnapshots = {};
    localStorage.clear();
  });

  it('应识别公园和老张', () => {
    const result = parseTextLocal('今天在公园碰见老张');
    const labels = state.nodes.map(n => n.label);
    expect(labels).toContain('公园');
    expect(labels).toContain('老张');
    expect(result.fromApi).toBe(false);
  });

  it('应提取情感关系：一起打太极', () => {
    const result = parseTextLocal('和老张一起打太极，');
    const emotionRel = result.relations.find(r => r.type === 'emotion');
    expect(emotionRel).toBeTruthy();
    expect(emotionRel.from).toBe('老张');
    expect(emotionRel.to).toBe('打太极');
  });

  it('应提取时间关系：然后', () => {
    const result = parseTextLocal('打太极，然后做饭');
    const timeRel = result.relations.find(r => r.type === 'time');
    expect(timeRel).toBeTruthy();
    expect(timeRel.from).toBe('打太极');
    expect(timeRel.to).toBe('做饭');
  });

  it('应创建匿名节点：那个穿红衣服的', () => {
    // 先放入一个可匹配的 person 节点，模拟历史记忆
    addNode('穿红衣服', 'person');
    const result = parseTextLocal('那个穿红衣服的');
    expect(result.anonNode).toBeTruthy();
    expect(result.anonNode.matchedTo).toBe('穿红衣服');
    expect(result.anonNode.type).toBe('anon');
  });

  it('应提取情感关系：和老伴一起', () => {
    const result = parseTextLocal('今天和老伴一起散步，');
    // "和...一起" 模式生成 from=SELF to=老伴；"一起..." 模式生成 from=老伴 to=散步
    const emotionRel = result.relations.find(r => r.type === 'emotion' && (r.from === '老伴' || r.to === '老伴'));
    expect(emotionRel).toBeTruthy();
  });

  it('应提取情感关系：遇到老张', () => {
    const result = parseTextLocal('今天遇到老张，');
    const emotionRel = result.relations.find(r => r.type === 'emotion' && r.to === '老张');
    expect(emotionRel).toBeTruthy();
  });

  it('应提取情感关系：儿子陪我', () => {
    const result = parseTextLocal('儿子陪我去医院看病');
    const emotionRel = result.relations.find(r => r.type === 'emotion' && r.to === '儿子');
    expect(emotionRel).toBeTruthy();
  });
});
