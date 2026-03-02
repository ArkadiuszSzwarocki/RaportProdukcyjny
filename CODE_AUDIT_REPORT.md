# 📋 Code Audit Report - RaportProdukcyjny

**Data:** 2026-03-02  
**Status:** Serwer uruchomiony ✅ Kod do optymalizacji ⚠️

---

## 🔴 KRYTYCZNE PROBLEMY

### 1. **Niezamknięte Koneksje DB** 
**Plik:** `app/blueprints/routes_production.py`  
**Linie:** 23-110, 145-180, 220-250  

**Problem:** Brak `finally` bloku powoduje wycieki koneksji gdy rzuci exception
```python
# ❌ BŁĘDY PRZYKŁAD:
conn = get_db_connection()
cursor = conn.cursor()
cursor.execute("SELECT ...")  # jeśli exception tu - conn nie będzie zamknięta!
conn.close()  # NIGDY się nie uruchomi
```

**Rozwiązanie:** Dodai try/except/finally
```python
# ✅ PRAWIDŁOWE:
conn = get_db_connection()
try:
    cursor = conn.cursor()
    cursor.execute("SELECT ...")
    conn.commit()
except Exception as e:
    conn.rollback()
    log_error(e)
finally:
    conn.close()
```

**Gdzie naprawić:**
- [ ] `start_zlecenie()` - linia 23
- [ ] `koniec_zlecenie()` - linia 145 
- [ ] `zapisz_wyjasnienie()` - linia 220
- [ ] `szarza_page()` - linia 250
- [ ] `koniec_zlecenie_page()` - linia 195

---

### 2. **Błędy Logowania - `except: pass`**
**Zasięg:** Cały projekt (20+ instancji)  
**Obrazek:**
```python
# ❌ ZŁAMANIEZBERA:
except Exception:
    pass  # Co się stało?? Wiemy?? NIE!
```

**Gdzie:**
- `routes_production.py`: linia 77, 89, 128, 194, 217, ...
- `routes_panels.py`: linia 226, 343, ...
- `routes_planning.py`: linia 155, 196, 248, ...

**Napraw:**
```python
# ✅ PRAWIDŁOWE:
except Exception as e:
    current_app.logger.error(f"Błąd w {func_name}: {e}", exc_info=True)
    # lub
    flash(f"❌ Błąd: {str(e)}", 'danger')
```

---

### 3. **Logika Błędu w `koniec_zlecenie`**
**Plik:** `routes_production.py`, linia 145  
**Problem:** Funkcja może nie logować błędu gdy rollback/commit nie powiedzie się

**Rozwiązanie:** 
```python
try:
    cursor.execute(SQL, params)
    conn.commit()
except Exception as e:
    current_app.logger.error(f"Failed to complete order {id}: {e}", exc_info=True)
    conn.rollback()
    raise  # lub flash error
finally:
    conn.close()
```

---

## 🟡 ŚREDNIOZWAŻNE PROBLEMY

### 4. **Brakuje Validacji w `dodaj_obecnosc`**
**Plik:** `routes_schedule.py`, linia 15  
**Problem:** Nie sprawdza czy pracownik istnieje przed wstawieniem

```python
# NAPRAW:
if not pracownik_id:
    flash('Pracownik jest wymagany', 'error')
    return redirect(...)

# Sprawdź czy pracownik istnieje:
cursor.execute("SELECT id FROM pracownicy WHERE id=%s", (pracownik_id,))
if not cursor.fetchone():
    flash('Pracownik nie znaleziony', 'error')
    return redirect(...)
```

---

### 5. **Duplikaty - Refresh Bufor Queue**
**Zasięg:** Powtarza się w 3+ miejscach  
**Rozwiązanie:** Wydzielić do helpera

```python
# app/services/buffer_service.py
def auto_refresh_buffer_after_closing():
    try:
        from app.db import refresh_bufor_queue
        refresh_bufor_queue(conn)
    except Exception as e:
        logger.warning(f"Buffer refresh failed: {e}")
```

---

## 🟢 NISKIE PRIORYTETY

### 6. **Magiczne Stringi (Role)**
**Zastąp:**
```python
# ❌ 
if role in ('planista', 'admin', 'lider'):
    
# ✅ 
from app.constants import ROLES
if role in [ROLES.PLANNER, ROLES.ADMIN, ROLES.LEADER]:
```

---

## 📈 METRYKI

| Metrika | Wartość |
|---------|---------|
| Funkcji bez finally | ~15 |
| Błędów logowania (pass) | ~25 |
| Duplikatów kodu | ~8 |
| SQLi Risk | Low (parametryzacja OK) |
| Coverage | ~40% (szacunkowo) |

---

## ✅ REKOMENDACJE

1. **Natychmiastowe (Today):**
   - Dodaj try/except/finally do `routes_production.py`
   - Zamień `except: pass` na proper logging

2. **Krótkoterminowe (Week):**
   - Wydziel helpery dla common patterns
   - Dodaj walidację upopowszechnie

3. **Długoterminowe (Next Sprint):**
   - Refactor magicznych stringów
   - Dodaj integration testy
   - Audit security (zaloguj wszystkie auth failures)

---

## 🚀 NEXT STEPS

1. ✅ **Serwer running** - można testować live
2. ⏳ **Naprawić koneksje DB** - największe ryzyko
3. 🔧 **Dodać proper logging** - ułatwi debugging
4. 🧪 **Uruchomić testy** - catch regressions

---

*Raport wygenerowany automatycznie przez AI Code Audit*
