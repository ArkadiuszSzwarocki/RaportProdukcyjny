-- Rollback for 0001_add_wyjscie_columns.sql
-- Run to remove the added columns if you need to rollback.

-- For SQL Server, DROP COLUMN IF EXISTS is not supported; use conditional checks.
IF EXISTS (
  SELECT 1 FROM sys.columns 
  WHERE Name = N'wyjscie_od' AND Object_ID = Object_ID(N'obecnosc')
)
BEGIN
  ALTER TABLE obecnosc DROP COLUMN wyjscie_od;
END

IF EXISTS (
  SELECT 1 FROM sys.columns 
  WHERE Name = N'wyjscie_do' AND Object_ID = Object_ID(N'obecnosc')
)
BEGIN
  ALTER TABLE obecnosc DROP COLUMN wyjscie_do;
END
