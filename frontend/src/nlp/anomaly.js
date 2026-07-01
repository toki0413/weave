// ============ 异常检测：事件-地点 + 事件-时间 ============
import { SEMANTIC_RULES } from './lexicon.js';

// 时间表达：用于事件-时间异常检测
var TIME_EXPRESSIONS = ['凌晨', '半夜', '深夜', '早上', '早晨', '上午', '中午', '下午', '傍晚', '晚上', '夜里'];

// 事件-时间预期：某些事件在特定时段出现属于异常
var EVENT_TIME_EXPECTATIONS = {
  '打太极': { expected: ['早上', '早晨', '上午'], severity: 'warn' },
  '晨练': { expected: ['早上', '早晨'], severity: 'warn' },
  '散步': { expected: ['早上', '早晨', '下午', '傍晚', '晚上'], severity: 'warn' },
  '睡觉': { expected: ['晚上', '夜里', '半夜', '凌晨'], severity: 'warn' },
  '起床': { expected: ['早上', '早晨', '上午'], severity: 'warn' },
  '午休': { expected: ['中午', '下午'], severity: 'warn' },
  '买菜': { expected: ['早上', '早晨', '上午', '下午'], severity: 'warn' },
  '看电视': { expected: ['下午', '傍晚', '晚上', '夜里'], severity: 'warn' },
};

function checkSemanticAnomalies(text, ent) {
  var anomalies = [];

  // 1. 事件-地点不匹配
  ent.events.forEach(function(ev) {
    var rule = SEMANTIC_RULES[ev];
    if (rule) {
      var hasExpectedPlace = ent.places.some(function(p) { return rule.expectedPlaces.indexOf(p) >= 0; });
      if (!hasExpectedPlace) {
        // 检查是否有非预期地点与事件同句出现，升级为 danger
        var severity = rule.severity;
        ent.places.forEach(function(pl) {
          if (rule.expectedPlaces.indexOf(pl) < 0) {
            var short = text.split(/[，。；]/);
            short.forEach(function(sentence) {
              if (sentence.indexOf(ev) >= 0 && sentence.indexOf(pl) >= 0) {
                severity = 'danger';
              }
            });
          }
        });
        anomalies.push({ event: ev, expectedPlaces: rule.expectedPlaces, severity: severity, type: 'event-place-mismatch' });
      }
    }
  });

  // 2. 事件-时间不匹配
  ent.events.forEach(function(ev) {
    var timeRule = EVENT_TIME_EXPECTATIONS[ev];
    if (timeRule) {
      // 检测文本中的时间表达
      var foundTimes = TIME_EXPRESSIONS.filter(function(t) { return text.indexOf(t) >= 0; });
      if (foundTimes.length > 0) {
        var unexpected = foundTimes.filter(function(t) { return timeRule.expected.indexOf(t) < 0; });
        if (unexpected.length > 0) {
          anomalies.push({
            event: ev,
            unexpectedTimes: unexpected,
            expectedTimes: timeRule.expected,
            severity: timeRule.severity,
            type: 'event-time-mismatch',
          });
        }
      }
    }
  });

  // 去重：同 event + 同 type 保留最高严重级
  var unique = {};
  anomalies.forEach(function(a) {
    var key = a.event + '|' + a.type;
    if (!unique[key] || a.severity === 'danger') unique[key] = a;
  });
  return Object.values(unique);
}

export { checkSemanticAnomalies, EVENT_TIME_EXPECTATIONS, TIME_EXPRESSIONS };
