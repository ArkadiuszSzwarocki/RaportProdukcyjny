# ✅ CHECKLIST: Email Report Feature Testing

## Pre-Release Testing

### Backend Configuration

- [ ] Zmienna `EMAIL_RECIPIENTS` jest ustawiona w `.env` lub używa domyślnych
- [ ] Endpoint `/api/email-config` zwraca JSON z listą odbiorców
- [ ] Endpoint wymaga `@login_required`
- [ ] Status HTTP 200 dla zalogowanego użytkownika
- [ ] Status HTTP 401 dla niezalogowanego użytkownika

**Test poleceniem:**
```bash
# Zalogowany
curl -X GET http://localhost:8082/api/email-config \
  -H "Cookie: session=YOUR_SESSION" \
  -H "Content-Type: application/json"

# Powinno zwrócić:
# {
#   "recipients": ["email1@...", "email2@..."],
#   "configured": true,
#   "count": 3
# }
```

### Frontend - Button Display

- [ ] Przycisk "📧 Wyślij raport mailem" jest widoczny na dashboard_global
- [ ] Przycisk jest obok przycisku "Zakończ zmianę"
- [ ] Ikona emoji 📧 wyświetla się poprawnie (bez znaków zastępczych)
- [ ] Button ma CSS class: `btn-send-email`
- [ ] Button ma CSS class: `btn-end-shift-large`

**Test:**
1. Zaloguj się do aplikacji
2. Przejdź do `/dashboard`
3. Szukaj przycisku z emoji i textem "Wyślij raport mailem"

### Frontend - Button Styling

- [ ] Przycisk ma niebieski kolor tła (#17a2b8)
- [ ] Przycisk ma biały tekst
- [ ] Na hover: kolor zmienia się na ciemniejszy (#138496)
- [ ] Na hover: pojawia się cień
- [ ] Na active (kliknięcie): kolor zmienia się na najciemniejszy

**Test:**
1. Otwórz DevTools (F12)
2. Sprawdź computed styles dla `#btnSendEmailReport`
3. Najedź myszą i sprawdź efekt hover

### Frontend - JavaScript Event Handler

- [ ] Event listener jest przypisany do `#btnSendEmailReport`
- [ ] Na kliknięcie: skrypt pobiera konfigurację z `/api/email-config`
- [ ] Konsola pokazuje logi: `[EMAIL] Otwieranie poczty dla...`
- [ ] Funkcja `sendEmailReport()` jest zdefiniowana

**Test:**
1. Otwórz DevTools (F12) → Console
2. Kliknij przycisk "Wyślij raport mailem"
3. Szukaj logu: `[EMAIL] Otwieranie poczty dla: 3 odbiorców`

### Mail Client Integration

- [ ] Kliknięcie przycisku otwiera domyślny klient poczty
- [ ] Poczta otworzy się z przedwypełnionym mailem do:
  - ✅ **To**: `lider@example.com,szef@example.com,biuro@example.com`
  - ✅ **Subject**: `Raport produkcyjny z dnia 01.02.2026` (z dzisiejszą datą)
  - ✅ **Body**: Zawiera "Przesyłam raport produkcyjny z dnia..."
- [ ] Tekst wiadomości jest czytelny
- [ ] Adresaci są poprawni

**Test:**
1. Zaloguj się
2. Przejdź do dashboard
3. Kliknij przycisk "📧 Wyślij raport mailem"
4. Poczta powinna się otworzyć z powyższymi danymi

### Error Handling

- [ ] Jeśli `/api/email-config` zwróci błąd (500):
  - Alert: "⚠️ Brak skonfigurowanych odbiorców raportów..."
  - Fallback do domyślnych odbiorców
  - Nie powiela błędu w konsoli (graceful)

- [ ] Jeśli użytkownik nie jest zalogowany:
  - Redirect do `/login`
  - Button jest niedostępny (lub nie wyświetla się)

**Test:**
1. Wyłącz API tymczasowo (symuluj 500 error)
2. Kliknij przycisk
3. Powinna być wiadomość o błędzie
4. Mail powinien się otworzyć z fallbackiem

### Cross-Browser Testing

| Browser | Status | Notes |
|---------|--------|-------|
| Chrome | ☐ | Testuj `mailto:` link |
| Firefox | ☐ | Testuj `mailto:` link |
| Edge | ☐ | Testuj `mailto:` link |
| Safari (Mac) | ☐ | Jeśli dostępny |

### Mail Clients Testing (Windows)

| Mail Client | Status | Notes |
|-------------|--------|-------|
| Outlook 365 | ☐ | Sprawdź czy otwiera się |
| Outlook 2021 | ☐ | Sprawdź czy otwiera się |
| Gmail (Web) | ☐ | Sprawdź czy otwiera się |
| Windows Mail | ☐ | Jeśli zainstalowany |
| Mozilla Thunderbird | ☐ | Jeśli zainstalowany |
| Poczta Interia | ☐ | Webmail |

### Data Encoding Testing

- [ ] Polski tekst wyświetla się poprawnie (no garbled characters)
- [ ] Znaki specjalne (ąćęłńóśźż) są poprawnie kodowane w URL
- [ ] Emoji (📧) nie powoduje błędów

**Test:**
1. Sprawdź Developer Tools → Network
2. Kliknij przycisk
3. Sprawdzanie czy URL z `mailto:` ma poprawne znaki (`%20` dla spacji, itd.)

### Performance Testing

- [ ] Kliknięcie przycisku nie blokuje UI (bez zawieszenia)
- [ ] `/api/email-config` odpowiada w <100ms
- [ ] Otwarcie poczty następuje w <1 sekunda

### Security Testing

- [ ] Endpoint `/api/email-config` wymaga autentykacji (`@login_required`)
- [ ] Nie ma XSS vulnerabilities w konstruowaniu mailto linku
- [ ] Email addresses w URL są bezpieczne (nie wyciekają w logs)

**Test:**
1. Spróbuj dostęp do `/api/email-config` bez sesji
2. Powinny być logs: `[DEBUG] Incoming request... unauthorized`

---

## Production Deployment Checklist

- [ ] `.env` ma zmienną `EMAIL_RECIPIENTS` ustawioną na rzeczywiste adresy
- [ ] `config.py` prawidłowo parsuje listę odbiorców
- [ ] Serwer QNAP ma endpoint dostępny dla Windows klientów
- [ ] Dokumentacja jest dostępna dla użytkowników
- [ ] IT team poinformowany o nowej funkcji
- [ ] Backupowe odbiorcy (fallback) są skonfigurowane

---

## Post-Release Monitoring

### First Week

- [ ] Czy użytkownicy klikają nowy przycisk?
- [ ] Czy są błędy w `/api/email-config`?
- [ ] Czy jakieś problemy z mailto linkami?
- [ ] Czy użytkownicy rozumieją funkcję?

### Monthly

- [ ] Analiza użycia funkcji (ile kliknięć?)
- [ ] Feedback od użytkowników
- [ ] Czy brakuje jakichś funkcji?

---

## Rollback Plan

Jeśli coś pójdzie nie tak:

1. Wyłącz przycisk w `dashboard_global.html`:
   ```html
   <!-- <button id="btnSendEmailReport">...</button> -->
   ```

2. Wyłącz endpoint w `routes_api.py`:
   ```python
   # @api_bp.route('/api/email-config', methods=['GET'])
   # @login_required
   # def get_email_config():
   #     ...
   ```

3. Restart aplikacji:
   ```bash
   systemctl restart raport-app
   ```

---

## Notes

- Funkcja używa `mailto:` protocol (standards-based, wspierana wszędzie)
- Nie wymaga konfiguracji SMTP na serwerze
- Wszystkie testy powinne być wykonane na rzeczywistych Windows klientach
- W QNAP wymagane restart aplikacji po zmianie `.env`

---

**Tester**: [Twoja nazwa]
**Data**: [Data testowania]
**Status**: [PASS/FAIL]

