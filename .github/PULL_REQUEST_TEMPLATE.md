## Co zmienia ten PR

- Dodaje responsywne menu boczne (hamburger + overlay) i skrypt obsługi
- Centralizuje style w `static/style.css` i dodaje utility classes
- Dodaje `static/favicon.ico` aby wyeliminować 404 na favicon
- Poprawki dostępności: `aria-label`, widoczne `label` tam gdzie potrzebne
- Poprawki struktury HTML (lista <ul> bez tekstowych nodów) i drobne poprawki w szablonach
- Dodaje `tools/spelling_whitelist.txt` z terminologią projektu (zmniejsza ostrzeżenia spellcheck)

## Jak przetestować

1. Uruchom aplikację lokalnie (`run.bat` na Windows) i otwórz <http://localhost:5000>
2. Przetestuj na mobilnym viewport: menu boczne powinno być ukryte i otwierać się po kliknięciu hamburgera jako panel z overlay.
3. Sprawdź, czy nie ma 404 dla `/static/favicon.ico`.
4. Przejrzyj kilka szablonów admin/planista/jakość — powinny mieć etykiety i `aria-label` tam, gdzie brakowało.

## Checklist

- [ ] Visual QA na małych ekranach (mobile)
- [ ] Przegląd etykiet i tekstów domenowych (język biznesowy)
- [ ] Code review

Opis zmian i lista plików: proszę sprawdzić szczegóły w Commits/Files changed.
