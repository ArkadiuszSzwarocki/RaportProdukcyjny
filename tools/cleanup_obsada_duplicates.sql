-- Safe cleanup for duplicate obsada_zmiany rows
-- Keep the smallest id for each (pracownik_id, data_wpisu, sekcja)
DELETE o1
FROM obsada_zmiany o1
JOIN (
  SELECT MIN(id) AS keep_id, pracownik_id, data_wpisu, sekcja
  FROM obsada_zmiany
  GROUP BY pracownik_id, data_wpisu, sekcja
  HAVING COUNT(*) > 1
) dup ON o1.pracownik_id = dup.pracownik_id
    AND o1.data_wpisu = dup.data_wpisu
    AND o1.sekcja = dup.sekcja
    AND o1.id <> dup.keep_id;

-- Remove duplicate automatic obecnosc entries created by obsada (keep smallest id)
DELETE o1
FROM obecnosc o1
JOIN (
  SELECT MIN(id) AS keep_id, pracownik_id, data_wpisu, komentarz
  FROM obecnosc
  WHERE komentarz = 'Automatyczne z obsady'
  GROUP BY pracownik_id, data_wpisu, komentarz
  HAVING COUNT(*) > 1
) dup ON o1.pracownik_id = dup.pracownik_id
    AND o1.data_wpisu = dup.data_wpisu
    AND COALESCE(o1.komentarz,'') = COALESCE(dup.komentarz,'')
    AND o1.id <> dup.keep_id;

-- NOTE: Run a backup before executing these statements.