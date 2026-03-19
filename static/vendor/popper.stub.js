// Minimal Popper stub to satisfy calls when CDN is blocked.
(function(){
  if (typeof window.Popper !== 'undefined') return;
  window.Popper = {
    createPopper: function(){ console.warn('Popper stub: createPopper called'); return { destroy: function(){} }; }
  };
})();
