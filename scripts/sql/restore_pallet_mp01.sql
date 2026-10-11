-- Przywrócenie palety SUR000001789972723706 na strefę MP01
UPDATE magazyn_surowce 
SET lokalizacja = 'MP01', is_blocked = 0 
WHERE nr_palety = 'SUR000001789972723706';

UPDATE magazyn_palety 
SET lokalizacja = 'MP01', is_blocked = 0, is_loaded = 0 
WHERE nr_palety = 'SUR000001789972723706';

UPDATE magazyn_palety_agro 
SET lokalizacja = 'MP01', is_blocked = 0, is_loaded = 0 
WHERE nr_palety = 'SUR000001789972723706';

UPDATE magazyn_opakowania 
SET lokalizacja = 'MP01', is_blocked = 0 
WHERE nr_palety = 'SUR000001789972723706';

UPDATE magazyn_dodatki 
SET lokalizacja = 'MP01', is_blocked = 0 
WHERE nr_palety = 'SUR000001789972723706';
