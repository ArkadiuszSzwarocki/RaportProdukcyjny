-- staging_migration.sql
-- Deduplikacja i dodanie indeksu UNIQUE na plan_produkcji(zasyp_id)
-- Uwaga: uruchomić tylko po wykonaniu backupu bazy.

-- 1) Sprawdź ile mamy potencjalnych duplikatów
-- SELECT zasyp_id, COUNT(*) as cnt FROM plan_produkcji GROUP BY zasyp_id HAVING cnt > 1;

-- 2) Usuń zduplikowane rekordy, pozostawiając najstarszy (najniższe id)
DELETE p1
FROM plan_produkcji p1
INNER JOIN plan_produkcji p2
  ON p1.zasyp_id = p2.zasyp_id AND p1.id > p2.id;

-- 3) Dodaj unikalny indeks (jeżeli nie istnieje)
-- Jeśli twoja wersja MySQL nie wspiera IF NOT EXISTS dla ADD CONSTRAINT,
-- uruchom poniższy ALTER tylko raz; skrypt zakłada, że indeks nie istnieje.
ALTER TABLE plan_produkcji
  ADD CONSTRAINT uq_plan_produkcji_zasyp_id UNIQUE (zasyp_id);

-- 4) Weryfikacja: powinien zwrócić 0 wierszy
-- SELECT zasyp_id, COUNT(*) as cnt FROM plan_produkcji GROUP BY zasyp_id HAVING cnt > 1;

-- KONIEC
