// ============ 用户可见错误文案归一化（story-10） ============
// 纯函数、零依赖：把后端 detail 统一翻译成"说给老人/家属听的话"。
// 规则收口在这一处——任何组件不得自行拼接后端错误原文（曾把
// "全部 ASR provider 失败：{内部异常}" 弹给老人）。

// 已知英文 detail 的映射表（后端已中文化的项此处兜底，防缓存/旧接口）
const EN_COPY = {
  'Could not validate credentials': '登录状态已失效，请重新登录',
  'Invalid credentials': '手机号或密码不正确',
  'Not authenticated': '请先登录',
  'Forbidden': '您没有权限做这件事',
};

/**
 * 把响应错误 detail 归一为用户可读文案。
 * @param {string|Array|null} detail FastAPI detail（字符串或 422 校验数组）
 * @param {number} status HTTP 状态码
 */
export function normalizeErrorDetail(detail, status) {
  if (Array.isArray(detail)) {
    // FastAPI 422：[{loc, msg, type}, ...] —— 曾显示成 [object Object]
    const parts = detail.map(function(d) {
      return d && d.msg ? String(d.msg) : JSON.stringify(d);
    });
    return '提交的信息有误：' + parts.join('；');
  }
  if (detail == null || detail === '') {
    return status === 401 ? '请先登录' : '请求失败（' + status + '），请稍后再试';
  }
  const s = String(detail);
  return EN_COPY[s] || s;
}
