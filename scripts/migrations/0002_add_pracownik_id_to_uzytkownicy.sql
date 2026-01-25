-- Migration: add pracownik_id to uzytkownicy (map user account -> pracownicy)
-- Safe conditional add: checks INFORMATION_SCHEMA and runs ALTER only if missing
SET @exists := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='uzytkownicy' AND COLUMN_NAME='pracownik_id');
SET @sql = IF(@exists=0, 'ALTER TABLE uzytkownicy ADD COLUMN pracownik_id INT NULL', 'SELECT "column exists"');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Note: foreign key constraints are omitted to avoid migration failures on CI/older servers.
