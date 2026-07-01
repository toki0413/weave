// ============ UTILS ============
import { state } from './state.js';
import { render } from './ui/render.js';

export function el(tag, attrs, children) {
  var node = document.createElement(tag);
  if (attrs) {
    Object.keys(attrs).forEach(function(k) {
      if (k === 'style') {
        Object.keys(attrs[k]).forEach(function(sk) { node.style[sk] = attrs[k][sk]; });
      } else if (k === 'onclick') {
        node.onclick = attrs[k];
      } else {
        node.setAttribute(k === 'className' ? 'class' : k, attrs[k]);
      }
    });
  }
  if (children) {
    children.forEach(function(c) {
      if (c == null) return;
      node.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    });
  }
  return node;
}

export function elSVG(tag, attrs) {
  var node = document.createElementNS('http://www.w3.org/2000/svg', tag);
  if (attrs) {
    Object.keys(attrs).forEach(function(k) {
      if (k === 'style') {
        Object.keys(attrs[k]).forEach(function(sk) { node.style[sk] = attrs[k][sk]; });
      } else {
        node.setAttribute(k === 'className' ? 'class' : k, attrs[k]);
      }
    });
  }
  return node;
}

export function switchView(view) {
  state.view = view;
  document.documentElement.classList.remove('elderly-mode', 'family-mode', 'doctor-mode');
  document.documentElement.classList.add(view + '-mode');
  document.body.className = 'mode-' + view;
  render();
}
