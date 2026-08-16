-- Rollback: remove pracownik_id from uzytkownicy
SET @exists := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='uzytkownicy' AND COLUMN_NAME='pracownik_id');
SET @sql = IF(@exists=1, 'ALTER TABLE uzytkownicy DROP COLUMN pracownik_id', 'SELECT "no column"');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
