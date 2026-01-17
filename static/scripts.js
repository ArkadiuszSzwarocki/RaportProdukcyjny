/* static/scripts.js */

document.addEventListener("DOMContentLoaded", function() {
    const czasInput = document.getElementById('czasStart');
    // Usunęliśmy pobieranie errorTime, bo znosimy limit czasu
    const poleTekstowe = document.getElementById('opisProblemu');
    const licznik = document.getElementById('licznikZnakow');
    const przycisk = document.getElementById('btnZglos');
    
    // --- OBSŁUGA FORMULARZA HR (WYMUSZANIE POWODU) ---
    const selectTyp = document.getElementById('selectTyp');
    const inputPowod = document.getElementById('inputPowod');

    if (selectTyp && inputPowod) {
        selectTyp.addEventListener('change', function() {
            if (this.value === 'Nadgodziny') {
                inputPowod.required = true;
                inputPowod.classList.add('input-required');
                inputPowod.placeholder = "WPISZ POWÓD (Wymagane!)";
            } else {
                inputPowod.required = false;
                inputPowod.classList.remove('input-required');
                inputPowod.placeholder = "Powód...";
            }
        });
    }

    // --- OBSŁUGA ZGŁASZANIA AWARII (LICZNIK ZNAKÓW) ---
    function aktualizujWalidacje() {
        if (!poleTekstowe || !licznik || !przycisk) return;
        
        // Liczymy znaki (usuwamy znaki specjalne)
        const czystaTresc = poleTekstowe.value.replace(/[^a-zA-Z0-9ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]/g, '');
        const liczbaZnakow = czystaTresc.length;
        
        // ZMIANA: ZMNIEJSZONO LIMIT DO 50 ZNAKÓW
        const wymagane = 50;
        
        licznik.innerText = `Liczba ważnych znaków: ${liczbaZnakow} / ${wymagane}`;
        
        // ZMIANA: USUNIĘTO SPRAWDZANIE GODZINY 15:00 (czasOK jest zawsze true)
        
        if (liczbaZnakow >= wymagane) { 
            licznik.style.color = 'green'; 
            przycisk.disabled = false; 
            przycisk.style.background = '#d32f2f'; // Czerwony (aktywny)
            przycisk.style.cursor = 'pointer'; 
            przycisk.innerText = 'ZGŁOŚ PROBLEM'; 
        } else { 
            licznik.style.color = 'red'; 
            przycisk.disabled = true; 
            przycisk.style.background = 'gray'; 
            przycisk.style.cursor = 'not-allowed'; 
            przycisk.innerText = `ZGŁOŚ PROBLEM (Brakuje ${wymagane - liczbaZnakow})`; 
        }
    }

    // Automatyczne ustawienie godziny na obecną
    if (czasInput) { 
        const now = new Date(); 
        const godzina = String(now.getHours()).padStart(2, '0'); 
        const minuta = String(now.getMinutes()).padStart(2, '0'); 
        czasInput.value = `${godzina}:${minuta}`; 
        // Usunęliśmy nasłuchiwanie czasu, bo nie ma już blokady
    }

    if (poleTekstowe) { 
        poleTekstowe.addEventListener('input', aktualizujWalidacje); 
    }
    
    // Uruchomienie przy starcie
    aktualizujWalidacje();
});


// Automatyczne odświeżanie strony co 60 sekund (60000 ms)
// Tylko jeśli nikt nic nie wpisuje (żeby nie skasować wpisywanego tekstu)
setInterval(function() {
    const aktywneElementy = document.querySelectorAll('input:focus, textarea:focus, select:focus');
    if (aktywneElementy.length === 0) {
        // Jeśli użytkownik nic nie pisze -> odśwież
        window.location.reload();
    }
}, 60000);