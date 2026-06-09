# System Przypisywania Palet do Zbiorników Produkcyjnych

## 📋 Przegląd

System umożliwia przypisywanie palet surowców do zbiorników produkcyjnych (BB01-BB24, MZ01-MZ24, KO01-KO24) z automatyczną walidacją i obsługą skanera.

---

## 🔌 API Endpointy

### 1. **Sprawdź stan zbiornika**

**POST** `/agro/api/zbiornik/status`

**Request Body:**
```json
{
  "zbiornik": "BB15"
}
```

**Response (pusty zbiornik):**
```json
{
  "success": true,
  "zbiornik": "BB15",
  "zajety": false,
  "surowce": [],
  "suma_kg": 0
}
```

**Response (zajęty zbiornik):**
```json
{
  "success": true,
  "zbiornik": "BB15",
  "zajety": true,
  "surowce": [
    {
      "nazwa": "Bm3",
      "ilosc_kg": 1250.5,
      "surowiec_id": 123,
      "ruch_id": 456,
      "lokalizacja": "R021002"
    }
  ],
  "suma_kg": 1250.5
}
```

---

### 2. **Opróżnij zbiornik** (zwrot do magazynu)

**POST** `/agro/api/zbiornik/oproznij`

**Request Body:**
```json
{
  "zbiornik": "BB15",
  "komentarz": "Zmiana receptury"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Zbiornik BB15 opróżniony (1 surowców zwrócono)"
}
```

**Co robi:**
- Zwraca wszystkie surowce z zbiornika do magazynu
- Tworzy wpisy ZWROT w magazyn_ruch
- Loguje do palety_historia (ZWROT_Z_PROD)

---

### 3. **Przypisz paletę do zbiornika**

**POST** `/agro/api/zbiornik/przypisz`

**Request Body:**
```json
{
  "zbiornik": "BB15",
  "surowiec_id": 123,
  "ilosc_kg": 1250,  // opcjonalnie - domyślnie cały stan
  "plan_id": 456     // opcjonalnie
}
```

**Response:**
```json
{
  "success": true,
  "message": "Przypisano 1250 kg (Bm3) do zbiornika BB15"
}
```

**Co robi:**
- Zmniejsza stan_magazynowy w magazyn_surowce
- Tworzy wpis PRODUKCJA w magazyn_ruch z przypisaniem zbiornika
- Loguje do palety_historia (WYDANIE_PROD)

---

### 4. **Znajdź paletę po skanowaniu**

**POST** `/agro/api/zbiornik/znajdz-palete`

**Request Body:**
```json
{
  "scan": "SUR000123"  // lub ID: "123"
}
```

**Response:**
```json
{
  "success": true,
  "paleta": {
    "id": 123,
    "nr_palety": "SUR000123",
    "nazwa": "Bm3",
    "stan_kg": 1250,
    "lokalizacja": "R021002"
  }
}
```

---

## 💻 Przykłady Użycia JavaScript

### Przykład 1: Kliknięcie w kafelek zbiornika

```javascript
// Dodaj do istniejących kafelków zbiorników w surowce_w_produkcji.html
function openAssignPalletModal(tankCode) {
    // 1. Sprawdź stan zbiornika
    fetch('/agro/api/zbiornik/status', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ zbiornik: tankCode })
    })
    .then(r => r.json())
    .then(data => {
        if (!data.success) {
            alert('Błąd: ' + data.message);
            return;
        }
        
        if (data.zajety) {
            // Zbiornik zajęty - pyta czy opróżnić
            if (confirm(`Zbiornik ${tankCode} zawiera:\n${data.surowce.map(s => `- ${s.nazwa}: ${s.ilosc_kg} kg`).join('\n')}\n\nOpróżnić zbiornik?`)) {
                emptyTank(tankCode, () => {
                    // Po opróżnieniu, pokaż wybór palety
                    showPalletSelector(tankCode);
                });
            }
        } else {
            // Zbiornik pusty - od razu wybór palety
            showPalletSelector(tankCode);
        }
    });
}

function emptyTank(tankCode, callback) {
    fetch('/agro/api/zbiornik/oproznij', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
            zbiornik: tankCode,
            komentarz: 'Opróżniono przez UI'
        })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showToast('Zbiornik opróżniony', 'success');
            callback();
        } else {
            alert('Błąd: ' + data.message);
        }
    });
}

function showPalletSelector(tankCode) {
    // TODO: Pokaż modal z listą palet lub polem skanera
    const paletaId = prompt('Podaj ID palety do przypisania:');
    if (paletaId) {
        assignPallet(tankCode, paletaId);
    }
}

function assignPallet(tankCode, paletaId) {
    fetch('/agro/api/zbiornik/przypisz', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
            zbiornik: tankCode,
            surowiec_id: parseInt(paletaId)
        })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showToast(data.message, 'success');
            location.reload(); // Odśwież widok
        } else {
            alert('Błąd: ' + data.message);
        }
    });
}
```

### Przykład 2: Obsługa skanera

```javascript
// Nasłuchuj na szybkie wpisywanie (skaner emuluje klawiaturę)
let scanBuffer = '';
let scanTimeout = null;

document.addEventListener('keypress', function(e) {
    // Jeśli modal jest otwarty, zbieraj znaki
    if (!document.getElementById('assignPalletModal')) return;
    
    clearTimeout(scanTimeout);
    
    if (e.key === 'Enter') {
        // Koniec skanowania
        if (scanBuffer.length > 5) {
            handleScan(scanBuffer.trim());
        }
        scanBuffer = '';
    } else {
        scanBuffer += e.key;
        scanTimeout = setTimeout(() => { scanBuffer = ''; }, 100);
    }
});

function handleScan(scannedCode) {
    // Wyszukaj paletę po zeskanowanym kodzie
    fetch('/agro/api/zbiornik/znajdz-palete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scan: scannedCode })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            // Wyświetl znalezioną paletę
            document.getElementById('palletInfo').innerHTML = `
                <strong>${data.paleta.nazwa}</strong><br>
                ${data.paleta.stan_kg} kg<br>
                Lokalizacja: ${data.paleta.lokalizacja}
            `;
            
            // Zapisz ID do przypisania
            document.getElementById('selectedPalletId').value = data.paleta.id;
        } else {
            showToast('Nie znaleziono palety: ' + scannedCode, 'error');
        }
    });
}
```

---

## 🚀 Kroki Wdrożenia

### Krok 1: Zmodyfikuj istniejące kafelki zbiorników

W pliku `templates/agro_warehouse/surowce_w_produkcji.html`, zmień onclick kafelka:

**PRZED:**
```html
<div class="pallet-card" onclick="openTankHistory('{{ tank.zbiornik }}'...">
```

**PO:**
```html
<div class="pallet-card" 
     onclick="openAssignPalletModal('{{ tank.zbiornik }}')"
     style="...">
```

### Krok 2: Dodaj przyciski akcji

W modalu historii zbiornika, dodaj przycisk "Przypisz Paletę":

```html
<div style="margin-top: 20px; display: flex; gap: 10px;">
    <button onclick="openAssignPalletModal(currentTank)" 
            style="background: #3b82f6; color: white; padding: 10px 20px; border-radius: 10px; font-weight: 800; cursor: pointer; border: none;">
        PRZYPISZ PALETĘ
    </button>
    <button onclick="closeTankHistoryModal()" 
            style="background: #f1f5f9; color: #475569; border: none; padding: 10px 20px; border-radius: 10px; font-weight: 800; cursor: pointer;">
        ZAMKNIJ
    </button>
</div>
```

### Krok 3: Stwórz modal przypisywania

Dodaj nowy modal do `templates/agro_warehouse/includes/modals.html`:

```html
<!-- MODAL: Przypisz Paletę do Zbiornika -->
<dialog id="modalAssignTank" class="modal-premium">
    <div class="modal-header">
        <h4 class="modal-title">Przypisz Paletę do <span id="assignTankCode">BB15</span></h4>
        <button class="modal-close" onclick="closeModal('modalAssignTank')">×</button>
    </div>
    <div class="modal-body">
        <input type="hidden" id="selectedPalletId">
        
        <div class="mb-15">
            <label class="form-label">Zeskanuj paletę lub wpisz ID:</label>
            <input type="text" id="palletScanInput" 
                   class="form-input" 
                   placeholder="Zeskanuj kod kreskowy lub wpisz ID..."
                   autofocus>
        </div>
        
        <div id="palletInfo" class="p-10 bg-gray-50 rounded-lg" style="display:none;">
            <!-- Wypełniane przez JS -->
        </div>
        
        <div id="tankStatusInfo" class="mt-10 p-10 bg-warning-light rounded-lg" style="display:none;">
            <!-- Status zbiornika -->
        </div>
    </div>
    <div class="modal-footer">
        <button class="btn btn-outline" onclick="closeModal('modalAssignTank')">Anuluj</button>
        <button class="btn btn-primary" onclick="confirmAssignment()">Przypisz</button>
    </div>
</dialog>
```

---

## 🧪 Testowanie

### Test 1: Sprawdź status zbiornika (PowerShell/curl)

```powershell
# Pusty zbiornik
Invoke-RestMethod -Uri "http://localhost:5000/agro/api/zbiornik/status" `
    -Method POST `
    -Headers @{"Content-Type"="application/json"} `
    -Body '{"zbiornik":"BB15"}' `
    -WebSession $session
```

### Test 2: Przypisz paletę

```powershell
Invoke-RestMethod -Uri "http://localhost:5000/agro/api/zbiornik/przypisz" `
    -Method POST `
    -Headers @{"Content-Type"="application/json"} `
    -Body '{"zbiornik":"BB15","surowiec_id":123}' `
    -WebSession $session
```

---

## 📝 Workflow Użytkownika

1. **Użytkownik klika w kafelek zbiornika** (np. BB15)
2. System sprawdza stan zbiornika `/api/zbiornik/status`
3. **Jeśli zajęty:**
   - Pokazuje zawartość
   - Pyta "Opróżnić?"
   - Wywołuje `/api/zbiornik/oproznij`
4. **Jeśli pusty:**
   - Pokazuje modal z polem skanera
   - Użytkownik skanuje paletę LUB wpisuje ID
   - System wywołuje `/api/zbiornik/znajdz-palete`
   - Pokazuje informacje o palecie
   - Użytkownik klika "Przypisz"
   - System wywołuje `/api/zbiornik/przypisz`
   - Odświeża widok

---

## ✅ Status Implementacji

- [x] Backend endpoints (tank_assignment.py)
- [x] API walidacja zbiorników (BB/MZ/KO)
- [x] Integracja z AgroWarehouseService.use_for_production()
- [x] Obsługa opróżniania zbiornika
- [x] Wyszukiwanie palety po skanowaniu
- [ ] UI Modal (do zrobienia)
- [ ] JavaScript integracja ze stroną (do zrobienia)
- [ ] Obsługa skanera kodów kreskowych (do zrobienia)

---

## 🔜 Następne Kroki

1. **Dodaj modal UI** - skopiuj strukturę z `warehouse/popups/add_pallet.html`
2. **Integruj z surowce_w_produkcji.html** - zmień onclick na kafelkach
3. **Dodaj JavaScript** - funkcje openAssignPalletModal, assignPallet, handleScan
4. **Testuj na dev** - sprawdź workflow end-to-end
5. **Deploy na produkcję** - po zatwierdzeniu przez użytkownika

---

## 📞 Jak uruchomić?

**Natychmiastowe testowanie API** (przez Postman/curl/PowerShell):
- Endpointy już działają!
- Użyj przykładów z sekcji "Testowanie"

**Pełne UI** (wymaga dalszej implementacji):
- Modal + JavaScript do dodania
- Szacowany czas: ~1-2h
