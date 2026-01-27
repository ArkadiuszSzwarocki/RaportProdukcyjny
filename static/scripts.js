/* static/scripts.js - Globalna logika aplikacji */

(function () {
    'use strict';

    

    // --- Stałe konfiguracyjne ---
    const REFRESH_INTERVAL_MS = 60_000; // Auto-odświeżanie co 60s
    const MIN_VALID_CHARS = 50; // Walidacja opisu awarii
    const ACTIVE_BG = '#d32f2f';
    const INACTIVE_BG = 'gray';

    // --- ZACHOWYWANIE POZYCJI PRZEWIJANIA (Scroll Preservation) ---
    // Ta funkcja działa na każdej podstronie systemu
    function initScrollPreservation() {
        const scrollKey = 'system_scroll_pos';
        
        // 1. Jeśli mamy zapisaną pozycję, przewiń do niej
        const savedPos = localStorage.getItem(scrollKey);
        if (savedPos) {
            window.scrollTo(0, parseInt(savedPos));
            localStorage.removeItem(scrollKey); // Czyścimy po użyciu
        }

        // 2. Nasłuchuj wysyłania formularzy (każde kliknięcie przycisku "Zapisz", strzałek itp.)
        document.addEventListener('submit', function(e) {
            if (e.target.tagName === 'FORM') {
                localStorage.setItem(scrollKey, window.scrollY);
            }
        });
    }

    // --- Elementy DOM (Dashboard - Awarie) ---
    const czasInput = document.getElementById('czasStart');
    const poleTekstowe = document.getElementById('opisProblemu');
    const licznik = document.getElementById('licznikZnakow');
    const przycisk = document.getElementById('btnZglos');

    // --- Elementy DOM (HR - Obecność) ---
    const selectTyp = document.getElementById('selectTyp');
    const inputPowod = document.getElementById('inputPowod');

    // --- Funkcje pomocnicze ---
    function getCzystaTresc(tekst) {
        return (tekst || '').replace(/[^a-zA-Z0-9ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]/g, '');
    }

    function ustawStanPrzycisku(liczbaZnakow) {
        if (!licznik || !przycisk) return;

        licznik.innerText = `Liczba ważnych znaków: ${liczbaZnakow} / ${MIN_VALID_CHARS}`;

        if (liczbaZnakow >= MIN_VALID_CHARS) {
            licznik.style.color = 'green';
            przycisk.disabled = false;
            przycisk.style.background = ACTIVE_BG;
            przycisk.style.cursor = 'pointer';
            przycisk.innerText = 'ZGŁOŚ PROBLEM';
        } else {
            licznik.style.color = 'red';
            przycisk.disabled = true;
            przycisk.style.background = INACTIVE_BG;
            przycisk.style.cursor = 'not-allowed';
            przycisk.innerText = `ZGŁOŚ PROBLEM (Brakuje ${MIN_VALID_CHARS - liczbaZnakow})`;
        }
    }

    function aktualizujWalidacje() {
        if (!poleTekstowe) return;
        const czysta = getCzystaTresc(poleTekstowe.value);
        ustawStanPrzycisku(czysta.length);
    }

    function inicjujGodzine() {
        if (!czasInput) return;
        const now = new Date();
        const godz = String(now.getHours()).padStart(2, '0');
        const min = String(now.getMinutes()).padStart(2, '0');
        czasInput.value = `${godz}:${min}`;
    }

    function initSelectTypListener() {
        if (!selectTyp || !inputPowod) return;
        selectTyp.addEventListener('change', function () {
            const wymagane = this.value === 'Nadgodziny';
            inputPowod.required = wymagane;
            inputPowod.classList.toggle('input-required', wymagane);
            inputPowod.placeholder = wymagane ? 'WPISZ POWÓD (Wymagane!)' : 'Powód...';
        });
    }

    // --- Ochrona przed auto-reloadem po ustawieniu skip_open_stop ---
    function skipOpenStopActive() {
        try {
            const v = sessionStorage.getItem('skip_open_stop');
            if (v !== '1') return false;
            const key = 'skip_open_stop_ts';
            const now = Date.now();
            const ts = parseInt(sessionStorage.getItem(key) || '0', 10);
            if (!ts) { sessionStorage.setItem(key, String(now)); return true; }
            // zachowaj odstęp ochronny 5s od momentu pierwszego zauważenia flagi
            return (now - ts) < 5000;
        } catch (e) {
            return false;
        }
    }

    // --- INICJALIZACJA ---
    document.addEventListener('DOMContentLoaded', function () {
        // Uruchomienie mechanizmu scrolla
        initScrollPreservation();

        // Uruchomienie logiki Dashboardu (jeśli elementy istnieją)
        inicjujGodzine();
        initSelectTypListener();
        if (poleTekstowe) {
            poleTekstowe.addEventListener('input', aktualizujWalidacje);
            aktualizujWalidacje();
        }

        // --- Responsive sidebar (hamburger + overlay) ---
        const hamburger = document.getElementById('hamburgerBtn');
        const overlay = document.getElementById('sidebarOverlay');
        const sidebar = document.getElementById('appSidebar');
        const navItems = sidebar ? sidebar.querySelectorAll('.nav-item') : [];

        function openSidebar() {
            document.body.classList.add('sidebar-open');
            if (hamburger) hamburger.setAttribute('aria-expanded', 'true');
            // Make sidebar focusable/interactive
            try {
                if (sidebar) { sidebar.inert = false; sidebar.removeAttribute('inert'); sidebar.setAttribute('aria-hidden', 'false'); }
                if (overlay) { overlay.inert = false; overlay.removeAttribute('inert'); overlay.setAttribute('aria-hidden', 'false'); }
            } catch (e) {
                if (sidebar) sidebar.setAttribute('aria-hidden', 'false');
                if (overlay) overlay.setAttribute('aria-hidden', 'false');
            }
        }

        function closeSidebar() {
            document.body.classList.remove('sidebar-open');
            if (hamburger) hamburger.setAttribute('aria-expanded', 'false');
            // If focus is inside the sidebar, move it to the hamburger to avoid aria-hidden on a focused descendant
            try {
                var active = document.activeElement;
                if (sidebar && active && sidebar.contains(active)) {
                    if (hamburger && typeof hamburger.focus === 'function') hamburger.focus();
                    else document.body.focus();
                }
            } catch (e) { /* ignore */ }
            // After ensuring focus moved, set inert and aria-hidden. Use timeout to allow browser to update focus first.
            setTimeout(function(){
                try {
                    if (sidebar) { sidebar.inert = true; sidebar.setAttribute('aria-hidden', 'true'); }
                    if (overlay) { overlay.inert = true; overlay.setAttribute('aria-hidden', 'true'); }
                } catch (e) {
                    if (sidebar) sidebar.setAttribute('aria-hidden', 'true');
                    if (overlay) overlay.setAttribute('aria-hidden', 'true');
                }
            }, 0);
        }

        if (hamburger) {
            hamburger.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation();
                const open = document.body.classList.contains('sidebar-open');
                if (open) closeSidebar(); else openSidebar();
            });
        }
        if (overlay) {
            overlay.addEventListener('click', function () { closeSidebar(); });
        }
        navItems.forEach(item => item.addEventListener('click', closeSidebar));
        // close on Esc
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') closeSidebar();
        });

        // close sidebar automatically when window resized to large screens
        window.addEventListener('resize', function () {
            if (window.innerWidth > 900) closeSidebar();
        });

        // Modal management removed — modale są wyłączone w całej aplikacji.
    });

    // Global click delegation: any element with `data-slide` or `data-slide-html` opens slide-over
    document.addEventListener('click', function(e){
        try{
            var el = e.target.closest && e.target.closest('[data-slide], [data-slide-html], .slide-link');
            if(!el){
                // also intercept anchors that point to API page endpoints (convention: urls containing '/api/' and '_page' or modal-like names)
                var a = e.target.closest && e.target.closest('a[href]');
                if(a){
                    var href = a.getAttribute('href') || '';
                    if(href.indexOf('/api/') !== -1 && (href.indexOf('_page') !== -1 || href.indexOf('dodaj') !== -1 || href.indexOf('edytuj') !== -1 || href.indexOf('confirm_delete') !== -1)){
                        el = a;
                    }
                }
            }
            if(!el) return;
            // prevent default navigation
            e.preventDefault();
            var url = el.getAttribute('data-slide') || el.getAttribute('href');
            var html = el.getAttribute('data-slide-html');
            // allow per-element opt-out via `data-allow-backdrop="false"`
            var allowAttr = el.getAttribute && el.getAttribute('data-allow-backdrop');
            var allowBackdrop = allowAttr === 'false' ? false : true;
            if(html){ showSlideOver(html, { isHtml: true, backdrop: true, allowBackdropClose: allowBackdrop }); return; }
            if(!url || url === '#' || url.indexOf('javascript:') === 0){ showSlideOver('<div class="p-10">Brak docelowego adresu</div>', { isHtml:true }); return; }
            showSlideOver(url, { backdrop: true, allowBackdropClose: allowBackdrop, transient: false });
        }catch(err){ /* ignore delegation errors */ }
    }, false);

    // Auto-refresh: odśwież gdy nikt nic nie wpisuje przez określony czas
    setInterval(function () {
        const aktywne = document.querySelectorAll('input:focus, textarea:focus, select:focus');
        if (aktywne.length === 0 && !skipOpenStopActive()) window.location.reload();
    }, REFRESH_INTERVAL_MS);

    // Partial reload: fetch current page and replace main content silently
    async function performPartialReload() {
        try{
            const resp = await fetch(window.location.href, { credentials: 'same-origin' });
            if(!resp.ok) return window.location.reload();
            const txt = await resp.text();
            const tmp = document.createElement('div'); tmp.innerHTML = txt;
            const newMain = tmp.querySelector('#mainContent');
            const curMain = document.getElementById('mainContent');
            if(newMain && curMain){
                curMain.innerHTML = newMain.innerHTML;
                // execute inline scripts inside newMain
                newMain.querySelectorAll('script').forEach(s => {
                    try{
                        if (s.src){
                            const sc = document.createElement('script'); sc.src = s.src; sc.async = false; document.body.appendChild(sc);
                        } else {
                            try{ (new Function(s.textContent))(); } catch(e){ console.warn('exec inline partial script failed', e); }
                        }
                    }catch(e){ console.warn('exec script fragment', e); }
                });
                // call update timer function if available
                try{ if(typeof updatePaletaTimers === 'function') updatePaletaTimers(); }catch(e){}
                // custom event
                try{ window.dispatchEvent(new CustomEvent('app:partialReload')); }catch(e){}
                return;
            }
            // fallback full reload
            window.location.reload();
        }catch(e){ console.error('performPartialReload failed', e); window.location.reload(); }
    }

    /* ===================== Slide-over (smukły panel od prawej) ===================== */
    function createSlideOverContainer() {
        let container = document.querySelector('.slide-over-container');
        if (!container) {
            container = document.createElement('div');
            container.className = 'slide-over-container';
            document.body.appendChild(container);
        }
        return container;
    }

    function buildSlideOverElement(html, opts) {
        const wrapper = document.createElement('div');
        wrapper.className = 'slide-over' + (opts && opts.transient ? ' transient' : '');
        wrapper.innerHTML = `
            <div class="so-header"><strong>${opts && opts.title ? opts.title : ''}</strong><button class="so-close" aria-label="Zamknij">&#10005;</button></div>
            <div class="so-body">${html}</div>
            <div class="so-footer"></div>`;
        return wrapper;
    }
    
    function buildCenterModalElement(html, opts){
        const wrapper = document.createElement('div');
        wrapper.className = 'center-modal' + (opts && opts.transient ? ' transient' : '');
        wrapper.innerHTML = `
            <div class="cm-header"><strong>${opts && opts.title ? opts.title : ''}</strong><button class="cm-close" aria-label="Zamknij">&#10005;</button></div>
            <div class="cm-body">${html}</div>
            <div class="cm-footer"></div>`;
        return wrapper;
    }

    function closeSlideOver(el) {
        try {
            if (!el) el = document.querySelector('.slide-over-container .slide-over.open');
            if (!el) return;
            // remove backdrop
            const bd = document.querySelector('.slide-over-backdrop'); if(bd) bd.classList.remove('show');
            el.classList.remove('open');
            document.body.classList.remove('slide-over-open');
            setTimeout(function(){
                const c = el.parentNode; if(c) c.removeChild(el);
                if(bd && bd.parentNode) bd.parentNode.removeChild(bd);
                // remove container if empty
                const cont = document.querySelector('.slide-over-container');
                if(cont && cont.children.length === 0) cont.remove();
            }, 360);
        } catch(e){ console.warn('closeSlideOver', e); }

    }

    function closeCenterModal(el){
        try{
            if(!el) el = document.querySelector('.center-modal-container .center-modal.open');
            if(!el) return;
            const bd = document.querySelector('.slide-over-backdrop'); if(bd) bd.classList.remove('show');
            el.classList.remove('open'); document.body.classList.remove('slide-over-open');
            setTimeout(function(){
                const c = el.parentNode; if(c) c.removeChild(el);
                if(bd && bd.parentNode) bd.parentNode.removeChild(bd);
                const cont = document.querySelector('.center-modal-container'); if(cont && cont.children.length === 0) cont.remove();
            }, 260);
        }catch(e){ console.warn('closeCenterModal', e); }
    }

    function showSlideOver(urlOrHtml, options) {
        options = options || {};
            const backdrop = options.backdrop !== false; // default true
            const allowBackdropClose = options.allowBackdropClose !== false; // default true
        const isHtml = options.isHtml === true;

        const container = createSlideOverContainer();

        // prepare backdrop
        let bd = document.querySelector('.slide-over-backdrop');
        if (!bd && backdrop) {
            bd = document.createElement('div'); bd.className = 'slide-over-backdrop'; document.body.appendChild(bd);
        }

        function attachAndOpen(html, title) {
            // try to extract only the first form inside html if present
            let content = html;
            try {
                const tmp = document.createElement('div'); tmp.innerHTML = String(html);
                // Prefer extracting a .section-box (full panel) when available —
                // some pages contain many small forms (e.g. per-chip delete buttons)
                // and extracting only the first form results in a tiny, broken slide-over.
                const section = tmp.querySelector('.section-box');
                if (section) {
                    content = section.innerHTML;
                } else {
                    const form = tmp.querySelector('form');
                    if (form) {
                        // remove target attributes that try to open new window
                        form.removeAttribute('target');
                        content = form.outerHTML;
                    } else {
                        const main = tmp.querySelector('main') || tmp;
                        content = main.innerHTML || tmp.innerHTML;
                    }
                }
            } catch(e){ content = html; }

                if(options.center){
                // center modal
                let ccont = document.querySelector('.center-modal-container');
                if(!ccont){ ccont = document.createElement('div'); ccont.className = 'center-modal-container'; document.body.appendChild(ccont); }
                const el = buildCenterModalElement(content || '', { transient: options.transient === true, title: title });
                ccont.appendChild(el);
                if (bd) bd.classList.add('show');
                document.body.classList.add('slide-over-open');
                requestAnimationFrame(()=> el.classList.add('open'));
                const closeBtn = el.querySelector('.cm-close'); if (closeBtn) closeBtn.addEventListener('click', ()=> closeCenterModal(el));

                // Execute any inline scripts included in the response so dynamic handlers bind correctly
                try{
                    const scripts = el.querySelectorAll('script');
                    scripts.forEach(function(old){
                        if(old.src){
                            const s = document.createElement('script');
                            for(let i=0;i<old.attributes.length;i++){ const a = old.attributes[i]; s.setAttribute(a.name, a.value); }
                            s.src = old.src;
                            s.async = false;
                            old.parentNode.replaceChild(s, old);
                        } else {
                            try{ (new Function(old.innerHTML))(); } catch(e){ console.warn('exec center inline script failed', e); }
                            // remove original to avoid duplicate execution later
                            old.parentNode.removeChild(old);
                        }
                    });
                }catch(e){ console.warn('execute center scripts failed', e); }

                if(html){ showSlideOver(html, { isHtml: true, backdrop: true, allowBackdropClose: true }); return; }

                showSlideOver(url, { backdrop: true, allowBackdropClose: true, transient: false });
                try{
                    const forms = el.querySelectorAll('form');
                    forms.forEach(function(innerForm){
                        innerForm.addEventListener('submit', function(evt){
                            evt.preventDefault();
                            const url = innerForm.getAttribute('action') || window.location.href;
                            const method = (innerForm.getAttribute('method') || 'POST').toUpperCase();
                            const data = new URLSearchParams(new FormData(innerForm));
                            const numericEntered = Array.from(innerForm.querySelectorAll('input, textarea')).some(i=> /\d/.test((i.value||'')));
                            fetch(url, { method: method, body: data, credentials: 'same-origin', headers:{'X-Requested-With':'XMLHttpRequest'} })
                            .then(async function(resp){
                                if(resp.status === 401){ window.location.href = '/login'; return; }
                                if(resp.redirected && resp.url){ closeCenterModal(el); performPartialReload(); return; }
                                if(resp.status === 204){ if(typeof showToast === 'function') showToast('OK','success'); closeCenterModal(el); performPartialReload(); return; }
                                const txt = await resp.text();
                                try{ const j = JSON.parse(txt); if(j && j.success){ if(typeof showToast === 'function') showToast(j.message || 'OK','success'); closeCenterModal(el); performPartialReload(); } else { if(typeof showToast === 'function') showToast(j && j.message ? j.message : 'Zwrócono odpowiedź', 'info'); } }
                                catch(e){ if(numericEntered){ if(typeof showToast === 'function') showToast('Zapisano','success'); closeCenterModal(el); performPartialReload(); } else { const tmp2 = document.createElement('div'); tmp2.innerHTML = txt; const newForm = tmp2.querySelector('form'); const body = el.querySelector('.cm-body'); if(newForm) { body.innerHTML = newForm.outerHTML; } else if(tmp2.innerHTML) { body.innerHTML = tmp2.innerHTML; } } }
                            }).catch(err=>{ console.error('Center modal form submit failed', err); if(typeof showToast === 'function') showToast('Błąd sieci','danger'); });
                        });
                    });
                }catch(e){ console.warn('rebind center form error', e); }
                return;
            }
            // original slide-over path
            const el = buildSlideOverElement(content || '', { transient: options && options.transient === true, title: title });
            container.appendChild(el);

            // Execute any inline scripts included in the slide-over HTML so event listeners are bound
            try{
                const scripts = el.querySelectorAll('script');
                scripts.forEach(function(old){
                    if(old.src){
                        const s = document.createElement('script');
                        for(let i=0;i<old.attributes.length;i++){ const a = old.attributes[i]; s.setAttribute(a.name, a.value); }
                        s.src = old.src; s.async = false; old.parentNode.replaceChild(s, old);
                    } else {
                        try{ (new Function(old.innerHTML))(); } catch(e){ console.warn('exec slide-over inline script failed', e); }
                        old.parentNode.removeChild(old);
                    }
                });
            }catch(e){ console.warn('execute slide-over scripts failed', e); }
            // show backdrop and prevent body scroll
            if (bd) bd.classList.add('show');
            document.body.classList.add('slide-over-open');
            // small delay for transition
            requestAnimationFrame(()=> el.classList.add('open'));
            const closeBtn = el.querySelector('.so-close');
            if (closeBtn) closeBtn.addEventListener('click', ()=> closeSlideOver(el));

            if (bd && allowBackdropClose) bd.addEventListener('click', ()=> closeSlideOver(el));

            // rewire forms inside the slide-over to submit via fetch to avoid full navigation (but keep default if JS unavailable)
            try {
                const forms = el.querySelectorAll('form');
                forms.forEach(function(innerForm){
                    innerForm.addEventListener('submit', function(evt){
                        evt.preventDefault();
                        const url = innerForm.getAttribute('action') || window.location.href;
                        const method = (innerForm.getAttribute('method') || 'POST').toUpperCase();
                        const data = new URLSearchParams(new FormData(innerForm));

                        // detect if user entered any numeric value in the form
                        const numericEntered = Array.from(innerForm.querySelectorAll('input, textarea')).some(i=> /\d/.test((i.value||'')));

                        fetch(url, { method: method, body: data, credentials: 'same-origin', headers:{'X-Requested-With':'XMLHttpRequest'} })
                        .then(async function(resp){
                            if(resp.status === 401){ window.location.href = '/login'; return; }
                            // If server redirected (normal POST->redirect), follow by navigating parent
                            if(resp.redirected && resp.url){ closeSlideOver(el); performPartialReload(); return; }
                            // 204 No Content -> treat as success
                            if(resp.status === 204){ if(typeof showToast === 'function') showToast('OK','success'); closeSlideOver(el); performPartialReload(); return; }
                            const txt = await resp.text();
                            // try to parse JSON success message
                            try{
                                const j = JSON.parse(txt);
                                if(j && j.success){ if(typeof showToast === 'function') showToast(j.message || 'OK','success'); closeSlideOver(el); performPartialReload(); }
                                else { if(typeof showToast === 'function') showToast(j && j.message ? j.message : 'Zwrócono odpowiedź', 'info'); }
                            } catch(e){ 
                                // HTML returned: if numeric was entered assume submission was intended to save and close
                                if(numericEntered){ if(typeof showToast === 'function') showToast('Zapisano','success'); closeSlideOver(el); performPartialReload(); }
                                else {
                                    // replace body with response HTML (e.g., validation errors)
                                    const tmp2 = document.createElement('div'); tmp2.innerHTML = txt; const newForm = tmp2.querySelector('form');
                                    const body = el.querySelector('.so-body'); if(newForm) { body.innerHTML = newForm.outerHTML; }
                                    else if(tmp2.innerHTML) { body.innerHTML = tmp2.innerHTML; }
                                }
                            }
                        }).catch(err=>{ console.error('Slide-over form submit failed', err); if(typeof showToast === 'function') showToast('Błąd sieci','danger'); });
                    });
                });
            } catch(e){ console.warn('rebind form error', e); }
        }

        if (isHtml) {
            attachAndOpen(String(urlOrHtml), options.title || '');
            return;
        }

        // Otherwise fetch the URL and insert content
        fetch(String(urlOrHtml), { credentials: 'same-origin' })
        .then(function(r){ if(r.status === 401){ window.location.href = '/login'; throw new Error('HTTP 401'); } if(!r.ok) throw new Error('HTTP '+r.status); return r.text(); })
        .then(function(txt){
            try{
                // Jeśli serwer zwrócił stronę logowania (użytkownik niezalogowany),
                // nie ładujemy jej w slide-over — zamiast tego przechodzimy pełną stroną
                const lower = (txt || '').toLowerCase();
                if(lower.indexOf('login-page-body') !== -1 || lower.indexOf('zaloguj') !== -1 || lower.indexOf('logowanie') !== -1){
                    // przekieruj przeglądarkę na pełny adres (pozwoli się zalogować)
                    window.location.href = String(urlOrHtml);
                    return;
                }
            }catch(e){ /* ignore detection errors */ }
            attachAndOpen(txt, options.title || '');
        })
        .catch(function(err){ console.error('showSlideOver fetch failed', err); attachAndOpen('<div class="text-muted p-10">Błąd ładowania zawartości</div>', options.title || ''); });
    }

    // Expose globally
    window.showSlideOver = showSlideOver;
    window.closeSlideOver = closeSlideOver;
    window.closeCenterModal = closeCenterModal;

})();