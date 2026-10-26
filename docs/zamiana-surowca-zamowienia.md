# Anulowanie i zamiana pozycji zamówienia

W Magazyny → Zamówienia przy niezrealizowanej lub częściowo zrealizowanej pozycji jest przycisk „Anuluj / zamień”.

- Rezygnacja anuluje tylko pozostałą ilość.
- Zamiana wymaga wyboru innego surowca ze słownika i podania ilości. Powstaje osobne, niezrealizowane zamówienie.
- Powód jest wymagany. System zapisuje konto zatwierdzającego, datę i wzajemne powiązanie pozycji.
- Dotychczasowe przypisania palet do transferów pozostają. Zmiana nie cofa transportu, nie koryguje stanów magazynowych i nie zmienia receptur.
- Kolejne skany nie realizują anulowanej pozycji. Pozostałe pozycje tego samego zamówienia mogą być nadal realizowane.
- Zamówień zawierających historię zamiany lub anulowania nie można trwale usuwać.

Uprawnienia są zgodne z dotychczasową polityką zarządzania zamówieniami. Dane decyzji są przechowywane w istniejącym polu JSON `items`, a status całego zamówienia może mieć wartość `ANULOWANE`. Nie jest potrzebna migracja schematu. Nowe zamówienie i decyzja o starym są zapisywane we wspólnej transakcji z blokadą rekordu źródłowego.
