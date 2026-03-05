from app.db import get_db_connection

conn = get_db_connection()

# Test UPDATE
update_cursor = conn.cursor()
print('PRZED UPDATE - sprawdzam co jest na 04.03...')
select_cursor = conn.cursor()
select_cursor.execute('SELECT id, data_planu FROM bufor WHERE DATE(data_planu) = %s', ('2026-03-04',))
before = select_cursor.fetchall()
print(f'  Rekordy na 04.03: {len(before)} sztuk')
for row in before:
    print(f'    - ID: {row[0]}, Data: {row[1]}')

print('')
print('WYKONUJĘ UPDATE...')
update_cursor.execute('''
    UPDATE bufor 
    SET data_planu = %s 
    WHERE DATE(data_planu) = %s
''', ('2026-03-05', '2026-03-04'))
rowcount = update_cursor.rowcount
print(f'  rowcount: {rowcount}')

print('')
print('ROBIĘ COMMIT...')
conn.commit()
print('  ✓ Commit OK')

print('')
print('PO UPDATE - sprawdzam bufor na 05.03...')
select_cursor2 = conn.cursor()
select_cursor2.execute('SELECT id, data_planu FROM bufor WHERE DATE(data_planu) = %s', ('2026-03-05',))
after = select_cursor2.fetchall()
print(f'  Rekordy na 05.03: {len(after)} sztuk')
for row in after:
    print(f'    - ID: {row[0]}, Data: {row[1]}')

print('')
print('SPRAWDZAM 04.03 PO UPDATE...')
select_cursor3 = conn.cursor()
select_cursor3.execute('SELECT id, data_planu FROM bufor WHERE DATE(data_planu) = %s', ('2026-03-04',))
remaining = select_cursor3.fetchall()
print(f'  Rekordy na 04.03: {len(remaining)} sztuk')
for row in remaining:
    print(f'    - ID: {row[0]}, Data: {row[1]}')

conn.close()
