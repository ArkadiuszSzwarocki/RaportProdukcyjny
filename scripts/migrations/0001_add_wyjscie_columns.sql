-- Migration: add wyjscie_od and wyjscie_do to obecnosc
-- Run this once against your database (e.g. mysql -u user -p dbname < 0001_add_wyjscie_columns.sql)

ALTER TABLE obecnosc
  ADD wyjscie_od TIME NULL, wyjscie_do TIME NULL;

-- Optional: add an index if you will query by these columns frequently
-- ALTER TABLE obecnosc ADD INDEX (wyjscie_od);
