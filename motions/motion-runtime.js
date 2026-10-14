/* motion-runtime.js — 进场动效激活器（零依赖）
 * 用法：内联或以 script 标签引入（可加 defer）。
 * 自动观察 .motion-fade-up / .motion-fade-in / .motion-stagger，进入视口加 .motion-in。
 */
(function () {
  function activate() {
    var els = document.querySelectorAll('.motion-fade-up, .motion-fade-in, .motion-stagger');
    if (!('IntersectionObserver' in window)) {
      els.forEach(function (el) { el.classList.add('motion-in'); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) {
          e.target.classList.add('motion-in');
          io.unobserve(e.target);
        }
      });
    }, { threshold: 0.15, rootMargin: '0px 0px -40px 0px' });
    els.forEach(function (el) { io.observe(el); });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', activate);
  else activate();
})();
