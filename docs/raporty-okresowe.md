# Raporty okresowe

Adres `/raporty_okresowe` pozostaje bez zmian. Filtry: hala AGRO / PSD / obie, rok, miesiąc i produkt. Kliknięcie miesiąca w wykresie lub w kafelku przechodzi do szczegółów z zachowaniem filtrów i wybranego etapu.

Zasyp i Workowanie są rozdzielone; ich mas nie sumujemy jako całej produkcji. Raport domyślnie obejmuje zlecenia w toku, zawieszone i zakończone według dat opisanych niżej (można wybrać tylko zakończone), z pominięciem usuniętych zleceń i zleceń jakościowych. Wykonanie Zasypu pochodzi z historii szarż, potwierdzonych dosypek i wrzuconych wiaderek, a Workowania z historii palet; przy braku tej historii stosujemy zapisane wykonanie zlecenia i datę planu z odpowiednim oznaczeniem. Brak pomiaru nie jest zastępowany planem; rzeczywisty pomiar 0 pozostaje zerem. Rozliczenie Excel jest dodatkową, niezależną miarą Zasypu.

Wykresy: rok, plan i wykonanie dzienne, przebieg narastający, tempo kolejnych zleceń i średnie, produkty oraz Pareto przestojów. Krzywa tempa używa czasu od `real_start` do `real_stop`, obejmującego przerwy. Średnie są ważone czasem; nie jest to wydajność netto ani ocena pracownika. Porównywalność poprawia filtr pojedynczego produktu. Przy brakujących pomiarach nie wyliczamy realizacji całego planu ani zmiany miesiąc do miesiąca. Osobne rejestry przestojów są przypisywane do odpowiednich etapów.

Dostępna jest szczegółowa tabela zleceń, wyszukiwanie, eksport CSV wybranego etapu i wydruk obu etapów. Wykresy korzystają z lokalnego Chart.js. Otwieranie raportu nie tworzy tabel, nie zapisuje do bazy, nie generuje plików i nie wysyła e-maili.

Historyczny rejestr `auto_report_history` jest dostępny w Administracja → Ustawienia systemu → E-mail i powiadomienia → Wysyłki raportów, z zachowaniem uprawnień historii poczty i dotychczasowych odnośników do PDF / Excel. Brak tej tabeli nie wywołuje jej utworzenia.


## Bieżące wykonanie

Status zlecenia jest widoczny w szczegółach i w CSV. Krzywa tempa oraz średnia kg/h korzystają wyłącznie z zakończonych zleceń; bieżące masy są uwzględniane w sumach i wykresach ilościowych. Nie są dodawane drugi raz przy zakończeniu zlecenia.

Ciche aktualizacje wykorzystują osobny kanał SSE powiadamiany po zatwierdzeniu zapisów planów i przestojów w aplikacji. Zmiany produkcyjne nie wywołują aktualizacji widoku magazynu. Przeglądarka pobiera raport po zmianie rewizji, porównuje dane i aktualizuje wykresy, wskaźniki oraz tabelę bez przeładowania strony. Zachowuje wyszukiwanie, aktywną zakładkę i przewinięcie. Po powrocie na kartę pobiera aktualny stan jednokrotnie; nie odpytuje cyklicznie raportu. Kanał dotyczy zapisów obserwowanych przez daną instancję aplikacji, nie zewnętrznych zmian SQL na innym serwerze.


## Kontynuacje Workowania i zgodność planu

Plan Workowania z jednoznacznym powiązaniem `zasyp_id` korzysta z dodatniej masy rzeczywistej tego Zasypu, zgodnie z panelem operatora. Brak takiej masy pozostawia zapisany plan Workowania; raport nie dopasowuje zleceń po samej nazwie produktu.

Wykonanie Workowania jest rozdzielane na dni według `data_dodania` palet i ich zapisanej `waga`, zgodnie z listą palet na Workowaniu. Suma miesięczna oraz roczna również korzystają z tych dat, więc kontynuacja na granicy miesięcy nie dubluje całego zlecenia. Plan pozostaje przy dacie planu zlecenia, bez sztucznego rozdzielania na dni. Podpowiedź dzienna podaje ilość z kontynuacji wcześniejszych zleceń. Zlecenia bez dostępnej historii palet zachowują wcześniejszą datę planu i są oznaczone w kompletności danych.

Tabela i CSV rozróżniają wykonanie miesiąca oraz całego zlecenia. Realizacja zlecenia i tempo brutto odnoszą się do całego zlecenia. Zasyp rozdzielamy według rzeczywistych dat szarż, dosypek i wrzuconych wiaderek.


## Dzienne wykonanie Zasypu

Dzienny Zasyp jest liczony z dat szarż, potwierdzenia nieanulowanych dosypek oraz wrzucenia wiaderek do mieszalnika. Wiaderka tylko przygotowane nie są wykonaniem. Dzięki temu poranna kontynuacja zlecenia planowanego poprzedniego dnia trafia do bieżącego dnia. Miesięczne sumy i szczegóły również korzystają z dat produkcji; nie dodajemy równocześnie zapisanej sumy zlecenia. Brak daty pojedynczego zdarzenia skutkuje użyciem daty planu i oznaczeniem niepełnej historii.
