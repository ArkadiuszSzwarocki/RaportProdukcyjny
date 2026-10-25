<!-- cspell:words atomowo FEFO -->
# Aktualizacja magazynu po zmianach

Widok `/warehouse-v2/` nie korzysta z globalnego sprawdzania `/api/system_state` co 3,5 sekundy. Kanał SSE `/warehouse-v2/api/live/events` przesyła wersję po zatwierdzeniu zapisu w tabelach magazynowych. Dopiero nowa wersja uruchamia odczyt `/warehouse-v2/api/live/snapshot`; ta sama wersja nie powoduje zapytania. Kilka szybkich zmian jest łączonych. Lista jest rysowana ponownie tylko przy zmianie danych, z zachowaniem wyszukiwania, filtrów, sortowania, liczby załadowanych palet i przewinięcia. Otwarte okno palety pozostaje bez zmian. Aktualizowane są także zajętości i FEFO. Nie ma przycisku ręcznego odświeżania.

Kanał nie odpytuje tabel magazynowych. Między procesami przekazuje wersję przez atomowo zapisywany plik w `instance/warehouse-events` (opcjonalnie `WAREHOUSE_EVENT_DIR`). Nazwa pliku zależy od bazy. Kilka hostów wymaga współdzielonego katalogu. Zmiany SQL spoza aplikacji nie emitują zdarzeń; po takim serwisowym zapisie należy wywołać `publish(nazwa_bazy)` na serwerze aplikacji. Plik nie zawiera danych palet ani danych użytkownika.

Strumień kończy się po 55 sekundach, aby ponowne połączenie sprawdziło aktualną sesję. Komentarz podtrzymujący połączenie co 15 sekund nie wywołuje pobierania danych. Ukryta karta rozłącza kanał. Po powrocie pobierane są pominięte zmiany. Przejściowy błąd odczytu zachowuje poprzednią listę; ponawiany jest tylko nieudany odczyt.

Gunicorn domyślnie ma 64 wątki. Kanały mogą zajmować najwyżej połowę (`WAREHOUSE_SSE_MAX_CLIENTS`, domyślnie maksymalnie 32 na proces). Własne ustawienie `GUNICORN_THREADS` musi zostawić zapas na zwykłe żądania. Przy Waitress użyj także co najmniej 64 wątków albo ustaw odpowiednio mniejszy limit kanałów. Reverse proxy powinno wyłączyć buforowanie SSE i umożliwić połączenia dłuższe niż 55 sekund; endpoint ustawia `X-Accel-Buffering: no` i `Cache-Control: no-store`.

Pobieranie stanu nie wykonuje korekty blokad ani `commit`. Korekty procesów pozostają w operacjach magazynowych. Powiadomienie jest emitowane po udanym `commit`, nigdy po wycofaniu lub nieudanym zapisie. Puste zapisy oraz sesje, powiadomienia i wydruki nie powinny powodować ponownego rysowania listy.
