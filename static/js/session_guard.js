/**
 * session_guard.js
 * Zapewnia że:
 * 1. Po wygaśnięciu sesji (401) → redirect do /login natychmiast
 * 2. Gdy aplikacja jest ukryta (minimalizacja, zablokowanie telefonu, zamknięcie taba)
 *    → wysyłamy sygnał wylogowania (beacon) do serwera
 * 3. Po powrocie do aplikacji → sprawdzamy sesję, jeśli wygasła → /login
 */
(function() {
    'use strict';

    // ── 1. GLOBALNY INTERCEPTOR FETCH (wykrywa 401 z dowolnego żądania) ──────────
    const _originalFetch = window.fetch;
    window.fetch = function(input, init) {
        return _originalFetch(input, init).then(function(response) {
            // Jeśli backend zwraca 401 (sesja wygasła / wylogowany)
            if (response.status === 401) {
                // Sprawdź czy to żądanie AJAX (nie nawigacja stronicowa)
                const isAjax = (init && (
                    (init.headers && (
                        (init.headers['X-Requested-With'] === 'XMLHttpRequest') ||
                        (typeof init.headers.get === 'function' && init.headers.get('X-Requested-With') === 'XMLHttpRequest')
                    ))
                ));
                // Przekieruj do logowania — unikaj pętli jeśli już na /login
                if (!window.location.pathname.startsWith('/login')) {
                    window.location.replace('/login');
                }
            }
            return response;
        });
    };

    // ── 2. WYLOGOWANIE PRZY UKRYCIU APLIKACJI (Visibility API) ──────────────────
    // Używamy localStorage do śledzenia kiedy apka była ukryta
    var _hiddenAt = null;

    document.addEventListener('visibilitychange', function() {
        if (document.visibilityState === 'hidden') {
            _hiddenAt = Date.now();
            try {
                localStorage.setItem('session_hidden_at', _hiddenAt.toString());
            } catch(e) {}
        } else if (document.visibilityState === 'visible') {
            // Sprawdź czy upłynął dopuszczalny czas nieaktywności w tle (dostosowany do SESSION_TIMEOUT_MINUTES z serwera, domyślnie 40 minut)
            try {
                var hiddenAtStr = localStorage.getItem('session_hidden_at');
                if (hiddenAtStr) {
                    var hiddenAt = parseInt(hiddenAtStr, 10);
                    var timeAway = Date.now() - hiddenAt;
                    
                    var configEl = document.getElementById('session-timeout-config');
                    var timeoutMinutes = 40;
                    if (configEl) {
                        timeoutMinutes = parseInt(configEl.getAttribute('data-timeout-minutes') || '40', 10);
                    }
                    var maxAwayTime = timeoutMinutes * 60 * 1000; // Dopasowanie do czasu sesji serwerowej
                    
                    if (timeAway > maxAwayTime) {
                        localStorage.removeItem('session_hidden_at');
                        window.location.replace('/logout');
                        return;
                    }
                }
            } catch(e) {}
            
            // Wróciłem do apki w dozwolonym czasie — sprawdź sesję na serwerze
            _checkSessionAlive();
        }
    });

    // ── 3. SPRAWDZENIE SESJI PO POWROCIE ────────────────────────────────────────
    function _checkSessionAlive() {
        // Lekkie żądanie — sprawdza czy sesja jest aktywna
        _originalFetch('/api/notifications?limit=1', {
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        }).then(function(r) {
            if (r.status === 401) {
                // Sesja wygasła podczas gdy apka była ukryta
                window.location.replace('/login');
            }
        }).catch(function() {
            // Brak połączenia — nie rób nic, pozwól użytkownikowi dokończyć
        });
    }

    // ── 4. WYCZYŚĆ CACHE PRZEGLĄDARKI DLA STRONY LOGOUT ─────────────────────────
    // Zapobiega wyświetlaniu starych stron z cache po wylogowaniu
    if (window.location.pathname === '/login') {
        // Jesteśmy na stronie logowania — wyczyść stary stan nawigacji
        if (window.history && window.history.replaceState) {
            window.history.replaceState(null, '', '/login');
        }
    }

    // ── 5. WYKRYCIE POWROTU PRZEZ PRZYCISK WSTECZ ───────────────────────────────
    // Na mobile często użytkownik naciska "wstecz" po wylogowaniu i widzi cached stronę
    window.addEventListener('pageshow', function(e) {
        // e.persisted = true gdy strona pochodzi z BF Cache (pamięci wstecz/naprzód)
        if (e.persisted) {
            // Sprawdź czy sesja nadal aktywna
            _checkSessionAlive();
        }
    });

    // ── 6. WYLOGOWANIE PRZY ZAMKNIĘCIU KARTY/APLIKACJI ───────────────────────────
    window._skipSessionClose = false;

    window._skipTimeout = null;

    // Ignoruj wylogowanie przy kliknięciach na linki i dowolnej interakcji użytkownika
    document.addEventListener('click', function(ev) {
        const a = ev.target.closest && ev.target.closest('a');
        if (a) {
            const href = a.getAttribute('href') || '';
            if (href && href !== '#' && !href.startsWith('javascript:')) {
                window._skipSessionClose = true;
                return;
            }
        }
        // Użytkownik kliknął przycisk lub inny element na stronie - zapobiegaj wylogowaniu przez najbliższe 15s
        window._skipSessionClose = true;
        if (window._skipTimeout) clearTimeout(window._skipTimeout);
        window._skipTimeout = setTimeout(function() { window._skipSessionClose = false; }, 15000);
    }, { capture: true, passive: true });

    // Ignoruj wylogowanie przy wysyłaniu formularzy
    document.addEventListener('submit', function() {
        window._skipSessionClose = true;
    }, { capture: true, passive: true });

    // Ignoruj wylogowanie przy naciśnięciu dowolnego klawisza (interakcja)
    document.addEventListener('keydown', function() {
        window._skipSessionClose = true;
        if (window._skipTimeout) clearTimeout(window._skipTimeout);
        window._skipTimeout = setTimeout(function() { window._skipSessionClose = false; }, 15000);
    }, { capture: true, passive: true });

    // Usunięto problematyczne pagehide i beforeunload wywołujące automatyczny logout (np. przy zwykłym odświeżeniu strony F5)
    // Serwer sam poprawnie wyloguje sesję po upływie zdefiniowanego czasu bezczynności (SESSION_TIMEOUT_MINUTES).

    // ── 7. AKTYWNY LICZNIK SESJI (navbar countdown) ─────────────────────────────
    document.addEventListener('DOMContentLoaded', function() {
        var configEl = document.getElementById('session-timeout-config');
        if (!configEl) return;
        
        var timeoutMinutes = parseInt(configEl.getAttribute('data-timeout-minutes') || '40', 10);
        var maxTime = timeoutMinutes * 60; // w sekundach
        var timeLeft = maxTime;
        var lastTouchTime = Date.now();
        
        var wrapper = document.getElementById('sessionTimeoutWrapper');
        var timerEl = document.getElementById('sessionTimeoutTimer');
        var badgeEl = document.getElementById('sessionTimeoutBadge');
        var iconEl = document.getElementById('sessionTimeoutIcon');
        var labelEl = document.getElementById('sessionTimeoutLabel');
        
        if (!wrapper || !timerEl) return;
        wrapper.style.display = 'flex'; // Pokaż licznik sesji
        
        // Wstrzyknij styl dla pulsu ikony, jeśli nie istnieje
        if (!document.getElementById('session-timer-pulse-style')) {
            var style = document.createElement('style');
            style.id = 'session-timer-pulse-style';
            style.innerHTML = '@keyframes timerPulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.4; transform: scale(1.1); } } .animate-pulse { animation: timerPulse 1s cubic-bezier(0.4, 0, 0.6, 1) infinite; }';
            document.head.appendChild(style);
        }
        
        // Zaktualizuj licznik wizualnie
        function updateTimerDisplay() {
            var minutes = Math.floor(timeLeft / 60);
            var seconds = timeLeft % 60;
            var timeStr = (minutes < 10 ? '0' : '') + minutes + ':' + (seconds < 10 ? '0' : '') + seconds;
            timerEl.textContent = timeStr;
            
            // Kolorystyka i zachowanie
            if (timeLeft > 300) {
                // Ponad 5 minut - spokojny zielony styl
                badgeEl.style.background = 'rgba(16, 185, 129, 0.1)';
                badgeEl.style.borderColor = 'rgba(16, 185, 129, 0.25)';
                badgeEl.style.color = '#10b981';
                iconEl.style.color = '#10b981';
                iconEl.classList.remove('animate-pulse');
                labelEl.textContent = 'Sesja:';
            } else if (timeLeft > 60) {
                // Pomiędzy 1 a 5 minut - ostrzeżenie żółte/pomarańczowe
                badgeEl.style.background = 'rgba(245, 158, 11, 0.15)';
                badgeEl.style.borderColor = 'rgba(245, 158, 11, 0.3)';
                badgeEl.style.color = '#f59e0b';
                iconEl.style.color = '#f59e0b';
                iconEl.classList.add('animate-pulse');
                labelEl.textContent = 'Kończy się za:';
            } else {
                // Mniej niż minuta - krytyczny czerwony styl + pulsująca ikona
                badgeEl.style.background = 'rgba(239, 68, 68, 0.2)';
                badgeEl.style.borderColor = 'rgba(239, 68, 68, 0.4)';
                badgeEl.style.color = '#ef4444';
                iconEl.style.color = '#ef4444';
                iconEl.classList.add('animate-pulse');
                labelEl.textContent = 'Wylogowanie za:';
            }
        }
        
        // Funkcja dotknięcia serwera (touch session)
        function touchServerSession() {
            var now = Date.now();
            // Throttling: dotykaj serwer maksymalnie raz na 30 sekund
            if (now - lastTouchTime > 30000) {
                lastTouchTime = now;
                _originalFetch('/api/notifications?limit=1', {
                    credentials: 'same-origin',
                    headers: { 'X-Requested-With': 'XMLHttpRequest' }
                }).then(function(r) {
                    if (r.status === 401) {
                        window.location.replace('/login');
                    }
                }).catch(function() {});
            }
        }
        
        // Funkcja resetująca lokalny licznik przy aktywności użytkownika
        function resetTimer() {
            timeLeft = maxTime;
            updateTimerDisplay();
            touchServerSession();
        }
        
        // Zdarzenia aktywności użytkownika
        var activityEvents = ['mousemove', 'mousedown', 'keypress', 'touchstart', 'scroll'];
        activityEvents.forEach(function(eventName) {
            document.addEventListener(eventName, resetTimer, { passive: true });
        });
        
        // Odliczanie co sekundę
        updateTimerDisplay();
        var timerInterval = setInterval(function() {
            if (timeLeft > 0) {
                timeLeft--;
                updateTimerDisplay();
            } else {
                clearInterval(timerInterval);
                window.location.replace('/logout');
            }
        }, 1000);
    });

})();
