// ============ MODE（模式类名单一来源）============
// 类名以前被三个地方各写一次：ui/init.js（无条件老人端）、
// ui/panels/header.js:13-14（切换时）、各 mode 文件渲染时（elderly.js:14-16 等）。
// 三处写同一个东西，就一定会出现"谁最后写谁赢"的竞态，
// 已知那次竞态是 init.js 无条件挂 elderly-mode，而 main.js 的 getMe() 是异步的。
//
// 本文件是**唯一**允许写 documentElement 模式类名的地方。

var VALID = { elderly: 1, family: 1, doctor: 1 };
var ROLE_KEY = 'cg-role';
var MODE_CLASSES = ['elderly-mode', 'family-mode', 'doctor-mode'];

/** 角色 → 模式类名。未知/空角色返回 null，表示"完整模式"（向后兼容）。 */
export function resolveModeClass(role) {
  return VALID[role] ? role + '-mode' : null;
}

/** 当前模式类名；null 表示完整模式。 */
export function currentMode() {
  for (var i = 0; i < MODE_CLASSES.length; i++) {
    if (document.documentElement.classList.contains(MODE_CLASSES[i])) return MODE_CLASSES[i];
  }
  return null;
}

/** 应用模式。幂等：重复传同一 role 不产生副作用。 */
export function applyMode(role) {
  var root = document.documentElement;
  MODE_CLASSES.forEach(function (c) { root.classList.remove(c); });
  var cls = resolveModeClass(role);
  if (cls) root.classList.add(cls);
  document.body.className = cls ? 'mode-' + role : '';
  return cls;
}

/** getMe() 成功后缓存角色，供下次启动在骨架屏阶段就用对主题。 */
export function rememberRole(role) {
  try {
    if (VALID[role]) localStorage.setItem(ROLE_KEY, role);
    else localStorage.removeItem(ROLE_KEY);
  } catch (e) { /* 隐私模式 / 存储不可用，忽略 */ }
}

/** 读取上次缓存的角色；无缓存返回 ''（= 完整模式，不再默认老人端）。 */
export function recallRole() {
  try {
    var r = localStorage.getItem(ROLE_KEY);
    return VALID[r] ? r : '';
  } catch (e) { return ''; }
}
