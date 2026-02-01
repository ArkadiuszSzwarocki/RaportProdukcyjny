# Konfiguracja Email dla Raportów Produkcyjnych

## Przegląd

Funkcjonalność "Wyślij raport mailem" 📧 umożliwia otworzenie domyślnego klienta poczty Windows z przygotowanym mailem zawierającym:
- **Temat**: "Raport produkcyjny z dnia [DATA]"
- **Adresaci**: Konfigurowalni odbiorcy
- **Treść**: Wstępnie sformatowana informacja o raporcie

## Konfiguracja Odbiorców

### Metoda 1: Zmienne Środowiskowe (Zalecane)

Ustawić zmienną `EMAIL_RECIPIENTS` w pliku `.env`:

```
EMAIL_RECIPIENTS=lider@example.com,szef@example.com,biuro@example.com
```

Każdy adres e-mail oddzielony przecinkiem.

### Metoda 2: Kod (Fallback)

Jeśli zmienna ENV nie jest ustawiona, aplikacja używa domyślnych odbiorców z [config.py](config.py):

```python
EMAIL_RECIPIENTS = os.getenv('EMAIL_RECIPIENTS', 'lider@example.com,szef@example.com,biuro@example.com').split(',')
```

## Architektura Rozwiązania

### Backend

**Plik**: [routes_api.py](routes_api.py)

Endpoint `/api/email-config` (GET):

```python
@api_bp.route('/api/email-config', methods=['GET'])
@login_required
def get_email_config():
    """Zwraca konfigurację odbiorców raportów email"""
    from config import EMAIL_RECIPIENTS
    return jsonify({
        "recipients": EMAIL_RECIPIENTS,
        "subject_template": "Raport produkcyjny z dnia {date}",
        "configured": len(EMAIL_RECIPIENTS) > 0,
        "count": len(EMAIL_RECIPIENTS)
    })
```

### Frontend

**Plik**: [templates/dashboard_global.html](templates/dashboard_global.html)

1. **Przycisk**: `<button id="btnSendEmailReport">📧 Wyślij raport mailem</button>`
2. **Event Handler**: Pobiera konfigurację z API i konstruuje `mailto:` link
3. **Otwiera**: Domyślny klient poczty Windows (Outlook, Gmail, itp.)

### Stylowanie

**Plik**: [static/css/dashboard_global.css](static/css/dashboard_global.css)

```css
.btn-send-email {
  background-color: #17a2b8 !important;
  color: white;
  border: 1px solid #138496;
  border-radius: 4px;
  transition: all 0.3s ease;
}

.btn-send-email:hover {
  background-color: #138496 !important;
  box-shadow: 0 2px 8px rgba(23, 162, 184, 0.4);
}
```

## Jak to Działa

### Flow Użytkownika

1. **Użytkownik klika przycisk** 📧 "Wyślij raport mailem" na dashboard
2. **JavaScript:**
   - Pobiera z API listę odbiorców
   - Konstruuje `mailto:` link
   - Otwiera domyślny klient poczty
3. **Poczta Windows** otwiera się z:
   - **To**: `osoba1@example.com,osoba2@example.com,osoba3@example.com`
   - **Subject**: `Raport produkcyjny z dnia 01.02.2026`
   - **Body**: Sformatowana wiadomość z danymi raportu
4. **Użytkownik** dodaje załączniki (jeśli potrzeba) i wysyła

### Technologia: `mailto:` Protocol

Rozwiązanie używa standardowego `mailto:` URL scheme zamiast SMTP na serwerze:

**Zalety:**
- ✅ Działa niezawodnie na Windows (każdy ma skonfigurowaną pocztę)
- ✅ Nie wymaga konfiguracji SMTP na serwerze
- ✅ Pracuje z dowolnym klientem poczty (Outlook, Gmail, Thunderbird, itp.)
- ✅ Zgodne z QNAP + Windows architekturą
- ✅ Brak potrzeby certyfikatów SSL/TLS na serwerze

**Ograniczenia:**
- ❌ Nie może automatycznie wysyłać (wymaga ludzkiego potwierdzenia)
- ❌ Całkowite rozmiary URL są ograniczone (~2000 znaki)
- ❌ Załączniki muszą być ręcznie dodane przez użytkownika

## Konfiguracja na Produkcji (QNAP)

1. **SSH do QNAP:**
   ```bash
   ssh admin@qnap-ip-address
   ```

2. **Edytuj `.env`:**
   ```bash
   nano /path/to/app/.env
   ```

3. **Dodaj/Zmień zmienną:**
   ```
   EMAIL_RECIPIENTS=kierownik@firma.pl,dyrektor@firma.pl,archiwum@firma.pl
   ```

4. **Restart aplikacji:**
   ```bash
   systemctl restart raport-app
   ```

## Testowanie

### Test API

```bash
curl -X GET http://localhost:8082/api/email-config \
  -H "Cookie: session=YOUR_SESSION_ID"
```

Spodziewana odpowiedź:

```json
{
  "recipients": ["lider@example.com", "szef@example.com", "biuro@example.com"],
  "subject_template": "Raport produkcyjny z dnia {date}",
  "configured": true,
  "count": 3
}
```

### Test Frontend

1. Zaloguj się do aplikacji
2. Przejdź do dashboard (http://localhost:8082/dashboard)
3. Kliknij przycisk "📧 Wyślij raport mailem"
4. Powinna otworzyć się poczta z przygotowanym mailem

## Opcjonalne: Server-Side Email (Backup)

Jeśli w przyszłości będzie potrzebne automatyczne wysyłanie, można dodać endpoint SMTP:

```python
from flask_mail import Mail, Message

# config.py
MAIL_SERVER = os.getenv('MAIL_SERVER')
MAIL_PORT = int(os.getenv('MAIL_PORT', 587))
MAIL_USERNAME = os.getenv('MAIL_USERNAME')
MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')

# routes_api.py
@api_bp.route('/api/send-report-email', methods=['POST'])
@login_required
def send_report_email():
    # Wysyła raport mailem przez SMTP
    pass
```

## Znane Problemy i Rozwiązania

### Problem: Przycisk nie otwiera poczty
**Rozwiązanie**: Sprawdź czy:
- Użytkownik jest zalogowany (konieczne dla `@login_required`)
- Poczta jest skonfigurowana w systemie Windows
- Konsola przeglądarki pokazuje błędy

### Problem: Zbyt dużo odbiorców
**Rozwiązanie**: Limit `mailto:` linku to ~2000 znaków. Jeśli masz więcej niż 10 odbiorców, rozważ:
- Grupy dystrybucyjne (np. `zespol-produkcja@firma.pl`)
- Server-side SMTP (patrz wyżej)

### Problem: Tekst raportu nieczytelny w mailu
**Rozwiązanie**: Edytuj treść body w [dashboard_global.html](templates/dashboard_global.html) funkcja `sendEmailReport()`

## Pliki Związane

- [config.py](config.py) - Konfiguracja EMAIL_RECIPIENTS
- [routes_api.py](routes_api.py) - Endpoint /api/email-config
- [templates/dashboard_global.html](templates/dashboard_global.html) - Przycisk i JavaScript
- [static/css/dashboard_global.css](static/css/dashboard_global.css) - Styling przycisku

## Historia Zmian

**2026-02-01**: Dodana funkcjonalność email z `mailto:` protocol
- ✅ Przycisk "Wyślij raport mailem" na dashboard
- ✅ Konfiguracja odbiorców z ENV
- ✅ Endpoint API `/api/email-config`
- ✅ CSS styling dla przycisku
- ✅ JavaScript event handler

