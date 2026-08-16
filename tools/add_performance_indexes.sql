-- ========================================================================
-- Skrypt dodający indeksy dla optymalizacji wydajności dashboardu
-- ========================================================================
-- Problem: Wolne ładowanie przy przesuwaniu dat (strzałki) na workowaniu
-- Rozwiązanie: Indeksy na najczęściej używanych kombinacjach kolumn
-- ========================================================================

-- Indeksy dla plan_produkcji (PSD)
CREATE INDEX IF NOT EXISTS idx_plan_data_status_deleted 
ON plan_produkcji (data_planu, status, is_deleted);

CREATE INDEX IF NOT EXISTS idx_plan_sekcja_data 
ON plan_produkcji (sekcja, data_planu, status);

-- Indeksy dla plan_produkcji_agro (AGRO)
CREATE INDEX IF NOT EXISTS idx_plan_agro_data_status_deleted 
ON plan_produkcji_agro (data_planu, status, is_deleted);

CREATE INDEX IF NOT EXISTS idx_plan_agro_sekcja_data 
ON plan_produkcji_agro (sekcja, data_planu, status);

-- Indeksy dla bufor
CREATE INDEX IF NOT EXISTS idx_bufor_data_status 
ON bufor (data_planu, status, linia);

CREATE INDEX IF NOT EXISTS idx_bufor_agro_data_status 
ON bufor_agro (data_planu, status);

-- ========================================================================
-- Indeksy dla tabel pomocniczych AGRO (workowanie, rozliczenia, magazyn)
-- ========================================================================

-- Palety AGRO - szybkie liczenie palet dla zlecenia
CREATE INDEX IF NOT EXISTS idx_palety_agro_plan_id 
ON palety_agro (plan_id);

-- Historia rozliczeń workowania AGRO
CREATE INDEX IF NOT EXISTS idx_agro_work_rozl_plan 
ON agro_workowanie_rozliczenie (plan_id, created_at);

-- Magazyn opakowań - filtrowanie po linii
CREATE INDEX IF NOT EXISTS idx_maga_opak_linia 
ON magazyn_opakowania (linia);

-- Dziennik zmiany - wpisy dla danej daty i sekcji
CREATE INDEX IF NOT EXISTS idx_dziennik_data_linia 
ON dziennik_zmiany (data_wpisu, sekcja);

-- Szarże AGRO - pobieranie dla planu
CREATE INDEX IF NOT EXISTS idx_szarze_agro_plan 
ON szarze_agro (plan_id, data_dodania);

-- Dosypki AGRO - pobieranie dla planu i szarży
CREATE INDEX IF NOT EXISTS idx_dosypki_agro_plan 
ON dosypki_agro (plan_id, szarza_id);

-- MIX rozliczenie - zużycie w planie
CREATE INDEX IF NOT EXISTS idx_agro_mix_zuzyte 
ON agro_mix_rozliczenie (zuzyte_w_id);

-- ========================================================================
-- Weryfikacja utworzonych indeksów
-- ========================================================================
SELECT 
    'plan_produkcji' AS tabela,
    INDEX_NAME,
    COLUMN_NAME,
    SEQ_IN_INDEX,
    CARDINALITY
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'plan_produkcji'
  AND INDEX_NAME IN ('idx_plan_data_status_deleted', 'idx_plan_sekcja_data')
ORDER BY INDEX_NAME, SEQ_IN_INDEX;

SELECT 
    'plan_produkcji_agro' AS tabela,
    INDEX_NAME,
    COLUMN_NAME,
    SEQ_IN_INDEX,
    CARDINALITY
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'plan_produkcji_agro'
  AND INDEX_NAME IN ('idx_plan_agro_data_status_deleted', 'idx_plan_agro_sekcja_data')
ORDER BY INDEX_NAME, SEQ_IN_INDEX;

SELECT 
    'bufor/bufor_agro' AS tabela,
    TABLE_NAME,
    INDEX_NAME,
    COLUMN_NAME,
    SEQ_IN_INDEX
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('bufor', 'bufor_agro')
  AND INDEX_NAME IN ('idx_bufor_data_status', 'idx_bufor_agro_data_status')
ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX;

SELECT 
    'AGRO tables' AS grupa,
    TABLE_NAME,
    INDEX_NAME,
    COLUMN_NAME
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND (
    (TABLE_NAME = 'palety_agro' AND INDEX_NAME = 'idx_palety_agro_plan_id')
    OR (TABLE_NAME = 'agro_workowanie_rozliczenie' AND INDEX_NAME = 'idx_agro_work_rozl_plan')
    OR (TABLE_NAME = 'magazyn_opakowania' AND INDEX_NAME = 'idx_maga_opak_linia')
    OR (TABLE_NAME = 'dziennik_zmiany' AND INDEX_NAME = 'idx_dziennik_data_linia')
    OR (TABLE_NAME = 'szarze_agro' AND INDEX_NAME = 'idx_szarze_agro_plan')
    OR (TABLE_NAME = 'dosypki_agro' AND INDEX_NAME = 'idx_dosypki_agro_plan')
    OR (TABLE_NAME = 'agro_mix_rozliczenie' AND INDEX_NAME = 'idx_agro_mix_zuzyte')
  )
ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX;

-- ========================================================================
-- Analiza użycia indeksów (opcjonalne - do testowania)
-- ========================================================================
-- Możesz uruchomić EXPLAIN na wolnym zapytaniu, aby sprawdzić czy używa indeksów:
-- 
-- EXPLAIN SELECT * FROM plan_produkcji 
-- WHERE DATE(data_planu) = '2026-06-02' AND status = 'w toku' AND is_deleted = 0;
--
-- W kolumnie 'key' powinien pojawić się idx_plan_data_status_deleted
-- ========================================================================
