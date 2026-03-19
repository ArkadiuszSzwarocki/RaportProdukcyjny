// Minimal Tippy.js stub to satisfy tippy(...) calls when CDN is blocked.
(function(){
  if (typeof window.tippy !== 'undefined') return;
  window.tippy = function(selectorOrElements, opts){
    console.warn('tippy stub: initialized — tooltips will not show.');
    return { forEach: function(){}, destroy: function(){} };
  };
})();
