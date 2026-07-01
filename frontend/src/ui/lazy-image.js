// ============ 渐进式图片加载 ============
export function createLazyImage(src, placeholder, options) {
  var img = document.createElement('img');
  img.loading = 'lazy';
  img.decoding = 'async';
  if (placeholder) {
    img.src = placeholder;
    img.dataset.src = src;
  } else {
    img.src = src;
  }
  if (options && options.alt) img.alt = options.alt;
  if (options && options.className) img.className = options.className;
  if (options && options.sizes) img.sizes = options.sizes;
  if (options && options.srcset) img.srcset = options.srcset;
  if (options && options.width) img.width = options.width;
  if (options && options.height) img.height = options.height;

  // 如果没有 IntersectionObserver，直接加载原图
  if (!('IntersectionObserver' in window) || !placeholder) {
    if (placeholder) img.src = src;
    return img;
  }

  var observer = new IntersectionObserver(function(entries) {
    entries.forEach(function(entry) {
      if (entry.isIntersecting) {
        var el = entry.target;
        var realSrc = el.dataset.src;
        if (realSrc) {
          el.src = realSrc;
          el.removeAttribute('data-src');
        }
        observer.unobserve(el);
      }
    });
  }, { rootMargin: '200px' });

  observer.observe(img);
  return img;
}
