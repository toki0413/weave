// ============ 词典批量导入解析（纯函数，可测） ============
// 旧实现有两处会静默产出错数据：
//   1) 只认 person/place/event/item，家属写"人名"会被**静默改成 item**；
//   2) 后端现已接受中文别名（routers/lexicon.py 同一套映射），前端若先
//      强转英文就抢在归一之前把数据改错了。
// 现在：中文别名按后端同源映射归一；类型识别不了的行**不写入**，
// 单独回报给调用方显示，不再悄悄降级成 item。

export const LEXICON_TYPE_ALIASES = {
  'person': 'person', '人名': 'person', '人物': 'person', '人': 'person',
  'place': 'place', '地点': 'place', '地方': 'place', '场所': 'place',
  'event': 'event', '事件': 'event', '事情': 'event', '活动': 'event',
  'item': 'item', '物品': 'item', '东西': 'item', '物件': 'item',
};

export function normalizeWordType(raw) {
  var key = String(raw == null ? '' : raw).trim().toLowerCase();
  // 单层查表即可：中文键不受 toLowerCase 影响，英文键本就是小写。
  // 此前多一层"原样查表"是冗余分支——变异验证证明删掉它行为完全不变（等价变异），
  // 留着只会让人误以为它承载了什么语义。
  return LEXICON_TYPE_ALIASES[key] || null;
}

/**
 * 解析导入文本：每行 `词,类型`（中英文逗号均可）。
 * @returns {Array<{word, word_type}>} 数组上带 .bad = 无法识别类型的行
 */
export function parseImportText(text) {
  var items = [];
  var bad = [];
  String(text || '').split(/\r?\n/).forEach(function(line) {
    var s = line.trim();
    if (!s) return;
    var parts = s.split(/[,，]/).map(function(x) { return x.trim(); });
    var word = parts[0];
    if (!word) return;
    var rawType = parts[1] || '';
    if (!rawType) {
      // 未填类型：保留旧的"默认 item"行为（用户没表达意图，不算错）
      items.push({ word: word, word_type: 'item' });
      return;
    }
    var t = normalizeWordType(rawType);
    if (!t) {
      bad.push(s);                      // 不再静默降级成 item
      return;
    }
    items.push({ word: word, word_type: t });
  });
  items.bad = bad;
  return items;
}
