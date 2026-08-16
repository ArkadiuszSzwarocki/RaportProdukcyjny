-- Incident fix: duplicate AGRO pallets around 2026-05-19 14:12.
-- Safe mode: backup + guarded update + soft neutralize duplicate.

SET @plan_id := 33;
SET @keep_id := 62;
SET @drop_id := 63;
SET @incident_from := '2026-05-19 14:12:00';
SET @incident_to := '2026-05-19 14:13:10';

SELECT DATABASE() AS current_database;
SELECT NOW() AS executed_at;

START TRANSACTION;

-- Lock and show rows that are going to be fixed.
SELECT id, plan_id, nr_palety, waga, status, dodal_login, data_dodania
FROM palety_agro
WHERE id IN (@keep_id, @drop_id)
FOR UPDATE;

-- Build one-row guard only when IDs and scope match expected incident.
DROP TEMPORARY TABLE IF EXISTS tmp_fix_guard;
CREATE TEMPORARY TABLE tmp_fix_guard AS
SELECT 1 AS ok
FROM palety_agro
WHERE id IN (@keep_id, @drop_id)
GROUP BY plan_id
HAVING
    plan_id = @plan_id
    AND COUNT(*) = 2
    AND MIN(data_dodania) >= @incident_from
    AND MAX(data_dodania) <= @incident_to;

SELECT COUNT(*) AS guard_rows FROM tmp_fix_guard;

-- Backup original rows once.
CREATE TABLE IF NOT EXISTS backup_palety_agro_dup_20260519_1412 LIKE palety_agro;
INSERT INTO backup_palety_agro_dup_20260519_1412
SELECT p.*
FROM palety_agro p
JOIN tmp_fix_guard g ON g.ok = 1
LEFT JOIN backup_palety_agro_dup_20260519_1412 b ON b.id = p.id
WHERE p.id IN (@keep_id, @drop_id)
  AND b.id IS NULL;

CREATE TABLE IF NOT EXISTS backup_magazyn_palety_agro_dup_20260519_1412 LIKE magazyn_palety_agro;
INSERT INTO backup_magazyn_palety_agro_dup_20260519_1412
SELECT m.*
FROM magazyn_palety_agro m
JOIN tmp_fix_guard g ON g.ok = 1
LEFT JOIN backup_magazyn_palety_agro_dup_20260519_1412 b ON b.id = m.id
WHERE m.paleta_workowanie_id IN (@keep_id, @drop_id)
  AND b.id IS NULL;

-- Move potential warehouse references from duplicate to keeper.
UPDATE magazyn_palety_agro m
JOIN tmp_fix_guard g ON g.ok = 1
SET m.paleta_workowanie_id = @keep_id
WHERE m.paleta_workowanie_id = @drop_id;

-- Soft-neutralize duplicate pallet row (audit-safe, reversible from backup).
UPDATE palety_agro p
JOIN tmp_fix_guard g ON g.ok = 1
SET
    p.waga = 0,
    p.waga_potwierdzona = 0,
    p.status = 'zamknieta',
    p.dodal_login = LEFT(CONCAT(COALESCE(p.dodal_login, 'System'), ' [DUP 2026-05-19 14:12]'), 100)
WHERE p.id = @drop_id;

-- Verification snapshot.
SELECT id, plan_id, nr_palety, waga, waga_potwierdzona, status, dodal_login, data_dodania
FROM palety_agro
WHERE id IN (@keep_id, @drop_id)
ORDER BY id;

SELECT id, paleta_workowanie_id, plan_id, produkt, waga_netto, data_potwierdzenia
FROM magazyn_palety_agro
WHERE paleta_workowanie_id IN (@keep_id, @drop_id)
ORDER BY id;

COMMIT;

-- Optional: if guard_rows = 0 or verification looks wrong, run ROLLBACK instead of COMMIT.