// quick_debug.js — tymczasowy helper do diagnostyki submitów w slide-over/quick-popup
(function(){
    'use strict';
    function isDebugEnabled(){ try{ return sessionStorage.getItem('enable_quick_debug') === '1'; }catch(e){return false;} }
    if(!isDebugEnabled()) return;
    console.info('[quick_debug] enabled');

    async function sendTelemetry(payload){
        try{
            await fetch('/telemetry/openmodal', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload) });
        }catch(e){ console.warn('[quick_debug] failed sendTelemetry', e); }
    }

    document.addEventListener('submit', function(ev){
        try{
            var form = ev.target;
            if(!form || form.tagName !== 'FORM') return;
            // only for slide-over / center modal / quick popup forms
            var inSlide = !!form.closest('.slide-over, .center-modal, .quick-popup, .drawer, .bottom-sheet');
            if(!inSlide) return;
            try{ console.info('[quick_debug] form submit in slide/quick:', form.action, form.method); }catch(e){}
            var fd = new FormData(form);
            var obj = {};
            fd.forEach(function(v,k){ obj[k]=v; });
            try{ console.info('[quick_debug] payload', obj); }catch(e){}
            // send lightweight telemetry (avoid large data)
            sendTelemetry({event:'quick_form_submit', url: form.action, method: form.method, payload: obj, page: location.pathname, ts: new Date().toISOString()});
        }catch(e){ console.warn('[quick_debug] submit handler error', e); }
    }, true);

    // also log clicks on + SZARŻA buttons
    document.addEventListener('click', function(ev){
        try{
            var el = ev.target.closest && ev.target.closest('a, button');
            if(!el) return;
            var txt = (el.innerText||'').trim();
            if(txt.indexOf('SZARŻA') !== -1){
                console.info('[quick_debug] clicked SZARŻA element', txt, el.getAttribute('href') || el.getAttribute('data-slide'));
                sendTelemetry({event:'click_szarza', text: txt, href: el.getAttribute('href')||el.getAttribute('data-slide')||'', page: location.pathname, ts: new Date().toISOString()});
            }
        }catch(e){ }
    }, true);
})();
