// 老人端 token、字号阶梯与图形配色的静态验算（直读仓库内 styles.css / state.js）
// 运行：node --test frontend/src/tests/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'path';

const SRC = path.resolve(import.meta.dirname, '..');
const CSS = fs.readFileSync(path.join(SRC, 'styles.css'), 'utf8');
const STATE = fs.readFileSync(path.join(SRC, 'state.js'), 'utf8');
const INIT = fs.readFileSync(path.join(SRC, 'ui/init.js'), 'utf8');
const HEADER = fs.readFileSync(path.join(SRC, 'ui/panels/header.js'), 'utf8');
const MAIN = fs.readFileSync(path.join(SRC, 'main.js'), 'utf8');
const NEBULA = fs.readFileSync(path.join(SRC, '3d/memory-nebula.js'), 'utf8');

const hx = c => { c = c.replace('#',''); if (c.length===3) c=[...c].map(x=>x+x).join(''); return [0,2,4].map(i=>parseInt(c.slice(i,i+2),16)); };
const lin = v => { v/=255; return v<=0.03928 ? v/12.92 : ((v+0.055)/1.055)**2.4; };
const Lum = c => { const [r,g,b]=hx(c); return .2126*lin(r)+.7152*lin(g)+.0722*lin(b); };
const ratio = (a,b) => { const x=Lum(a),y=Lum(b); return (Math.max(x,y)+.05)/(Math.min(x,y)+.05); };

const live = CSS.replace(/\/\*[\s\S]*?\*\//g, '');
const mediaRanges = (() => {
  const out = []; const rx = /@media[^{]*\{/g; let m;
  while ((m = rx.exec(live))) {
    let d = 1, i = m.index + m[0].length;
    while (i < live.length && d > 0) { if (live[i]==='{') d++; else if (live[i]==='}') d--; i++; }
    out.push([m.index, i]);
  }
  return out;
})();
const inMedia = pos => mediaRanges.some(([a,b]) => pos>=a && pos<b);
/** 该选择器是否真的作用于老人端。
 *  不能用 sel.includes('elderly-mode')：`:root:not(.elderly-mode)` 也含这个子串，
 *  而它表达的恰好是反面，误判会把非老人端的紧凑档当成基础值读出来。 */
const elderlySel = sel =>
  /\.elderly-mode/.test(sel) && !sel.includes(':not(.elderly-mode)');

function elderlyToken(tk) {
  let out = null;
  const rx = new RegExp('--'+tk+'\\s*:\\s*(#[0-9A-Fa-f]{3,6})[\\s;]', 'g');
  let m;
  while ((m = rx.exec(live))) {
    if (inMedia(m.index)) continue;
    const head = live.lastIndexOf('{', m.index);
    const sel = live.slice(live.lastIndexOf('}', head)+1, head).trim();
    if (!elderlySel(sel)) continue;
    out = m[1];
  }
  return out;
}
const BASE_ROOTS = [...live.matchAll(/(^|\})\s*:root\s*\{([^}]*)\}/g)].map(m => m[2]);
function rampTok(name) {
  for (const body of BASE_ROOTS) {
    const d = body.match(new RegExp('--'+name+'\\s*:\\s*([0-9.]+)rem'));
    if (d) return parseFloat(d[1]);
  }
  assert.fail('所有基础 :root 块里都找不到 --'+name);
}
const NON_ELDER = (live.match(/:root:not\(\.elderly-mode\)\s*\{([^}]*)\}/) || [,''])[1];
const ELDER_ROOT = 21;
const NT = Object.fromEntries([...(STATE.match(/const NODE_TYPES\s*=\s*\{([\s\S]*?)\n\};/)||[,''])[1]
  .matchAll(/(\w+)\s*:\s*\{\s*color:\s*'(#[0-9A-Fa-f]{6})'/g)].map(m=>[m[1],m[2]]));

test('解析器自检：取到本次新增块的值而非历史块，否则整份验算不可信', () => {
  assert.ok(BASE_ROOTS.length >= 2, '基础 :root 块数量异常: ' + BASE_ROOTS.length);
  assert.ok(NON_ELDER, '找不到 :root:not(.elderly-mode)，解析前提变了');
  assert.equal(elderlyToken('bg'), '#FFFFFF');
  assert.equal(elderlyToken('bg2'), '#F2F2F2');    // 历史块是 #F5F5F5
  assert.equal(elderlyToken('danger'), '#8E4141');
});

test('老人端强调色：语义色对画布底过 1.4.11，四个告警色过 AAA 正文 7:1', () => {
  for (const tk of ['danger','warn','accent2','accent3','accent','rule','focus-ring','rec-fill']) {
    const c = elderlyToken(tk);
    assert.ok(c, '--'+tk+' 未在 elderly-mode 下定义');
    assert.ok(ratio(c, '#FFFFFF') >= 3.0, `${tk} ${c} 对 bg 仅 ${ratio(c,'#FFFFFF').toFixed(2)} < 3`);
  }
  for (const tk of ['danger','warn','accent2','accent3']) {
    assert.ok(ratio(elderlyToken(tk), '#FFFFFF') >= 7.0, tk+' 未达 AAA 正文 7:1');
  }
});

test('字号阶梯地板越过 14pt，且不把非老人端紧凑档误读为基础值', () => {
  for (const k of ['caption','body-sm','body','lead','title','display']) {
    const px = rampTok('t-'+k) * ELDER_ROOT;
    assert.ok(px >= 18.66, `--t-${k} = ${px.toFixed(2)}px < 14pt`);
    const compact = (NON_ELDER.match(new RegExp('--t-'+k+'\\s*:\\s*([0-9.]+)rem'))||[,])[1];
    if (compact) {
      assert.ok(px !== parseFloat(compact)*ELDER_ROOT,
        `--t-${k} 取到了紧凑档 ${compact}rem，反向选择器被误判为老人端块`);
    }
  }
});

test('SVG 文本字号由 CSS 覆盖，且覆盖必须穷尽 render.js 实际写的值', () => {
  const RENDER = fs.readFileSync(path.join(SRC, 'ui/render.js'), 'utf8');
  const hardcoded = [...new Set([...RENDER.matchAll(/setAttribute\('font-size',\s*(?:[^)]*\?)?\s*'?(\d+)'?/g)].map(m => m[1]))];
  assert.ok(hardcoded.length >= 2, '未从 render.js 解析出硬编码字号，本断言失去意义: ' + hardcoded);
  for (const v of hardcoded) {
    assert.ok(new RegExp('\\[font-size="'+v+'"\\]\\s*\\{\\s*font-size:').test(live),
      `render.js 写了 font-size="${v}"，但没有对应的 CSS 覆盖`);
  }
  assert.ok(/\.nodes-group text\[font-size="12"\]\s*\{\s*font-size:\s*1\.05rem/.test(live));
  assert.ok(/\.nodes-group text\[font-size="14"\]\s*\{\s*font-size:\s*1\.25rem/.test(live));
  assert.ok(/\.nodes-group text\[font-size="10"\]\s*\{\s*font-size:\s*0\.9rem/.test(live));
  // 覆盖之所以不需要 !important，是因为 presentation attribute 优先级最低；
  // 一旦出现 !important，说明这条依据已经不成立，整套"零 JS 改动"的前提就塌了
  const overrides = [...live.matchAll(/[^{}]*\[font-size="\d+"\][^{}]*\{([^}]*)\}/g)].map(m => m[1]);
  assert.ok(overrides.length >= 3, '覆盖规则数量异常: ' + overrides.length);
  assert.equal(overrides.filter(o => o.includes('!important')).length, 0,
    '未加 layer 的 CSS 本应压得住 presentation attribute，用 !important 说明前提变了');
  // 光锁上面三条会漏掉"把 .node-sub 等语义类改回写死 px"这种回归，故再锁不变式：
  const textRules = [...live.matchAll(/\.(node-label|node-label--self|node-sub)\s*\{([^}]*)\}/g)];
  assert.ok(textRules.length >= 3, '语义类数量异常: ' + textRules.length);
  for (const [, cls, body] of textRules) {
    assert.ok(/font-size:\s*var\(--t-/.test(body), '.' + cls + ' 不再引用 --t-* token');
    assert.ok(!/font-size:\s*\d+px/.test(body), '.' + cls + ' 出现写死的 px 字号');
    assert.ok(!body.includes('!important'), '.' + cls + ' 用了 !important');
  }
});

test('节点色唯一真相在 state.js：CSS 不得留任何 circle[fill 规则', () => {
  const all = [...live.matchAll(/([^{}]*)\{([^{}]*)\}/g)];
  const decls = all.filter(m => /circle\[fill\s*=/.test(m[1]));
  // 反向自查：锚点解析必须有足够多的规则块，否则"零命中"不代表干净
  assert.ok(all.length > 200, 'CSS 规则块解析数量异常: ' + all.length);
  assert.equal(decls.length, 0,
    '存在节点圆 CSS 覆盖，会让 leftPanel.js:542 的图例与图不同色: ' + decls.map(d => d[1].trim().slice(0, 70)));
});

test('NODE_TYPES 六类同时满足白字≥4.5 与对两种画布底≥3', () => {
  assert.equal(Object.keys(NT).length, 6);
  for (const ghost of ['custom','space','time','emotion']) assert.ok(!(ghost in NT));
  for (const [k,c] of Object.entries(NT)) {
    assert.ok(ratio('#FFFFFF', c) >= 4.5, `${k} 白字 ${ratio('#FFFFFF',c).toFixed(2)} < 4.5`);
    assert.ok(ratio(c, '#FFFFFF') >= 3.0, `${k} 对老人画布 ${ratio(c,'#FFFFFF').toFixed(2)} < 3`);
    assert.ok(ratio(c, '#F7F4EE') >= 3.0, `${k} 对标准画布 ${ratio(c,'#F7F4EE').toFixed(2)} < 3`);
  }
});

test('EDGE_TYPES 四条边色对画布底过 3:1（1.4.11）', () => {
  const et = Object.fromEntries([...(STATE.match(/const EDGE_TYPES\s*=\s*\{([\s\S]*?)\n\};/)||[,''])[1]
    .matchAll(/(\w+)\s*:\s*\{\s*color:\s*'(#[0-9A-Fa-f]{6})'/g)].map(m=>[m[1],m[2]]));
  assert.equal(Object.keys(et).length, 4);
  for (const [k,c] of Object.entries(et)) {
    assert.ok(Math.min(ratio(c,'#FFFFFF'), ratio(c,'#F7F4EE')) >= 3.0,
      `边 ${k} ${c} 不达 3:1`);
  }
});

test('启动与字号：JS 不再无条件挂老人端、不再内联写 --font-size', () => {
  assert.ok(!/classList\.add\(\s*['"]elderly-mode['"]\s*\)/.test(INIT));
  assert.ok(/applyMode\(recallRole\(\)\)/.test(INIT));
  assert.ok(/applyMode\(view\)/.test(HEADER) && !/classList\.remove\(\s*['"]elderly-mode['"]/.test(HEADER));
  for (const [n,s] of [['init.js',INIT],['header.js',HEADER],['main.js',MAIN]]) {
    assert.ok(!/setProperty\(\s*['"]--font-size['"]/.test(s), n+' 仍在写 --font-size');
  }
  assert.ok(/applyMode\(''\)/.test(MAIN), 'getMe 失败分支未归零，会停在老人端');
});

test('3D 星云色板由 NODE_TYPES 派生，不再手抄', () => {
  assert.ok(/import \{ NODE_TYPES \} from '\.\.\/state\.js'/.test(NEBULA));
  assert.ok(/Object\.keys\(NODE_TYPES\)\s*\.forEach/.test(NEBULA));
  assert.ok(/TYPE_COLORS\[k\]\s*=\s*hexToRGBA\(hex\)/.test(NEBULA));
  assert.ok(!/TYPE_COLORS\s*=\s*\{\s*\w+\s*:\s*\[/.test(NEBULA), '仍有 RGBA 字面量');
  assert.ok(/throw new Error\(/.test(NEBULA), '缺少色值合法性守卫');
  // 恒假守卫的判据：不导入 state，就不可能写出 if (state.debug)（state 本无 debug 字段）
  assert.ok(!/import\s*\{[^}]*\bstate\b[^}]*\}\s*from/.test(NEBULA),
    '3D 又导入了 state，恒假的 state.debug 守卫可能回归');
  assert.ok(!/state\.debug/.test(NEBULA), '存在恒假守卫（state 无 debug 字段）');
  // 兜底与 2D 同构：render.js:430 用 NODE_TYPES.item，3D 必须也回退 item
  assert.ok(/TYPE_COLORS\[n\.type\]\s*\|\|\s*TYPE_COLORS\.item/.test(NEBULA),
    '缺 type 时两端兜底不一致，又会造出新的颜色分歧');
});

test('视图切换器未选中态不再用半透明白（原有效对比 1.06:1）', () => {
  // 逐条规则单独取 body：用 [^}]* 跨规则匹配会命中另一条声明，据此断言等于没检查
  const rules = [...live.matchAll(/\.view-mode-btn([^\{]*)\{([^\}]*)\}/g)]
    .map(m => ({ sel: m[1].trim(), body: m[2].trim() }));
  assert.ok(rules.length >= 3, '切换器规则数量异常: ' + rules.length);
  const inactive = rules.filter(r => r.sel.includes(':not(.active)'));
  assert.ok(inactive.length >= 2, '未选中态规则少于预期，需复核: ' + inactive.length);
  for (const r of inactive) {
    assert.ok(/color:\s*var\(--ink2\)|color:\s*#0A0A0A/.test(r.body),
      '未选中态仍是半透明白前景: ' + r.body);
  }
  assert.ok(!/\.view-mode-btn[^\{]*\{[^\}]*rgba\(255,\s*255,\s*255,\s*0?\.6\)/.test(live),
    '仍有 rgba(255,255,255,0.6) 作前景');
  assert.ok(/\.view-switcher-3d\s*\{[^\}]*background:\s*var\(--bg2\)/.test(live),
    '切换器底仍是半透明黑');
  const base = rules.find(r => r.sel === '');
  assert.ok(base && /min-height:\s*44px/.test(base.body), '缺触控尺寸下限');
  assert.ok(ratio('#3D362E', '#EDE7DA') >= 4.5);
});
