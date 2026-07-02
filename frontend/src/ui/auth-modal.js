// ============ AUTH MODAL ============
// 可选的登录/注册弹窗：注册成功后展示恢复码
import { el } from './components.js';
import { state } from '../state.js';
import { render } from './render.js';
import { withLoading } from './loading.js';
import { showToast } from './toast.js';

import { trapFocus } from './interactions.js';

var _overlay = null;
var _restoreFocus = null;
var _savedFocus = null;

function _close() {
  if (_overlay && _overlay.parentNode) {
    _overlay.parentNode.removeChild(_overlay);
    _overlay = null;
  }
  if (_restoreFocus) {
    _restoreFocus();
    _restoreFocus = null;
  }
  _savedFocus = null;
}

function _input(id, type, label, placeholder) {
  var wrap = el('div', { style: { marginBottom: '14px' } });
  wrap.appendChild(el('label', {
    htmlFor: id,
    style: { display: 'block', marginBottom: '6px', fontSize: '0.9rem', fontWeight: '600' },
  }, label));
  wrap.appendChild(el('input', {
    id: id,
    type: type,
    placeholder: placeholder,
    style: {
      width: '100%',
      padding: '12px',
      fontSize: '1rem',
      border: '1px solid var(--rule)',
      borderRadius: '8px',
      fontFamily: 'inherit',
    },
  }));
  return wrap;
}

function _showError(msg) {
  var err = document.getElementById('auth-error');
  if (err) {
    err.textContent = msg;
    err.style.display = msg ? 'block' : 'none';
  }
}

function _renderRecoveryCode(recoveryCode) {
  var card = el('div', {
    style: {
      background: '#fff',
      borderRadius: '12px',
      padding: '24px',
      maxWidth: '420px',
      width: '90%',
      boxShadow: '0 12px 40px rgba(0,0,0,0.15)',
      textAlign: 'center',
    },
  });
  card.appendChild(el('h2', { style: { color: 'var(--accent-d)', marginBottom: '12px' } }, '请保存恢复码'));
  card.appendChild(el('p', { style: { color: 'var(--ink2)', marginBottom: '16px', lineHeight: '1.6' } },
    '恢复码是忘记密码时找回数据的唯一凭证，请截图或抄写在安全位置。平台不会再次展示。'));
  card.appendChild(el('div', {
    style: {
      background: 'var(--warn-l)',
      border: '1px solid var(--warn)',
      borderRadius: '8px',
      padding: '16px',
      fontSize: '1.1rem',
      fontWeight: '700',
      letterSpacing: '0.05em',
      wordBreak: 'break-all',
      marginBottom: '20px',
      userSelect: 'all',
    },
  }, recoveryCode));
  card.appendChild(el('button', {
    style: {
      padding: '12px 28px',
      fontSize: '1rem',
      border: 'none',
      borderRadius: '8px',
      background: 'var(--accent)',
      color: '#fff',
      cursor: 'pointer',
    },
    onclick: function() {
      _close();
      render();
    },
  }, '我已保存'));

  _overlay.innerHTML = '';
  _overlay.appendChild(card);
}

function _renderForm() {
  var mode = 'login'; // 'login' | 'register'

  var card = el('div', {
    style: {
      background: '#fff',
      borderRadius: '12px',
      padding: '24px',
      maxWidth: '380px',
      width: '90%',
      boxShadow: '0 12px 40px rgba(0,0,0,0.15)',
    },
  });

  var title = el('h2', { style: { marginBottom: '16px', color: 'var(--accent-d)' } }, '登录');
  card.appendChild(title);

  var tabs = el('div', { style: { display: 'flex', gap: '8px', marginBottom: '20px' } });
  var loginTab = el('button', {
    style: {
      flex: 1,
      padding: '10px',
      border: '1px solid var(--rule)',
      borderRadius: '8px',
      background: 'var(--accent)',
      color: '#fff',
      cursor: 'pointer',
    },
  }, '登录');
  var registerTab = el('button', {
    style: {
      flex: 1,
      padding: '10px',
      border: '1px solid var(--rule)',
      borderRadius: '8px',
      background: '#fff',
      color: 'var(--ink2)',
      cursor: 'pointer',
    },
  }, '注册');

  function setMode(m) {
    mode = m;
    title.textContent = m === 'login' ? '登录' : '注册';
    loginTab.style.background = m === 'login' ? 'var(--accent)' : '#fff';
    loginTab.style.color = m === 'login' ? '#fff' : 'var(--ink2)';
    registerTab.style.background = m === 'register' ? 'var(--accent)' : '#fff';
    registerTab.style.color = m === 'register' ? '#fff' : 'var(--ink2)';
    // 注册时才显示手机号和姓名（都是可选）
    phoneWrap.style.display = m === 'register' ? 'block' : 'none';
    nameWrap.style.display = m === 'register' ? 'block' : 'none';
    submitBtn.textContent = m === 'login' ? '登录' : '注册';
    _showError('');
  }

  loginTab.onclick = function() { setMode('login'); };
  registerTab.onclick = function() { setMode('register'); };
  tabs.appendChild(loginTab);
  tabs.appendChild(registerTab);
  card.appendChild(tabs);

  // 登录时是「用户名/手机号」，注册时是「用户名」
  var identifierWrap = _input('auth-identifier', 'text', '用户名', '请输入用户名');
  var phoneWrap = _input('auth-phone', 'text', '手机号（可选）', '便于家属关联');
  phoneWrap.style.display = 'none';
  var nameWrap = _input('auth-name', 'text', '姓名（可选）', '请输入姓名');
  nameWrap.style.display = 'none';
  var passwordWrap = _input('auth-password', 'password', '密码', '至少8位，含字母数字特殊字符');
  card.appendChild(identifierWrap);
  card.appendChild(phoneWrap);
  card.appendChild(nameWrap);
  card.appendChild(passwordWrap);

  var errorMsg = el('div', {
    id: 'auth-error',
    style: {
      color: 'var(--danger)',
      fontSize: '0.85rem',
      marginBottom: '12px',
      display: 'none',
    },
  });
  card.appendChild(errorMsg);

  var submitBtn = el('button', {
    className: 'btn-primary',
    style: { width: '100%', padding: '12px', fontSize: '1rem' },
    onclick: function() {
      var identifier = document.getElementById('auth-identifier').value.trim();
      var password = document.getElementById('auth-password').value;
      var phone = document.getElementById('auth-phone').value.trim();
      var name = document.getElementById('auth-name').value.trim() || identifier;
      if (!identifier || !password || password.length < 6) {
        _showError('请输入用户名和至少6位密码');
        return;
      }

      withLoading(submitBtn, function() {
        return import('../api/client.js').then(function(api) {
          var promise = mode === 'login'
            ? api.login(identifier, password)
            : api.register(identifier, password, 'elderly', name, phone || undefined);
          return promise.then(function(data) {
            if (mode === 'register' && data.recovery_code) {
              _renderRecoveryCode(data.recovery_code);
            } else {
              _close();
              render();
              showToast('登录成功', 'success');
            }
          }).catch(function(err) {
            _showError(err.message || '操作失败');
            throw err;
          });
        });
      }, '处理中…');
    },
  }, '登录');
  card.appendChild(submitBtn);

  var closeBtn = el('button', {
    style: {
      marginTop: '12px',
      width: '100%',
      padding: '10px',
      border: 'none',
      background: 'transparent',
      color: 'var(--muted)',
      cursor: 'pointer',
    },
    onclick: _close,
  }, '取消');
  card.appendChild(closeBtn);

  _overlay.innerHTML = '';
  _overlay.appendChild(card);
}

function showAuthModal() {
  if (_overlay) return;
  _savedFocus = document.activeElement;
  _overlay = el('div', {
    style: {
      position: 'fixed',
      inset: 0,
      background: 'rgba(31,27,22,0.5)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 9999,
    },
    role: 'dialog',
    'aria-modal': 'true',
    'aria-label': '登录 / 注册',
  });
  document.body.appendChild(_overlay);
  _renderForm();
  // 焦点管理：聚焦第一个输入框
  var identifierInput = document.getElementById('auth-identifier');
  if (identifierInput) identifierInput.focus();
  // 焦点陷阱
  _restoreFocus = trapFocus(_overlay, _savedFocus);
}

export { showAuthModal };
