// ============ VIEW MODE（2D/3D 偏好的唯一读写口）============
// 背景：'viewMode' 原先是跨模式共用的单个 localStorage key，有四个地方在读写它：
//   3d/view-switcher.js:7    模块加载时读
//   3d/view-switcher.js:85   用户点击时写
//   main.js:107              启动 300ms 后读，命中就 enter3DMode()
//   modes/elderly.js:19      老人端渲染时写 '2d'
// 两个后果：
//   1) 老人端一渲染就把家属在同一设备上存的 3D 偏好静默清除；
//   2) 更要紧的是 main.js:107 在 getMe()（异步）之前就跑，老人可能先被拉进
//      3D、再被 elderly.js 拉回 2D，中间那一闪不可控。elderly.js 的 setItem
//      实际上是在掩盖 main.js 的行为，而不是在做防护。
//
// 本模块是唯一读写口。规则：偏好按模式分片；老人端不支持 3D，
// 既不读也不写任何持久偏好，恒定 2D。退出当前 3D 不等于改写用户的持久偏好。

import { currentMode } from './mode.js';

var LEGACY_KEY = 'viewMode';
var PREFIX = 'viewMode:';

export function viewModeKey(mode) {
  return PREFIX + (mode || 'full');
}

/** 该模式是否支持 3D。老人端刻意不支持：界面只留一件事。 */
export function modeSupports3D(mode) {
  return mode === 'family-mode' || mode === 'doctor-mode';
}

function readRaw(key) {
  try { return localStorage.getItem(key); } catch (e) { return null; }
}
function writeRaw(key, val) {
  try { val === null ? localStorage.removeItem(key) : localStorage.setItem(key, val); }
  catch (e) { /* 隐私模式 / 配额满，静默：偏好丢失可接受，渲染崩掉不可接受 */ }
}

/** 读取该模式的视图偏好。老人端恒为 '2d'；未迁移时回退旧的全局键。 */
export function getViewMode(mode) {
  mode = mode || currentMode();
  if (!modeSupports3D(mode)) return '2d';
  var v = readRaw(viewModeKey(mode));
  if (v === '3d' || v === '2d') return v;
  var legacy = readRaw(LEGACY_KEY);
  return (legacy === '3d' || legacy === '2d') ? legacy : '2d';
}

/** 写该模式的视图偏好。不支持 3D 的模式一律拒绝，绝不留旁路。 */
export function setViewMode(mode, v) {
  mode = mode || currentMode();
  if (!modeSupports3D(mode)) return false;
  if (v !== '2d' && v !== '3d') return false;
  writeRaw(viewModeKey(mode), v);
  return true;
}

/** 一次性迁移：把旧全局键的意图归给当时正在使用 3D 的那个模式，然后删旧键。
 *  旧键本身无法区分是哪个模式设的，这里取"当前模式优先，否则给家属端"：
 *  老人端本就不支持 3D，绝不可能成为归属方。 */
export function migrateLegacyOnce(mode) {
  mode = mode || currentMode();
  var legacy = readRaw(LEGACY_KEY);
  if (legacy !== '2d' && legacy !== '3d') {
    if (legacy !== null) writeRaw(LEGACY_KEY, null);
    return null;
  }
  var owner = modeSupports3D(mode) ? mode : 'family-mode';
  if (readRaw(viewModeKey(owner)) === null) {
    writeRaw(viewModeKey(owner), legacy);
  }
  writeRaw(LEGACY_KEY, null);
  return owner;
}

/** 该角色此刻是否应进入 3D。供 main.js 启动恢复用，先判支持再读偏好。 */
export function prefers3D(mode) {
  mode = mode || currentMode();
  return modeSupports3D(mode) && getViewMode(mode) === '3d';
}
