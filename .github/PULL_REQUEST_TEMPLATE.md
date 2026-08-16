# Żądanie Zmian

## Co zmienia ten PR

- Dodaje responsywne menu boczne (hamburger + warstwa) i skrypt obsługi
- Centralizuje style w `static/style.css` i dodaje pomocnicze klasy
- Dodaje `static/favicon.ico` aby wyeliminować 404 na favicon
- Poprawki dostępności: `aria-label`, widoczne `label` tam gdzie potrzebne
- Poprawki struktury HTML (listy bez tekstowych węzłów) i drobne poprawki w szablonach
- Dodaje `tools/spelling_whitelist.txt` z terminologią projektu (zmniejsza ostrzeżenia sprawdzania pisowni)

## Jak przetestować

1. Uruchom aplikację lokalnie (`run.bat` na Windows) i otwórz <http://localhost:5000>
2. Przetestuj na mobilnym rozdzielczości: menu boczne powinno być ukryte i otwierać się po kliknięciu hamburgera jako panel z warstwą.
3. Sprawdź, czy nie ma 404 dla `/static/favicon.ico`.
4. Przejrzyj kilka szablonów admin/planista/jakość — powinny mieć etykiety i `aria-label` tam, gdzie brakowało.

## Lista Kontrolna

- [ ] Visual QA na małych ekranach (mobile)
- [ ] Przegląd etykiet i tekstów domenowych (język biznesowy)
- [ ] Przegląd Kodu

Opis zmian i lista plików: proszę sprawdzić szczegóły w Zatwierdzeniach/Pliki zmienione.
