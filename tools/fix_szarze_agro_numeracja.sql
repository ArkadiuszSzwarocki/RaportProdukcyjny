-- ============================================================
-- Naprawa numeracji szarż AGRO - brakująca szarża #6
-- ============================================================

-- KROK 1: Diagnostyka - sprawdź co mamy w bazie
-- ============================================================

-- Pokaż wszystkie szarże z dzisiejszych zleceń AGRO
SELECT 
    s.id as szarza_id,
    s.nr_szarzy,
    s.plan_id,
    s.waga,
    s.godzina,
    s.data_dodania,
    p.produkt,
    p.nazwa_zlecenia,
    p.data_planu
FROM szarze_agro s
JOIN plan_produkcji_agro p ON s.plan_id = p.id
WHERE p.data_planu >= CURDATE() - INTERVAL 7 DAY  -- ostatnie 7 dni
ORDER BY p.data_planu DESC, s.nr_szarzy ASC;

-- Sprawdź etapy w zasyp_etapy dla AGRO
SELECT 
    ze.id,
    ze.plan_id,
    ze.szarza_nr,
    ze.etap,
    ze.data_start,
    ze.data_koniec,
    p.produkt,
    p.data_planu
FROM zasyp_etapy ze
JOIN plan_produkcji_agro p ON ze.plan_id = p.id
WHERE ze.linia = 'AGRO' 
  AND p.data_planu >= CURDATE() - INTERVAL 7 DAY
ORDER BY p.data_planu DESC, ze.szarza_nr ASC, ze.etap ASC;

-- Sprawdź które szarze_nr są w etapach ale nie ma ich w szarze_agro
SELECT DISTINCT 
    ze.plan_id,
    ze.szarza_nr,
    p.produkt,
    p.data_planu,
    'BRAK W SZARZE_AGRO' as status
FROM zasyp_etapy ze
JOIN plan_produkcji_agro p ON ze.plan_id = p.id
LEFT JOIN szarze_agro s ON s.plan_id = ze.plan_id AND s.nr_szarzy = ze.szarza_nr
WHERE ze.linia = 'AGRO'
  AND p.data_planu >= CURDATE() - INTERVAL 7 DAY
  AND s.id IS NULL
ORDER BY p.data_planu DESC, ze.szarza_nr ASC;

-- ============================================================
-- KROK 2: OPCJA A - Przenumuuj szarże aby usunąć lukę
-- ============================================================
-- UWAGA: Uruchom to TYLKO jeśli chcesz przenumuować szarże 7,8,9... na 6,7,8...
-- Musisz podać konkretny plan_id!

-- Przykład: jeśli plan_id = 12345 i brakuje #6, to:
-- szarża #7 stanie się #6
-- szarża #8 stanie się #7
-- itd.

-- NAJPIERW SPRAWDŹ które szarże będą przenumuowane (BEZPIECZNE):
/*
SET @target_plan_id = 12345;  -- ZMIEŃ NA WŁAŚCIWY PLAN_ID!
SET @missing_nr = 6;           -- Brakujący numer

SELECT 
    s.id,
    s.nr_szarzy as stary_nr,
    s.nr_szarzy - 1 as nowy_nr,
    s.waga,
    s.produkt,
    'BĘDZIE PRZENUMUOWANE' as akcja
FROM szarze_agro s
WHERE s.plan_id = @target_plan_id
  AND s.nr_szarzy > @missing_nr
ORDER BY s.nr_szarzy ASC;
*/

-- POTEM uruchom UPDATE (OSTROŻNIE!):
/*
SET @target_plan_id = 12345;  -- ZMIEŃ NA WŁAŚCIWY PLAN_ID!
SET @missing_nr = 6;           -- Brakujący numer

UPDATE szarze_agro
SET nr_szarzy = nr_szarzy - 1
WHERE plan_id = @target_plan_id
  AND nr_szarzy > @missing_nr;

-- Również zaktualizuj zasyp_etapy:
UPDATE zasyp_etapy
SET szarza_nr = szarza_nr - 1
WHERE plan_id = @target_plan_id
  AND szarza_nr > @missing_nr
  AND linia = 'AGRO';
*/

-- ============================================================
-- KROK 3: OPCJA B - Dodaj brakującą szarżę #6 ręcznie
-- ============================================================
-- UWAGA: Uruchom to TYLKO jeśli chcesz dodać brakującą szarżę #6

-- NAJPIERW sprawdź parametry z istniejących szarż tego samego planu:
/*
SET @target_plan_id = 12345;  -- ZMIEŃ NA WŁAŚCIWY PLAN_ID!

SELECT 
    s.*,
    p.produkt,
    p.typ_produkcji,
    p.data_planu
FROM szarze_agro s
JOIN plan_produkcji_agro p ON s.plan_id = p.id
WHERE s.plan_id = @target_plan_id
ORDER BY s.nr_szarzy ASC;
*/

-- POTEM dodaj brakującą szarżę (DOSTOSUJ WARTOŚCI!):
/*
SET @target_plan_id = 12345;     -- ZMIEŃ NA WŁAŚCIWY PLAN_ID!
SET @nr_szarzy = 6;              -- Brakujący numer
SET @waga = 1000.0;              -- ZMIEŃ NA WŁAŚCIWĄ WAGĘ (w kg)
SET @godzina = '12:00:00';       -- ZMIEŃ NA ODPOWIEDNIĄ GODZINĘ
SET @data_dodania = NOW();       -- lub ustaw konkretną datę
SET @pracownik_id = NULL;        -- lub ID pracownika
SET @produkt = 'NAZWA PRODUKTU'; -- ZMIEŃ NA NAZWĘ PRODUKTU
SET @typ_produkcji = NULL;       -- lub typ produkcji
SET @data_planu = CURDATE();     -- lub konkretna data

INSERT INTO szarze_agro (
    plan_id,
    nr_szarzy,
    waga,
    godzina,
    data_dodania,
    pracownik_id,
    produkt,
    typ_produkcji,
    data_planu
) VALUES (
    @target_plan_id,
    @nr_szarzy,
    @waga,
    @godzina,
    @data_dodania,
    @pracownik_id,
    @produkt,
    @typ_produkcji,
    @data_planu
);

-- Zaktualizuj tonaz_rzeczywisty w planie:
UPDATE plan_produkcji_agro 
SET tonaz_rzeczywisty = (
    SELECT COALESCE(SUM(waga), 0) 
    FROM szarze_agro 
    WHERE plan_id = @target_plan_id
) + (
    SELECT COALESCE(SUM(kg), 0) 
    FROM dosypki_agro 
    WHERE plan_id = @target_plan_id 
      AND potwierdzone = 1 
      AND COALESCE(anulowana, 0) = 0
)
WHERE id = @target_plan_id;
*/

-- ============================================================
-- KROK 4: Weryfikacja po naprawie
-- ============================================================

-- Sprawdź czy wszystkie numery są ciągłe:
/*
SET @target_plan_id = 12345;  -- ZMIEŃ NA WŁAŚCIWY PLAN_ID!

SELECT 
    nr_szarzy,
    COUNT(*) as ilosc,
    GROUP_CONCAT(id) as szarza_ids
FROM szarze_agro
WHERE plan_id = @target_plan_id
GROUP BY nr_szarzy
ORDER BY nr_szarzy ASC;

-- Powinny być wszystkie numery od 1 do N bez luk
*/
