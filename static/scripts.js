/* static/scripts.js - Refaktoryzacja: czytelne funkcje, stałe i inicjalizacja */

(function () {
    'use strict';

    // --- Stałe konfiguracyjne ---
    const REFRESH_INTERVAL_MS = 60_000; // odśwież co 60s, gdy nic nie jest wprowadzane
    const MIN_VALID_CHARS = 50; // minimalna liczba "ważnych" znaków
    const ACTIVE_BG = '#d32f2f';
    const INACTIVE_BG = 'gray';

    // --- Elementy DOM (cache) ---
    const czasInput = document.getElementById('czasStart');
    const poleTekstowe = document.getElementById('opisProblemu');
    const licznik = document.getElementById('licznikZnakow');
    const przycisk = document.getElementById('btnZglos');

    // HR: typ i pole "powód"
    const selectTyp = document.getElementById('selectTyp');
    const inputPowod = document.getElementById('inputPowod');

    // --- Pomocnicze funkcje ---
    // Zwraca treść z usuniętymi znakami specjalnymi (liczymy tylko znaczące znaki)
    function getCzystaTresc(tekst) {
        return (tekst || '').replace(/[^a-zA-Z0-9ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]/g, '');
    }

    // Ustawia wygląd i stan przycisku oraz tekst licznika
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

    // Główna funkcja walidacji treści pola z opisem problemu
    function aktualizujWalidacje() {
        if (!poleTekstowe) return;
        const czysta = getCzystaTresc(poleTekstowe.value);
        ustawStanPrzycisku(czysta.length);
    }

    // Inicjalne ustawienie pola czasu na aktualną godzinę
    function inicjujGodzine() {
        if (!czasInput) return;
        const now = new Date();
        const godz = String(now.getHours()).padStart(2, '0');
        const min = String(now.getMinutes()).padStart(2, '0');
        czasInput.value = `${godz}:${min}`;
    }

    // Obsługa wyboru typu (HR) — wymuszanie pola "powód" dla Nadgodzin
    function initSelectTypListener() {
        if (!selectTyp || !inputPowod) return;
        selectTyp.addEventListener('change', function () {
            const wymagane = this.value === 'Nadgodziny';
            inputPowod.required = wymagane;
            inputPowod.classList.toggle('input-required', wymagane);
            inputPowod.placeholder = wymagane ? 'WPISZ POWÓD (Wymagane!)' : 'Powód...';
        });
    }

    // Inicjalizacja po załadowaniu DOM
    document.addEventListener('DOMContentLoaded', function () {
        inicjujGodzine();
        initSelectTypListener();
        if (poleTekstowe) poleTekstowe.addEventListener('input', aktualizujWalidacje);
        // Wywołanie raz, żeby ustawić początkowy stan przycisku/licznika
        aktualizujWalidacje();
    });

    // Auto-refresh: odśwież gdy nikt nic nie wpisuje
    setInterval(function () {
        const aktywne = document.querySelectorAll('input:focus, textarea:focus, select:focus');
        if (aktywne.length === 0) window.location.reload();
    }, REFRESH_INTERVAL_MS);

})();