// ============ 连续记录天数（story-3） ============
// 纯函数、零依赖：以"本地日历日"为单位从会话日期键算连续段。
// 跨天自动归零：昨天没录，今天录了也只算 1 天——不虚标。

export function localDateKey(dateLike) {
  var d = new Date(dateLike);
  if (isNaN(d.getTime())) return null;
  var m = ('0' + (d.getMonth() + 1)).slice(-2);
  var day = ('0' + d.getDate()).slice(-2);
  return d.getFullYear() + '-' + m + '-' + day;
}

/**
 * 连续天数：今天没记录 → 0；从今天往前数连续有记录的日历日个数。
 * @param {string[]} dateKeys 会话的本地日期键（可乱序、可重复）
 * @param {string} todayKey 今天的本地日期键
 */
export function computeStreak(dateKeys, todayKey) {
  var set = {};
  (dateKeys || []).forEach(function(k) { if (k) set[k] = true; });
  if (!set[todayKey]) return 0;
  var count = 0;
  var cur = new Date(todayKey + 'T00:00:00');
  while (cur && !isNaN(cur.getTime())) {
    var key = localDateKey(cur);
    if (set[key]) {
      count++;
      cur.setDate(cur.getDate() - 1);
    } else {
      break;
    }
  }
  return count;
}

export function hasTodayRecord(dateKeys, todayKey) {
  return (dateKeys || []).indexOf(todayKey) >= 0;
}
