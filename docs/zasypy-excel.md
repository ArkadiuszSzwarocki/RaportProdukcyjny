# Zasypy AGRO według rozliczenia Excel

Przy zakończeniu zlecenia Zasyp AGRO operator wpisuje łączną faktyczną masę zasypów w kg. Pole jest wymagane; przyjmuje także jawnie wpisane 0 i maksymalnie trzy miejsca po przecinku. Wartość zapisuje się razem z zakończeniem zlecenia, a wpis audytu wskazuje autora i masę.

Dane są przechowywane osobno w `plan_produkcji_agro.zasyp_excel_kg` (DECIMAL(14,3), NULL dla starszych wpisów). Nie zastępują planu, wykonania z systemu ani odrzutów.

Workowanie korzysta z powiązania `zasyp_id`. Dla starszych zleceń bez tego powiązania można odczytać wartość tylko wtedy, gdy istnieje dokładnie jeden nieusunięty Zasyp tego produktu z tej samej daty. Przy niejednoznacznym źródle widnieje „brak wpisu”.

Wartość jest widoczna w nagłówku Workowania, przy zleceniu, w raporcie palet (podgląd i wydruk), liście zleceń do raportu, dziennym raporcie i CSV oraz w arkuszu produkcji i PDF raportu zmiany. W dziennym zestawieniu palet masa Excel jest wartością całego zlecenia, a nie pojedynczej palety; nie należy jej sumować po wierszach palet.

Migracja `scripts/migrations/ensure_zasyp_excel.py` dodaje wyłącznie pole w `biblioteka_testowa`, sprawdza faktyczną nazwę bazy i nie uzupełnia historycznych mas. Zwykła migracja aplikacji również uwzględnia to pole przy przyszłym wdrożeniu. Lokalny start nie wykonuje migracji automatycznie.

Rejestry przestojów AGRO i PSD znajdują się w menu „Awarie i usterki”. Zgłaszanie przestoju pozostaje dostępne na Workowaniu. Dzwonek przypomnień o czyszczeniu jest ukryty na Workowaniu.
