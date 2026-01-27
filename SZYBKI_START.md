# 🚀 Szybki Start - Biblioteka

## ⚡ Uruchomienie w 5 minut

### Krok 1: Przygotuj bazę danych

```sql
-- Zaloguj się do MySQL
mysql -u root -p

-- Utwórz bazę i użytkownika
CREATE DATABASE biblioteka CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'biblioteka'@'localhost' IDENTIFIED BY 'Filipinka2025';
GRANT ALL PRIVILEGES ON biblioteka.* TO 'biblioteka'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

### Krok 2: Zainstaluj zależności

**Sposób automatyczny (Windows):**

```cmd
setup.bat
```

**Sposób ręczny:**

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### Krok 3: Uruchom aplikację

```bash
python app.py
```

### Krok 4: Otwórz przeglądarkę

Przejdź do: **http://localhost:5000**

### Krok 5: Zaloguj się

**Admin:**
- Login: `admin`
- Hasło: `masterkey`

**Lider:**
- Login: `lider`
- Hasło: `admin123`

**Planista:**
- Login: `planista`
- Hasło: `plan123`

**Pracownik:**
- Login: `pracownik`
- Hasło: `user123`

---

## 🎯 Pierwsze kroki w systemie

### Jako Admin

1. Zaloguj się jako `admin`
2. Przejdź do **Panel Admina** (przycisk w górnym pasku)
3. Dodaj pracowników:
   - Imię i Nazwisko: np. "Jan Kowalski"
   - Kliknij **DODAJ PRACOWNIKA**
4. Zmień domyślne hasła kont

### Jako Planista

1. Zaloguj się jako `planista`
2. Wybierz sekcję **ZASYP**
3. W sekcji "PLAN PRODUKCJI" wypełnij formularz:
   - Data: wybierz dzisiejszą datę
   - Produkt: np. "Nawóz NPK 15-15-15"
   - Tony: np. 25
4. Kliknij **DODAJ PLAN**

### Jako Lider

1. Zaloguj się jako `lider`
2. Dodaj pracowników do obsady:
   - W sekcji "Obsada" wybierz pracownika z listy
   - Kliknij **DODAJ**
3. Rozpocznij zlecenie:
   - Kliknij **▶ START** przy zleceniu
4. Po zakończeniu:
   - Kliknij **■ KONIEC**
   - Wpisz rzeczywisty tonaż
5. Zgłoś problem (jeśli wystąpił):
   - Wybierz kategorię (Awaria/Postój/itp.)
   - Wpisz godzinę
   - Opisz problem (min. 150 znaków)
6. Zamknij zmianę:
   - Na dole strony w panelu lidera
   - Wpisz uwagi
   - Kliknij **ZATWIERDŹ I ZAMKNIJ ZMIANĘ**

### Jako Pracownik

1. Zaloguj się jako `pracownik`
2. Przeglądaj plan produkcji
3. Zgłaszaj problemy
4. Edytuj swoje zgłoszenia

---

## 📊 Główne funkcje

### Dashboard Produkcji
- **Zakładki**: Zasyp, Workowanie, Magazyn
- **Plan produkcji**: Lista zleceń z tonażem i statusem
- **Obsada**: Pracownicy na zmianie
- **Problemy**: Zgłoszenia awarii i przestojów

### Eksport do Excel
- Kliknij przycisk **📥 Excel** w nagłówku
- Pobierze się raport z 3 arkuszami:
  - Produkcja
  - Awarie
  - HR

### Raporty Okresowe
- Dostępne dla: Admin, Lider, Planista
- Statystyki miesięczne i roczne
- Wykresy trendów
- Analiza awarii

### Dashboard Zarządu
- Przycisk **📊 WYNIKI** w górnym pasku
- KPI produkcyjne
- Wykresy wydajności
- Statystyki pracowników

---

## 🔧 Rozwiązywanie problemów

### Nie mogę się połączyć z bazą

```
Błąd: mysql.connector.errors.ProgrammingError
```

**Rozwiązanie:**
1. Sprawdź czy MySQL jest uruchomiony
2. Zweryfikuj dane w `app.py` (linie 11-18)
3. Upewnij się, że baza `biblioteka` istnieje

### Błąd importu pandas

```
ModuleNotFoundError: No module named 'pandas'
```

**Rozwiązanie:**
```bash
pip install pandas openpyxl
```

### Nie można zapisać tonażu
**Możliwe przyczyny:**
- Brak uprawnień (tylko Planista, Lider, Admin)
- Zlecenie nie jest zakończone

### Nie mogę zgłosić problemu
**Możliwe przyczyny:**
- Opis za krótki (minimum 150 znaków)
- Próba zgłoszenia po godzinie 15:00

---

## 📚 Dodatkowe zasoby

- **README.md** - Pełna dokumentacja
- **KONFIGURACJA.md** - Szczegółowa konfiguracja
- **app.py** - Kod źródłowy aplikacji

---

## ⚠️ Ważne uwagi bezpieczeństwa

1. **Zmień domyślne hasła** po pierwszym uruchomieniu
2. **Zmień `app.secret_key`** w `app.py` (linia 8)
3. **Użyj HTTPS** w środowisku produkcyjnym
4. **Regularnie twórz kopie zapasowe** bazy danych
5. **Wyłącz tryb debug** w produkcji (`debug=False`)

---

## 💡 Porady

- Używaj nawigacji po datach do przeglądania historii
- Niezakończone zlecenia automatycznie przenoszą się na następny dzień
- Panel lidera jest dostępny tylko dla roli "Lider"
- Excel można eksportować z dowolnego dnia historycznego

---

**Wszystko działa?** Świetnie! Miłej pracy z systemem Biblioteka! 🎉
