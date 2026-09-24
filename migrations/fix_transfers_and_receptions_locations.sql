-- Migration SQL to resolve pallets stuck in OCZEKUJĄCE from transfer 22092026071643 and delivery 344a97a0

-- 1. Close transfer 22092026071643 and mark as COMPLETED
UPDATE magazyn_dostawy 
SET status = 'COMPLETED' 
WHERE (order_ref LIKE '%22092026071643%' OR id LIKE '%22092026071643%')
  AND status != 'COMPLETED';

-- 2. Move raw materials from transfer 22092026071643 out of OCZEKUJĄCE to real target locations (fallback MS01)
UPDATE magazyn_surowce 
SET lokalizacja = 'MS01', is_blocked = 0, is_loaded = 0 
WHERE (lokalizacja IN ('OCZEKUJĄCE', 'OCZEKUJACE', 'RAMPA', 'BRAK', '') OR is_blocked = 1)
  AND nr_palety IN (
    SELECT JSON_UNQUOTE(JSON_EXTRACT(j.item, '$.nr_palety'))
    FROM magazyn_dostawy d,
    JSON_TABLE(d.items, '$[*]' COLUMNS (nr_palety VARCHAR(64) PATH '$.nr_palety')) j
    WHERE d.order_ref LIKE '%22092026071643%' OR d.id LIKE '%22092026071643%'
);

-- 3. Move packaging materials from transfer 22092026071643 out of OCZEKUJĄCE (fallback MOP01)
UPDATE magazyn_opakowania 
SET lokalizacja = 'MOP01', is_blocked = 0, is_loaded = 0 
WHERE (lokalizacja IN ('OCZEKUJĄCE', 'OCZEKUJACE', 'RAMPA', 'BRAK', '') OR is_blocked = 1)
  AND nr_palety IN (
    SELECT JSON_UNQUOTE(JSON_EXTRACT(j.item, '$.nr_palety'))
    FROM magazyn_dostawy d,
    JSON_TABLE(d.items, '$[*]' COLUMNS (nr_palety VARCHAR(64) PATH '$.nr_palety')) j
    WHERE d.order_ref LIKE '%22092026071643%' OR d.id LIKE '%22092026071643%'
);

-- 4. Close delivery 344a97a0 and ensure status is COMPLETED
UPDATE magazyn_dostawy 
SET status = 'COMPLETED' 
WHERE id LIKE '344a97a0%' AND status != 'COMPLETED';

-- 5. Move raw materials from delivery 344a97a0 out of OCZEKUJĄCE to real target location (MS01)
UPDATE magazyn_surowce 
SET lokalizacja = 'MS01', is_blocked = 0, is_loaded = 0 
WHERE (lokalizacja IN ('OCZEKUJĄCE', 'OCZEKUJACE', 'RAMPA', 'BRAK', '') OR is_blocked = 1)
  AND nr_palety IN (
    SELECT JSON_UNQUOTE(JSON_EXTRACT(j.item, '$.nr_palety'))
    FROM magazyn_dostawy d,
    JSON_TABLE(d.items, '$[*]' COLUMNS (nr_palety VARCHAR(64) PATH '$.nr_palety')) j
    WHERE d.id LIKE '344a97a0%'
);

-- 6. Move packaging materials from delivery 344a97a0 out of OCZEKUJĄCE to real target location (MOP01)
UPDATE magazyn_opakowania 
SET lokalizacja = 'MOP01', is_blocked = 0, is_loaded = 0 
WHERE (lokalizacja IN ('OCZEKUJĄCE', 'OCZEKUJACE', 'RAMPA', 'BRAK', '') OR is_blocked = 1)
  AND nr_palety IN (
    SELECT JSON_UNQUOTE(JSON_EXTRACT(j.item, '$.nr_palety'))
    FROM magazyn_dostawy d,
    JSON_TABLE(d.items, '$[*]' COLUMNS (nr_palety VARCHAR(64) PATH '$.nr_palety')) j
    WHERE d.id LIKE '344a97a0%'
);
