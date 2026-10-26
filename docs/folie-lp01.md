# Rolki folii na LP01 i w Workowaniu AGRO

Skan SSCC wskazuje paletę źródłową. Operator zawsze wpisuje ilość pobieranej rolki i wybiera niezakończone zlecenie Workowania. Dostępny jest tryb używanej rolki (wyłącznie w toku, bez drugiej używanej) lub przygotowanej do wymiany. Pobranie i przypisanie są jedną transakcją.

Każde pobranie ma osobny rekord opakowania oraz link do zlecenia. Do zlecenia można przypisać najwyżej dwie niezamknięte rolki. Nie sumujemy kolejnych pobrań. Źródłowy SSCC, ID palety i identyfikator żądania są zapisane jako JSON w komentarzu ruchu POBRANIE_NA_MASZYNE. Historia WSADZENIE zapisuje operatora i czas.

Nie jest wymagana zmiana schematu: istniejące NULL w licznik_start oznacza przygotowaną rolkę, która nie ma jeszcze początku pomiaru zużycia. Licznik 0 jest prawidłowym początkiem używanej rolki. Starsze linki z NULL są prezentowane jako przygotowane; operator może je jawnie założyć.

Założenie przygotowanej rolki wymaga zlecenia w toku. Przy wymianie operator wpisuje pozostałość na bieżącej rolce. Zamknięcie pierwszej oraz aktywacja drugiej są atomowe. Etykiety pozostałości wysyłane są po commit. Wymiana nie pobiera ponownie folii z palety. Przy zamknięciu zlecenia niewykorzystana przygotowana rolka jest zwalniana z pełną ilością i zerowym zużyciem, pozostając do zwrotu na LP01/Maszyna.

Korekta i cofnięcie starszego rozliczenia nie mogą modyfikować osobnych nowych pobrań. Nieużywaną rolkę można zwolnić i pobrać ponownie. Z poziomu LP01 nie można archiwizować ani zwracać rolki, zanim nie zostanie zwolniona lub rozliczona w zleceniu.
