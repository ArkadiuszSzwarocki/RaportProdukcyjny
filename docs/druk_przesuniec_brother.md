<!-- cspell:words przeglądarkowego przeglądarkowy zapisywalny -->
# Druk przesunięć A4 z monitorowaniem — Brother MFC-L2700DW

Rozwiązanie jest przygotowane bez aktywnych drukarek. W poniedziałek potrzebne są adresy IP oraz dokładne nazwy kolejek Brothera w Windows na komputerze uruchamiającym mostek. Nie zmienia konfiguracji drukarek etykiet ani dotychczasowego druku przeglądarkowego. Nie wysyła nic automatycznie po uruchomieniu.

## Przygotowanie i uruchomienie

1. Na komputerze mostka zainstaluj sterownik Brothera i sprawdź zwykły wydruk testowy Windows. Konto uruchamiające mostek musi widzieć tę kolejkę. Nazwę sprawdzisz poleceniem `Get-Printer | Select-Object Name, DriverName, PortName`.
2. Uaktualnij zależności aplikacji z `requirements.txt`, a mostka z `printer_server/requirements.txt`. Do renderowania raportów aplikacja korzysta z istniejącego Playwright/Chromium; mostek drukuje PDF przez PyMuPDF i sterownik Windows, bez skojarzeń plików i bez ShellExecute.
3. Skopiuj `printer_server/office_printers.example.json` do lokalnego pliku konfiguracyjnego. Wpisz `windows_name` dokładnie jak w Windows. Opcjonalny `ipp_uri` ma postać `ipp://ADRES_IP:631/ipp/print`; właściwą ścieżkę IPP należy potwierdzić na urządzeniu. Nie zgaduj adresów. Po sprawdzeniu ustaw `enabled: true` dla właściwej drukarki. Pozostałe wpisy pozostaw wyłączone.
4. W środowisku **aplikacji i mostka** ustaw `OFFICE_PRINTERS_FILE` na ten sam plik (lub jego zgodną kopię na drugim komputerze). Alternatywnie można użyć `OFFICE_PRINTERS_JSON` — ma pierwszeństwo przed plikiem. Mostek nadal wymaga istniejącego `PRINTER_BRIDGE_TOKEN`, a aplikacja jego poprawnego adresu `PRINTER_BRIDGE_URL`. Nie umieszczaj tokenu w przeglądarce ani w repozytorium. Po zmianie konfiguracji zrestartuj procesy.
5. Katalog `printer_server/runtime` musi być zapisywalny przez mostek. Zawiera trwałą historię SQLite; tymczasowe PDF są usuwane po przekazaniu do sterownika. Można wskazać inną trwałą ścieżkę przez `OFFICE_PRINT_JOB_DB`. Zachowuj bazę przy aktualizacji i nie uruchamiaj dwóch mostków na tej samej bazie jednocześnie.
6. Otwórz raport przesunięcia. Obok zwykłego druku pojawia się „Druk A4 z monitorowaniem”, wybór drukarki i przycisk „Wyślij i monitoruj”. Bez konfiguracji przycisk jest nieaktywny. Jedno zadanie obejmuje maksymalnie 20 dokumentów i 100 stron; wysyłamy po jednej kopii.

## Co zapisujemy

Każde żądanie ma UUID oraz użytkownika, drukarkę, dokumenty, status i numer zadania Windows zwrócony przez StartDoc. Mostek zapisuje UUID przed próbą druku. Ponowne przesłanie tego samego UUID i PDF nie uruchamia drugiego wydruku. Inny plik pod tym samym UUID jest odrzucany. Po restarcie nie ma automatycznego odtwarzania zadań do drukarki.

- „W kolejce Windows” i „Drukowanie według Windows” opisują kolejkę, nie fizyczne wyjście papieru.
- „Obsłużono w Windows — wydruk niepotwierdzony” nie jest potwierdzeniem odbioru przez urządzenie.
- „Drukarka zgłosiła zakończenie” wymaga odczytu IPP z dokładnie dopasowaną nazwą unikalnego zadania `RP-UUID`. Status `completed` z powodem `queued-in-device` nie daje takiego potwierdzenia. Ostrzeżenia, anulowanie i błędy pozostają osobnymi statusami.
- Gotowość drukarki, wzrost licznika stron ani zniknięcie zadania z kolejki nie stanowią dowodu wydrukowania danego dokumentu.
- Jeśli sterownik zmieni nazwę zadania, Brother nie zachowuje historii IPP albo blokuje odczyt, status pozostanie niepotwierdzony. Konieczny jest test sprzętowy; sama obsługa IPP przez model nie gwarantuje potwierdzenia każdego zadania.

Historia pokazuje najnowsze zadanie monitorowane dokumentu i jego autora. Kliknięcia pozostają w dotychczasowym audycie. Nowy wydruk przeglądarkowy po zadaniu monitorowanym nie dziedziczy jego potwierdzenia. Podział ostatnie 30 dni / archiwum pozostaje zachowany.

## Test w poniedziałek

Wykonaj jeden świadomy wydruk testowy z raportu i porównaj UUID/numer Windows ze statusem urządzenia oraz wydrukiem. Następnie sprawdź brak papieru lub offline oraz odzyskanie łączności. Nie powtarzaj niepewnego wydruku, dopóki nie sprawdzisz kolejki i papieru. Zamknięcie okna przeglądarki nie cofa już wysłanego zadania. Nie wysyłaliśmy próbnych zadań podczas przygotowania w domu.

Odczyt statusu nie wysyła ponownie PDF i nie uruchamia mostka. Przy utracie odpowiedzi po POST wynik jest niepewny — aplikacja odczytuje status tego samego UUID, bez automatycznego ponowienia. Po upływie kilku minut odświeżanie w danym widoku kończy się; status można ponownie odczytać po otwarciu historii.

## Źródła znaczenia statusów

- Windows StartDoc: https://learn.microsoft.com/en-us/windows/win32/api/wingdi/nf-wingdi-startdoca
- Windows JOB_INFO_1: https://learn.microsoft.com/en-us/windows/win32/printdocs/job-info-1
- IPP: https://www.rfc-editor.org/rfc/rfc8011.html (Get-Jobs i job-state-reasons).
