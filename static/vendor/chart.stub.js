// Minimal Chart.js stub to avoid runtime errors when CDN is blocked.
(function(){
  if (typeof window.Chart !== 'undefined') return;
  function ChartStub(ctx, cfg){
    console.warn('Chart stub: Chart constructor called — charts will not render.');
    this.ctx = ctx; this.config = cfg;
  }
  ChartStub.prototype.update = function(){ console.warn('Chart stub: update()'); };
  ChartStub.prototype.destroy = function(){ console.warn('Chart stub: destroy()'); };
  window.Chart = ChartStub;
})();
