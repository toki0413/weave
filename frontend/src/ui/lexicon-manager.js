// ============ 自定义词典管理 UI ============
// 弹窗：按类型分组展示词条，支持增删、批量导入、搜索过滤
import { el } from './components.js';
import {
  getLexicon,
  addLexiconWord,
  deleteLexiconWord,
  importLexicon,
} from '../api/client.js';
import { trapFocus } from './interactions.js';

// 类型元信息：标签 + 颜色 + 图标
var TYPE_META = {
  person: { label: '人物', color: '#4A7C4A', icon: '👤' },
  place:  { label: '地点', color: '#3D6FA8', icon: '📍' },
  event:  { label: '事件', color: '#B86B4C', icon: '⚡' },
  item:   { label: '物品', color: '#B8860B', icon: '📦' },
};
var TYPE_ORDER = ['person', 'place', 'event', 'item'];

// 当前会话状态
var session = {
  overlay: null,
  words: [],         // 全部词条
  filter: '',        // 搜索关键字
  filterType: '',    // 类型过滤，空为全部
  loading: false,
  msg: null,         // 临时提示 { type, text }
  _savedFocus: null,
  _restoreFocus: null,
};

// 打开词典管理弹窗
export function openLexiconPanel() {
  closeLexiconPanel();
  session._savedFocus = document.activeElement;
  var overlay = el('div', {
    className: 'lexicon-overlay',
    id: 'lexicon-overlay',
    role: 'dialog',
    'aria-modal': 'true',
    'aria-label': '自定义词典管理',
  });
  document.body.appendChild(overlay);
  session.overlay = overlay;
  session.words = [];
  session.filter = '';
  session.filterType = '';
  session.msg = null;
  paintLoading('正在加载词典…');
  loadWords();
  session._restoreFocus = trapFocus(overlay, session._savedFocus);
}

export function closeLexiconPanel() {
  if (session.overlay && session.overlay.parentNode) {
    session.overlay.parentNode.removeChild(session.overlay);
  }
  if (session._restoreFocus) {
    session._restoreFocus();
    session._restoreFocus = null;
  }
  session._savedFocus = null;
  session.overlay = null;
}

// 拉取词条
function loadWords() {
  session.loading = true;
  getLexicon()
    .then(function(rows) {
      session.loading = false;
      session.words = rows || [];
      paint();
    })
    .catch(function(err) {
      session.loading = false;
      session.msg = { type: 'error', text: '加载失败：' + (err && err.message ? err.message : '未知错误') };
      paint();
    });
}

// 渲染整个弹窗
function paint() {
  if (!session.overlay) return;
  var modal = buildShell();

  // 顶部说明
  modal.body.appendChild(el('p', { className: 'lexicon-desc' },
    '添加家人名字、常去地点等专属词条，系统会在解析叙述时优先识别它们。'));

  // 添加表单
  modal.body.appendChild(renderAddForm());

  // 搜索 + 过滤
  modal.body.appendChild(renderFilterBar());

  // 词条列表（按类型分组）
  modal.body.appendChild(renderGroups());

  // 批量导入
  modal.body.appendChild(renderImportArea());

  paint_(modal.container);
}

function paintLoading(text) {
  var modal = buildShell();
  modal.body.appendChild(el('div', { className: 'lexicon-loading' }, text || '加载中…'));
  paint_(modal.container);
}

function buildShell() {
  var container = el('div', { className: 'lexicon-modal' });
  var header = el('div', { className: 'lexicon-modal-header' }, [
    el('h2', { className: 'lexicon-modal-title' }, '我的词典'),
    el('button', {
      className: 'lexicon-close-btn',
      'aria-label': '关闭',
      onclick: closeLexiconPanel,
    }, '✕'),
  ]);
  var body = el('div', { className: 'lexicon-modal-body' });
  container.appendChild(header);
  container.appendChild(body);
  return { container: container, body: body };
}

function paint_(node) {
  if (!session.overlay) return;
  session.overlay.innerHTML = '';
  session.overlay.appendChild(node);
}

// 添加词条表单
function renderAddForm() {
  var wrap = el('div', { className: 'lexicon-add-form' });

  var input = el('input', {
    type: 'text',
    className: 'lexicon-input',
    placeholder: '输入词条，如：小明 / 社区医院 / 跳广场舞',
    id: 'lexicon-word-input',
    maxlength: '100',
  });

  var typeSelect = el('select', { className: 'lexicon-select', id: 'lexicon-type-select' });
  TYPE_ORDER.forEach(function(t) {
    var opt = el('option', { value: t }, TYPE_META[t].label);
    typeSelect.appendChild(opt);
  });

  var msgBox = el('div', { className: 'lexicon-form-msg', id: 'lexicon-form-msg' });

  var addBtn = el('button', {
    className: 'lexicon-add-btn',
    onclick: function() {
      var word = input.value.trim();
      if (!word) {
        showFormMsg('请输入词条内容', 'error');
        return;
      }
      var wordType = typeSelect.value;
      addBtn.disabled = true;
      addBtn.textContent = '添加中…';
      addLexiconWord(word, wordType)
        .then(function() {
          input.value = '';
          addBtn.disabled = false;
          addBtn.textContent = '添加';
          // 直接本地追加，避免重新拉全量
          session.words.unshift({
            id: '', // 后端返回的 id 在刷新前不可用，删除时按 word+type 兜底
            word: word,
            word_type: wordType,
            created_at: new Date().toISOString(),
            _pending: true,
          });
          showFormMsg('已添加', 'ok');
          paint();
        })
        .catch(function(err) {
          addBtn.disabled = false;
          addBtn.textContent = '添加';
          showFormMsg('添加失败：' + (err && err.message ? err.message : '未知错误'), 'error');
        });
    },
  }, '添加');

  // 回车提交
  input.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') { e.preventDefault(); addBtn.click(); }
  });

  wrap.appendChild(input);
  wrap.appendChild(typeSelect);
  wrap.appendChild(addBtn);
  wrap.appendChild(msgBox);
  return wrap;
}

function showFormMsg(text, type) {
  var box = document.getElementById('lexicon-form-msg');
  if (!box) return;
  box.textContent = text;
  box.className = 'lexicon-form-msg ' + (type === 'ok' ? 'ok' : 'error');
  if (type === 'ok') {
    setTimeout(function() {
      if (box) { box.textContent = ''; box.className = 'lexicon-form-msg'; }
    }, 1500);
  }
}

// 搜索 + 类型过滤
function renderFilterBar() {
  var wrap = el('div', { className: 'lexicon-filter-bar' });

  var search = el('input', {
    type: 'text',
    className: 'lexicon-search',
    placeholder: '搜索词条…',
    value: session.filter,
    oninput: function(e) { session.filter = e.target.value; refreshListOnly(); },
  });

  var typeFilter = el('select', {
    className: 'lexicon-select',
    onchange: function(e) { session.filterType = e.target.value; refreshListOnly(); },
  });
  typeFilter.appendChild(el('option', { value: '' }, '全部类型'));
  TYPE_ORDER.forEach(function(t) {
    var opt = el('option', { value: t, selected: session.filterType === t }, TYPE_META[t].label);
    typeFilter.appendChild(opt);
  });

  wrap.appendChild(search);
  wrap.appendChild(typeFilter);
  return wrap;
}

// 只刷新列表区域，避免输入框失焦
function refreshListOnly() {
  var listWrap = document.getElementById('lexicon-groups-wrap');
  if (!listWrap) return;
  listWrap.innerHTML = '';
  listWrap.appendChild(renderGroupsContent());
}

// 按类型分组的词条列表
function renderGroups() {
  var wrap = el('div', { id: 'lexicon-groups-wrap' });
  wrap.appendChild(renderGroupsContent());
  return wrap;
}

function renderGroupsContent() {
  var fragment = el('div', {});

  // 过滤
  var filter = session.filter.trim().toLowerCase();
  var filtered = session.words.filter(function(w) {
    if (session.filterType && w.word_type !== session.filterType) return false;
    if (filter && w.word.toLowerCase().indexOf(filter) === -1) return false;
    return true;
  });

  if (session.loading) {
    fragment.appendChild(el('div', { className: 'lexicon-loading' }, '加载中…'));
    return fragment;
  }

  if (filtered.length === 0) {
    fragment.appendChild(el('div', { className: 'lexicon-empty' },
      session.words.length === 0 ? '还没有自定义词条，添加第一个吧' : '没有匹配的词条'));
    return fragment;
  }

  // 按 type 分桶
  var buckets = {};
  TYPE_ORDER.forEach(function(t) { buckets[t] = []; });
  filtered.forEach(function(w) {
    if (buckets[w.word_type]) buckets[w.word_type].push(w);
  });

  TYPE_ORDER.forEach(function(t) {
    if (!buckets[t] || buckets[t].length === 0) return;
    var meta = TYPE_META[t];
    var group = el('div', { className: 'lexicon-group' });
    group.appendChild(el('div', { className: 'lexicon-group-title' }, [
      el('span', { className: 'lexicon-group-icon', style: { color: meta.color } }, meta.icon),
      el('span', {}, meta.label),
      el('span', { className: 'lexicon-group-count' }, '(' + buckets[t].length + ')'),
    ]));

    var chips = el('div', { className: 'lexicon-chips' });
    buckets[t].forEach(function(w) {
      chips.appendChild(renderChip(w));
    });
    group.appendChild(chips);
    fragment.appendChild(group);
  });

  return fragment;
}

// 单个词条 chip
function renderChip(w) {
  var meta = TYPE_META[w.word_type] || TYPE_META.item;
  var chip = el('div', {
    className: 'lexicon-chip' + (w._pending ? ' pending' : ''),
    title: w.word,
  });
  chip.appendChild(el('span', { className: 'lexicon-chip-dot', style: { background: meta.color } }));
  chip.appendChild(el('span', { className: 'lexicon-chip-text' }, w.word));
  var delBtn = el('button', {
    className: 'lexicon-chip-del',
    'aria-label': '删除 ' + w.word,
    title: '删除',
    onclick: function(e) {
      e.stopPropagation();
      if (!confirm('删除词条「' + w.word + '」？')) return;
      delBtn.disabled = true;
      deleteLexiconWord(w.id)
        .then(function() {
          // 本地移除
          session.words = session.words.filter(function(x) { return x !== w; });
          refreshListOnly();
        })
        .catch(function(err) {
          delBtn.disabled = false;
          alert('删除失败：' + (err && err.message ? err.message : '未知错误'));
        });
    },
  }, '✕');
  chip.appendChild(delBtn);
  return chip;
}

// 批量导入区
function renderImportArea() {
  var wrap = el('div', { className: 'lexicon-import-area' });
  wrap.appendChild(el('div', { className: 'lexicon-section-title' }, '批量导入'));
  wrap.appendChild(el('div', { className: 'lexicon-import-hint' },
    '每行一个，格式：词,类型（类型可选：person / place / event / item），如：小明,person'));

  var ta = el('textarea', {
    className: 'lexicon-textarea',
    placeholder: '小明,person\n社区医院,place\n跳广场舞,event\n老花镜,item',
    rows: '5',
    id: 'lexicon-import-ta',
  });
  wrap.appendChild(ta);

  var msgBox = el('div', { className: 'lexicon-form-msg', id: 'lexicon-import-msg' });

  var btnRow = el('div', { className: 'lexicon-import-actions' });
  var importBtn = el('button', {
    className: 'lexicon-import-btn',
    onclick: function() {
      var text = ta.value.trim();
      if (!text) {
        showImportMsg('请先输入要导入的内容', 'error');
        return;
      }
      var items = parseImportText(text);
      if (items.length === 0) {
        showImportMsg('未解析到有效词条，请检查格式', 'error');
        return;
      }
      importBtn.disabled = true;
      importBtn.textContent = '导入中…';
      importLexicon(items)
        .then(function(created) {
          importBtn.disabled = false;
          importBtn.textContent = '导入';
          // 把新增的合并到本地列表
          (created || []).forEach(function(c) {
            session.words.unshift({
              id: c.id,
              word: c.word,
              word_type: c.word_type,
              created_at: c.created_at,
            });
          });
          ta.value = '';
          showImportMsg('成功导入 ' + (created ? created.length : 0) + ' 条', 'ok');
          refreshListOnly();
        })
        .catch(function(err) {
          importBtn.disabled = false;
          importBtn.textContent = '导入';
          showImportMsg('导入失败：' + (err && err.message ? err.message : '未知错误'), 'error');
        });
    },
  }, '导入');
  btnRow.appendChild(importBtn);
  wrap.appendChild(btnRow);
  wrap.appendChild(msgBox);
  return wrap;
}

// 解析批量导入文本
function parseImportText(text) {
  var lines = text.split(/\r?\n/);
  var validTypes = { person: 1, place: 1, event: 1, item: 1 };
  var items = [];
  lines.forEach(function(line) {
    var s = line.trim();
    if (!s) return;
    var parts = s.split(/[,，]/).map(function(x) { return x.trim(); });
    if (parts.length === 0) return;
    var word = parts[0];
    if (!word) return;
    // 没填类型默认 item
    var wordType = parts[1] ? parts[1].toLowerCase() : 'item';
    if (!validTypes[wordType]) wordType = 'item';
    items.push({ word: word, word_type: wordType });
  });
  return items;
}

function showImportMsg(text, type) {
  var box = document.getElementById('lexicon-import-msg');
  if (!box) return;
  box.textContent = text;
  box.className = 'lexicon-form-msg ' + (type === 'ok' ? 'ok' : 'error');
  if (type === 'ok') {
    setTimeout(function() {
      if (box) { box.textContent = ''; box.className = 'lexicon-form-msg'; }
    }, 2000);
  }
}
