# Skaner QR z kamerą - Dokumentacja użytkownika

## Przegląd

System **RaportProdukcyjny** został rozszerzony o funkcjonalność skanowania kodów QR za pomocą aparatu w telefonach, tabletach i innych urządzeniach mobilnych.

## Funkcje

### 1. **Logowanie przez QR**
Użytkownicy mogą zalogować się poprzez zeskanowanie kodu QR zawierającego dane logowania.

**Obsługiwane formaty QR dla logowania:**
- JSON: `{"login": "username", "haslo": "password"}`
- Prosty format: `LOGIN:username:password`

**Jak użyć:**
1. Przejdź do strony logowania (`/login`)
2. Kliknij przycisk **"📱 Skanuj QR"**
3. Zezwól przeglądarce na dostęp do kamery
4. Skieruj aparat na kod QR z danymi logowania
5. System automatycznie wypełni formularz i zaloguje użytkownika

### 2. **Skanowanie etykiet palet**
Szybkie skanowanie kodów QR z etykiet palet w magazynie.

**Jak użyć:**
1. W panelu magazynu (Agro Warehouse) kliknij ikonę QR przy polu wprowadzania
2. Zeskanuj kod QR z etykiety palety
3. System automatycznie wypełni odpowiednie pole

**Obsługiwane miejsca:**
- Przyjęcie dostawy (ID palety)
- Wydanie na produkcję (lokalizacja)
- Korekta stanu magazynowego
- Przesunięcia międzymagazynowe

### 3. **Skanowanie lokalizacji**
Skanowanie kodów QR lokalizacji magazynowych (regały, półki).

**Format lokalizacji:**
- `R010101` - regał-rząd-półka
- `A-B-01` - strefa-sekcja-pozycja

## Integracja dla developerów

### Dodanie skanera QR do własnej strony

#### 1. Dodaj skrypty do szablonu HTML:

```html
<!-- W sekcji <head> lub na końcu <body> -->
<script src="https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js"></script>
<script src="{{ url_for('static', filename='js/qr_scanner.js') }}"></script>
```

#### 2. Dodaj modal QR do szablonu:

```html
{% include 'includes/qr_scanner_modal.html' %}
```

#### 3. Wywołaj skaner z kodu JavaScript:

```javascript
// Podstawowe użycie - skanowanie do pola tekstowego
openQrScannerModal('id-pola-docelowego', 'generic');

// Skanowanie dla logowania
openQrScannerModal('login', 'login');

// Skanowanie etykiety palety
openQrScannerModal('pole-nr-palety', 'pallet');

// Skanowanie lokalizacji
openQrScannerModal('pole-lokalizacji', 'location');
```

#### 4. Dodaj przycisk w HTML:

```html
<button onclick="openQrScannerModal('myField', 'generic')">
    📱 Skanuj QR
</button>
```

### Tryby skanowania

| Tryb | Opis | Użycie |
|------|------|--------|
| `login` | Logowanie przez QR | Format: `LOGIN:user:pass` lub JSON |
| `pallet` | Etykieta palety | Automatyczne uppercase, trim |
| `location` | Kod lokalizacji | Wyszukiwanie w dropdown, uppercase |
| `generic` | Ogólne | Bezpośrednie wypełnienie pola |

### Własna obsługa wyniku skanowania

Możesz też użyć klasy `QRScanner` bezpośrednio:

```javascript
const scanner = new QRScanner({
    fps: 10,
    qrbox: { width: 250, height: 250 },
    onSuccess: (decodedText) => {
        console.log('Zeskanowano:', decodedText);
        // Twoja logika
    },
    onError: (errorMessage) => {
        // Obsługa błędów
    }
});

// Uruchom skaner w elemencie o ID 'qr-reader'
await scanner.start('qr-reader');

// Zatrzymaj skaner
await scanner.stop();
```

## Generowanie kodów QR dla logowania

### Backend (Python):

```python
import qrcode
import json

# Wersja JSON (zalecana)
data = {
    "login": "pracownik1",
    "haslo": "haslo123"
}
qr_data = json.dumps(data)

# Lub prosty format
qr_data = "LOGIN:pracownik1:haslo123"

# Generuj QR
img = qrcode.make(qr_data)
img.save("login_qr.png")
```

### Frontend (JavaScript):

```html
<script src="https://cdn.jsdelivr.net/npm/qrcodejs@1.0.0/qrcode.min.js"></script>
<div id="qrcode"></div>

<script>
const data = JSON.stringify({
    login: "pracownik1",
    haslo: "haslo123"
});

new QRCode(document.getElementById("qrcode"), {
    text: data,
    width: 256,
    height: 256
});
</script>
```

## Wymagania

### Przeglądarka:
- Chrome/Edge 53+
- Firefox 36+
- Safari 11+
- Opera 40+

### Uprawnienia:
- Dostęp do kamery (użytkownik musi zaakceptować w przeglądarce)

### HTTPS:
- ⚠️ **Ważne:** Kamery działają tylko na HTTPS (lub localhost)
- W produkcji aplikacja musi być serwowana przez HTTPS

## Rozwiązywanie problemów

### "Nie można uruchomić kamery"
**Możliwe przyczyny:**
1. Brak uprawnień - sprawdź ustawienia przeglądarki
2. Kamera używana przez inną aplikację
3. Połączenie nie jest HTTPS (wymagane w produkcji)

**Rozwiązanie:**
- Sprawdź ustawienia uprawnień w przeglądarce (ikona kłódki w pasku adresu)
- Zamknij inne aplikacje używające kamery
- Upewnij się, że strona działa na HTTPS

### Kod QR nie jest rozpoznawany
**Możliwe przyczyny:**
1. Za mała rozdzielczość kamery
2. Słabe oświetlenie
3. Zniekształcony/uszkodzony kod QR

**Rozwiązanie:**
- Zwiększ oświetlenie
- Trzymaj telefon stabilnie, prostopadle do kodu
- Użyj opcji "Wpisz kod ręcznie" jeśli skanowanie nie działa

### Skaner się nie otwiera
**Możliwe przyczyny:**
1. Skrypt nie został załadowany
2. Błąd JavaScript w konsoli

**Rozwiązanie:**
- Otwórz konsolę deweloperską (F12)
- Sprawdź błędy w zakładce "Console"
- Upewnij się, że wszystkie skrypty są załadowane

## Bezpieczeństwo

### ⚠️ Ostrzeżenia bezpieczeństwa:

1. **NIE drukuj** kodów QR z hasłami w miejscach publicznych
2. **NIE udostępniaj** kodów QR logowania przez e-mail/komunikatory
3. **Używaj** kodów QR tylko w kontrolowanym środowisku (np. terminale produkcyjne)
4. **Generuj** unikalne hasła dla każdego użytkownika
5. **Regularnie zmieniaj** hasła i regeneruj kody QR

### Zalecenia:

- Kody QR logowania powinny być używane tylko na dedykowanych terminalach
- Rozważ użycie tokenów jednoczasowych zamiast stałych haseł
- Monitoruj logi logowania pod kątem podejrzanej aktywności
- Implementuj blokadę konta po wielu nieudanych próbach

## Przykłady użycia

### Przykład 1: Magazynier skanuje paletę

```html
<div class="form-group">
    <label>Numer palety</label>
    <div style="display:flex; gap:8px;">
        <input type="text" id="nr_palety" class="form-control">
        <button onclick="openQrScannerModal('nr_palety', 'pallet')">
            📱 Skanuj
        </button>
    </div>
</div>
```

### Przykład 2: Skaner lokalizacji z fallbackiem

```javascript
// W pliku JS
function handleLocationScan() {
    if (typeof openQrScannerModal === 'function') {
        openQrScannerModal('lokalizacja_field', 'location');
    } else {
        // Fallback - ręczne wprowadzenie
        alert('Skaner niedostępny. Wprowadź lokalizację ręcznie.');
    }
}
```

## API Reference

### Funkcje globalne

#### `openQrScannerModal(targetFieldId, mode)`
Otwiera modal skanera QR.

**Parametry:**
- `targetFieldId` (string) - ID pola docelowego
- `mode` (string) - Tryb: `'login'`, `'pallet'`, `'location'`, `'generic'`

#### `closeQrScannerModal()`
Zamyka modal i zatrzymuje kamerę.

#### `confirmQrScan(decodedText)`
Potwierdza skan i przetwarza wynik.

**Parametry:**
- `decodedText` (string, opcjonalny) - Zeskanowany tekst

### Klasa QRScanner

#### `new QRScanner(config)`
Tworzy nową instancję skanera.

**Config:**
```javascript
{
    fps: 10,                           // Klatki na sekundę
    qrbox: { width: 250, height: 250 }, // Obszar skanowania
    aspectRatio: 1.0,                  // Proporcje
    onSuccess: (text) => {},           // Callback sukcesu
    onError: (err) => {}               // Callback błędu
}
```

#### `scanner.start(elementId)`
Uruchamia skaner w elemencie HTML.

**Parametry:**
- `elementId` (string) - ID elementu kontenera

**Zwraca:** Promise

#### `scanner.stop()`
Zatrzymuje skaner i zwalnia kamerę.

**Zwraca:** Promise

## Changelog

### v1.0.0 (2026-06-02)
- ✅ Dodano obsługę skanowania QR z kamery
- ✅ Integracja z systemem logowania
- ✅ Skanowanie etykiet palet
- ✅ Skanowanie kodów lokalizacji
- ✅ Modal z podglądem kamery
- ✅ Fallback na ręczne wprowadzanie
- ✅ Obsługa różnych formatów QR

## Kontakt i wsparcie

W przypadku problemów lub pytań:
- Sprawdź logi w konsoli deweloperskiej (F12)
- Skontaktuj się z zespołem IT
- Zgłoś issue w systemie ticketowym

---

**Uwaga:** Ta funkcjonalność wymaga nowoczesnej przeglądarki z obsługą WebRTC i dostępu do kamery.
