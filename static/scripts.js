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

        function openSidebar() {
            document.body.classList.add('sidebar-open');
            if (hamburger) hamburger.setAttribute('aria-expanded', 'true');
            if (sidebar) sidebar.setAttribute('aria-hidden', 'false');
            if (overlay) overlay.setAttribute('aria-hidden', 'false');
        }

        function closeSidebar() {
            document.body.classList.remove('sidebar-open');
            if (hamburger) hamburger.setAttribute('aria-expanded', 'false');
            if (sidebar) sidebar.setAttribute('aria-hidden', 'true');
            if (overlay) overlay.setAttribute('aria-hidden', 'true');
        }

        if (hamburger) {
            hamburger.addEventListener('click', function (e) {
                const open = document.body.classList.contains('sidebar-open');
                if (open) closeSidebar(); else openSidebar();
            });
        }
        if (overlay) {
            overlay.addEventListener('click', function () { closeSidebar(); });
        }
        // close on Esc
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') closeSidebar();
        });

        // close sidebar automatically when window resized to large screens
        window.addEventListener('resize', function () {
            if (window.innerWidth > 900) closeSidebar();
        });
    });

    // Auto-refresh: odśwież gdy nikt nic nie wpisuje przez określony czas
    setInterval(function () {
        const aktywne = document.querySelectorAll('input:focus, textarea:focus, select:focus');
        if (aktywne.length === 0 && !skipOpenStopActive()) window.location.reload();
    }, REFRESH_INTERVAL_MS);

})();