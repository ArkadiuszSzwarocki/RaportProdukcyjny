# 📧 Konfiguracja SMTP - Wysyłanie Raportów Mailem z Załącznikami

**Data**: 2026-02-01  
**Status**: ✅ Nowa wersja - Server-side email z załącznikami

---

## 🎯 Zmiana Architektury

Zamiast `mailto:` protocol (bez załączników), teraz używamy **server-side SMTP** z Flask-Mail:

| Aspekt | Stary (`mailto:`) | Nowy (SMTP) |
|--------|------------------|-----------|
| Załączniki | ❌ Brak | ✅ XLSX, TXT, PDF |
| Automatyczne wysyłanie | ❌ Wymaga Send | ✅ Automatyczne |
| Konfiguracja | Prosta | Wymaga SMTP |
| Mail client | Konieczny | Nie potrzebny |

---

## 🔧 Konfiguracja SMTP

### Opcja 1: Gmail (Rekomendowane)

**Krok 1**: Utwórz "App Password" w Google Account

1. Przejdź do: https://myaccount.google.com/security
2. Włącz 2-Step Verification (jeśli nie włączone)
3. Utwórz App Password dla "Mail" i "Windows"
4. Skopiuj hasło (będzie 16 znaków z spacjami)

**Krok 2**: Zaktualizuj `.env`

```env
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USE_SSL=False
MAIL_USERNAME=twoj.email@gmail.com
MAIL_PASSWORD=abc123 xyz456 789def  # App Password
MAIL_DEFAULT_SENDER=Raport Produkcyjny <noreply@firma.pl>
EMAIL_RECIPIENTS=kierownik@firma.pl,dyrektor@firma.pl
```

**Krok 3**: Test

```bash
python -c "from app import app, mail; print('[OK] SMTP skonfigurowany'); print('MAIL_SERVER:', app.config['MAIL_SERVER'])"
```

---

### Opcja 2: Outlook/Office365

```env
MAIL_SERVER=smtp-mail.outlook.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USE_SSL=False
MAIL_USERNAME=twoj.email@outlook.com
MAIL_PASSWORD=Twoje-haslo-do-Outlooka
MAIL_DEFAULT_SENDER=Raport Produkcyjny <raport@firma.pl>
EMAIL_RECIPIENTS=kierownik@firma.pl,szef@firma.pl
```

---

### Opcja 3: Własny Serwer Mail (QNAP)

Jeśli QNAP ma serwer mail:

```env
MAIL_SERVER=mail.qnap-local.com  # lub 192.168.x.x
MAIL_PORT=25
MAIL_USE_TLS=False
MAIL_USE_SSL=False
MAIL_USERNAME=
MAIL_PASSWORD=
MAIL_DEFAULT_SENDER=Raport Produkcyjny <system@firma.pl>
```

---

## 📝 Zmienne `.env` - Pełny Opis

```env
# Odbiorcy domyślni
EMAIL_RECIPIENTS=email1@firma.pl,email2@firma.pl,email3@firma.pl

# SMTP Server
MAIL_SERVER=smtp.gmail.com              # Host serwera poczty
MAIL_PORT=587                           # Port (587 = TLS, 465 = SSL, 25 = no auth)
MAIL_USE_TLS=True                       # Encryption TLS
MAIL_USE_SSL=False                      # Encryption SSL (nie używaj z TLS)
MAIL_USERNAME=twoj.email@gmail.com      # Login do serwera SMTP
MAIL_PASSWORD=abc123 xyz456 789def      # Hasło lub App Password
MAIL_DEFAULT_SENDER=System <noreply@firma.pl>  # From: adres w mailu
```

---

## 🧪 Testowanie SMTP

### Test 1: Sprawdzenie Konfiguracji

```bash
python -c "
from app import app
print('MAIL_SERVER:', app.config.get('MAIL_SERVER'))
print('MAIL_PORT:', app.config.get('MAIL_PORT'))
print('MAIL_USE_TLS:', app.config.get('MAIL_USE_TLS'))
print('MAIL_USERNAME:', app.config.get('MAIL_USERNAME'))
"
```

### Test 2: Wysłanie Testowego Maila

```python
from app import app, mail
from flask_mail import Message

with app.app_context():
    msg = Message(
        subject='Test Raport',
        recipients=['twoj.email@gmail.com'],
        body='Test wiadomości z aplikacji'
    )
    mail.send(msg)
    print('[OK] Mail wysłany!')
```

### Test 3: API Endpoint

```bash
curl -X POST http://localhost:8082/api/send-report-email \
  -H "Content-Type: application/json" \
  -H "Cookie: session=YOUR_SESSION_ID" \
  -d '{
    "recipients": ["test@example.com"],
    "subject": "Test Raport",
    "body": "Treść testowej wiadomości",
    "date": "2026-02-01"
  }'
```

Spodziewana odpowiedź:

```json
{
  "status": "success",
  "message": "Raport wysłany do 1 odbiorców",
  "recipients_count": 1,
  "attachments_count": 3,
  "emails_sent": ["test@example.com"]
}
```

---

## 🐛 Troubleshooting

### Problem: "SMTPAuthenticationError: (535, b'5.7.8 Username and password not accepted')"

**Przyczyna**: Błędne credentials

**Rozwiązanie**:
- Gmail: Użyj App Password (nie zwykłe hasło)
- Outlook: Upewnij się że hasło jest prawidłowe
- Własny serwer: Sprawdź login i hasło

### Problem: "SMTPException: SMTP AUTH extension not supported by server"

**Przyczyna**: Serwer SMTP nie wspiera autentykacji

**Rozwiązanie**:
- Ustaw `MAIL_USERNAME` i `MAIL_PASSWORD` na puste ("")
- Sprawdź czy port jest prawidłowy (25 = no auth, 587 = TLS)

### Problem: "Connection timed out" / "Connection refused"

**Przyczyna**: Serwer SMTP niedostępny lub blokada firewall

**Rozwiązanie**:
- Sprawdź MAIL_SERVER i MAIL_PORT
- Sprawdzenie firewall na QNAP
- Test: `telnet smtp.gmail.com 587`

### Problem: "Raporty nie są załączane"

**Przyczyna**: Pliki raportu nie istnieją

**Rozwiązanie**:
- Sprawdzenie czy raporty były wygenerowane
- Sprawdzenie ścieżki do folderu `raporty/`
- Logowanie pokazuje: `[EMAIL-SEND] ⚠️ Brak raportów do załączenia`

---

## 📋 Wdrażanie na QNAP

### SSH do QNAP

```bash
ssh admin@qnap-ip-address
cd /path/to/raport-app
```

### Edytuj `.env`

```bash
nano .env
```

**Dodaj/zmień**:

```env
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USE_SSL=False
MAIL_USERNAME=twoj.email@gmail.com
MAIL_PASSWORD=abc123 xyz456 789def
MAIL_DEFAULT_SENDER=Raport Produkcyjny <noreply@firma.pl>
EMAIL_RECIPIENTS=kierownik@firma.pl,dyrektor@firma.pl,hr@firma.pl
```

### Restart Aplikacji

```bash
systemctl restart raport-app
# lub
systemctl stop raport-app
sleep 2
systemctl start raport-app
```

### Sprawdzenie Logów

```bash
tail -f /var/log/raport-app.log | grep EMAIL-SEND
```

Spodziewany log po kliknięciu przycisku:

```
[EMAIL-SEND] Wysyłanie raportu do 3 odbiorców
[EMAIL-SEND] ✓ Załącznik: Raport_2026-02-01.xlsx (6138 bytes)
[EMAIL-SEND] ✓ Załącznik: Do_Maila_2026-02-01.txt (139 bytes)
[EMAIL-SEND] ✓ Załącznik: Raport_2026-02-01.pdf (1930 bytes)
[EMAIL-SEND] ✅ Mail wysłany do: kierownik@firma.pl, dyrektor@firma.pl, hr@firma.pl
```

---

## 🔒 Bezpieczeństwo

### Ochrona Hasła

- ✅ Hasło w `.env` (nie w repozytorium - `.env` w `.gitignore`)
- ✅ Gmail App Password (nie zwykłe hasło)
- ✅ TLS encryption (port 587)
- ✅ Zmienne ENV nie logowane

### Sprawdzenie Bezpieczeństwa

```bash
# Sprawdzenie czy .env jest w .gitignore
cat .gitignore | grep .env

# Sprawdzenie czy hasło jest logowane
grep -r "MAIL_PASSWORD" logs/
# Powinno być puste
```

---

## 📊 Opcjonalne: Statystyki Maili

Dodaj tracking do logów:

```python
# routes_api.py
logger.info(f"[EMAIL-SEND] Wysłano {len(recipients)} maili, {len(attachments)} załączników")
```

Analiza:

```bash
ssh admin@qnap
grep "EMAIL-SEND.*Wysłano" /var/log/raport-app.log | tail -20
```

---

## 🚀 Backup: Fallback na `mailto:` (jeśli SMTP nieaktywny)

Jeśli SMTP nie działa, system automatycznie fallbackuje:

```python
# W JavaScript:
try:
  // Send via SMTP
  response = await fetch('/api/send-report-email')
} catch {
  // Fallback to mailto:
  window.location.href = 'mailto:...?subject=...&body=...'
}
```

---

## 📞 Support

**Błąd SMTP?**
- Logowanie: Check `/var/log/raport-app.log` dla `[EMAIL-SEND]` entries
- Test: `python` script testujący connection
- Gmail: Sprawdzenie App Password, 2-Step verification

**Inne pytania?**
- Email: it@firma.pl
- Phone: +48-xxx-xxx-xxxx

---

**Wersja**: 1.1.1 - SMTP z załącznikami  
**Data**: 2026-02-01

