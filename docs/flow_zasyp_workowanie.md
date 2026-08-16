## Przepływ: Zasyp → Bufor → Workowanie → Palety → Magazyn

Poniżej diagram Mermaid przedstawiający główne kroki przepływu oraz odwołania do kluczowych miejsc w kodzie.

```mermaid
flowchart LR
  Z[Zasyp\n(plan_produkcji: sekcja='Zasyp')]
  B[Bufor\n(tabela `bufor`)]
  W[Workowanie\n(plan_produkcji: sekcja='Workowanie')]
  P[Palety\n(tabela `palety_workowanie`)]
  M[Magazyn\n(plan_produkcji: sekcja='Magazyn')]
  A[Auto-confirm przy migracji]
  NoteDiff[(Uwaga: różne filtry SUM w spakowano vs potwierdzeniu)]

  Z -->|1. refresh_bufor_queue(): wybiera zasypy (ORDER BY real_start) i dodaje do bufora| B
  B -->|2. start_from_queue(kolejka): ustawia Workowanie.status='w toku' i bufor.status='startowany'| W
  W -->|3. dodaj_palete(plan_id): INSERT INTO palety_workowanie status='do_przyjecia'| P
  P -->|4. potwierdz_palete(paleta_id) [role: magazynier/lider/admin]: status='przyjeta', data_potwierdzenia, aktualizuje plan_produkcji| M

  %% synchronizacje/aktualizacje tonazu
  Z -->|sync: refresh_bufor_queue() ustawia Workowanie.tonaz = Zasyp.tonaz_rzeczywisty| W
  P -->|sync: refresh_bufor_queue() / UPDATE sum palet → Workowanie.tonaz_rzeczywisty| W

  %% auto-confirm migration
  A -->|_auto_confirm_existing_palety() podczas setup_database() może ustawić status='przyjeta'| P

  %% uwaga o różnicach w obliczeniach
  B --> NoteDiff
  P --> NoteDiff

```

**Główne pliki / miejsca w kodzie**
- **Tabela palet (definicja):** [app/db.py](app/db.py#L51)
- **Tabela bufor (definicja):** [app/db.py](app/db.py#L110)
- **Funkcja odświeżająca bufor:** [app/db.py](app/db.py#L216)
- **Auto-confirm (migracja palet):** [app/db.py](app/db.py#L374)
- **Endpoint dodania palety (Workowanie):** [app/blueprints/routes_warehouse.py](app/blueprints/routes_warehouse.py#L22)
- **Endpoint potwierdzenia palety (magazyn):** [app/blueprints/routes_warehouse.py](app/blueprints/routes_warehouse.py#L182)
- **Endpoint startu z kolejki (bufor -> Workowanie):** [app/blueprints/routes_warehouse.py](app/blueprints/routes_warehouse.py#L391)
- **API zwracające zawartość bufora:** [app/blueprints/routes_warehouse.py](app/blueprints/routes_warehouse.py#L326)

**Uwaga operacyjna**
- `refresh_bufor_queue()` oblicza pole `spakowano` używając SUM z tabeli `palety_workowanie` bez jawnego filtrowania po `status`, natomiast `potwierdz_palete()` przy aktualizacji agregatów używa zapytań z filtrem `status != 'przyjeta'` — to może prowadzić do nieoczekiwanych rozbieżności w raportach/pozycjach bufora. Zwróć uwagę na ten fragment przy debugowaniu różnic.

---

Jeśli chcesz, mogę zapisać także plik SVG/PNG z diagramem lub dodać odwołania do dokładniejszych zakresów linii (np. bloki SQL). Napisz którą opcję wybierasz.
