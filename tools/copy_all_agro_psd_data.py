import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv(override=True)

host = os.getenv('DB_HOST', 'raportprodukcji.mycloudnas.com')
port = int(os.getenv('DB_PORT', 3307))
user = os.getenv('DB_USER', 'biblioteka')
password = os.getenv('DB_PASSWORD', 'Filipinka2025')

date_str = '2026-05-19'

def get_common_columns_except_auto(src_cursor, dest_cursor, table):
    # Fetch columns from source database table
    src_cursor.execute(f"SHOW COLUMNS FROM {table}")
    src_cols = {}
    for r in src_cursor.fetchall():
        field = r.get('Field') or r.get('field') if isinstance(r, dict) else r[0]
        extra = r.get('Extra') or r.get('extra') if isinstance(r, dict) else r[5]
        src_cols[field] = extra

    # Fetch columns from destination database table and find the intersection
    dest_cursor.execute(f"SHOW COLUMNS FROM {table}")
    common_cols = []
    for r in dest_cursor.fetchall():
        field = r.get('Field') or r.get('field') if isinstance(r, dict) else r[0]
        extra = r.get('Extra') or r.get('extra') if isinstance(r, dict) else r[5]
        if field in src_cols:
            if 'auto_increment' not in str(extra).lower():
                common_cols.append(field)
    return common_cols

def copy_table_data(src_cursor, dest_cursor, table, filter_col, filter_val, mapping_func=None):
    columns = get_common_columns_except_auto(src_cursor, dest_cursor, table)
    col_list_str = ", ".join(columns)
    
    query = f"SELECT id, {col_list_str} FROM {table} WHERE {filter_col} = %s"
    src_cursor.execute(query, (filter_val,))
    rows = src_cursor.fetchall()
    
    id_map = {}
    print(f"Copying {len(rows)} records from table '{table}'...")
    
    for row in rows:
        old_id = row['id']
        row_dict = dict(row)
        del row_dict['id']
        
        # Keep only common columns
        row_dict = {col: row_dict[col] for col in columns if col in row_dict}
        
        # Apply mapping functions if defined
        if mapping_func:
            row_dict = mapping_func(row_dict)
            if row_dict is None:  # Skipped
                continue
                
        # Insert
        insert_cols = list(row_dict.keys())
        insert_vals = list(row_dict.values())
        insert_query = f"INSERT INTO {table} ({', '.join(insert_cols)}) VALUES ({', '.join(['%s']*len(insert_cols))})"
        dest_cursor.execute(insert_query, insert_vals)
        new_id = dest_cursor.lastrowid
        id_map[old_id] = new_id
        print(f"  Inserted {table} record: Old ID {old_id} -> New ID {new_id}")
        
    return id_map

def copy_table_data_in_set(src_cursor, dest_cursor, table, filter_col, filter_vals, mapping_func=None):
    if not filter_vals:
        return {}
    columns = get_common_columns_except_auto(src_cursor, dest_cursor, table)
    col_list_str = ", ".join(columns)
    
    filter_vals_list = list(filter_vals)
    placeholder_str = ", ".join(["%s"] * len(filter_vals_list))
    query = f"SELECT id, {col_list_str} FROM {table} WHERE {filter_col} IN ({placeholder_str})"
    src_cursor.execute(query, tuple(filter_vals_list))
    rows = src_cursor.fetchall()
    
    id_map = {}
    print(f"Copying {len(rows)} records from table '{table}' based on {filter_col} set...")
    
    for row in rows:
        old_id = row['id']
        row_dict = dict(row)
        del row_dict['id']
        
        # Keep only common columns
        row_dict = {col: row_dict[col] for col in columns if col in row_dict}
        
        if mapping_func:
            row_dict = mapping_func(row_dict)
            if row_dict is None:
                continue
                
        insert_cols = list(row_dict.keys())
        insert_vals = list(row_dict.values())
        insert_query = f"INSERT INTO {table} ({', '.join(insert_cols)}) VALUES ({', '.join(['%s']*len(insert_cols))})"
        dest_cursor.execute(insert_query, insert_vals)
        new_id = dest_cursor.lastrowid
        id_map[old_id] = new_id
        print(f"  Inserted {table} record: Old ID {old_id} -> New ID {new_id}")
        
    return id_map

def main():
    print("Initiating WMS Database Copy Process from biblioteka_testowa to biblioteka...")
    
    src_conn = mysql.connector.connect(
        host=host, port=port, user=user, password=password, database='biblioteka_testowa'
    )
    dest_conn = mysql.connector.connect(
        host=host, port=port, user=user, password=password, database='biblioteka'
    )
    
    src_cursor = src_conn.cursor(dictionary=True)
    dest_cursor = dest_conn.cursor(dictionary=True)
    
    try:
        # Start transaction on destination
        dest_conn.start_transaction()
        
        # 1. Copy plan_produkcji (PSD)
        psd_plan_map = copy_table_data(src_cursor, dest_cursor, 'plan_produkcji', 'data_planu', date_str)
        
        # 2. Copy plan_produkcji_agro (AGRO)
        # We need to handle self-referencing zasyp_id. We'll insert with zasyp_id=None first,
        # then update after inserting all plans.
        src_cursor.execute(f"SELECT id, zasyp_id FROM plan_produkcji_agro WHERE data_planu = %s", (date_str,))
        agro_plans_raw = src_cursor.fetchall()
        old_zasyp_relations = {r['id']: r['zasyp_id'] for r in agro_plans_raw if r['zasyp_id'] is not None}
        
        def map_agro_plan(row_dict):
            # Temporarily set zasyp_id to None
            row_dict['zasyp_id'] = None
            return row_dict
            
        agro_plan_map = copy_table_data(src_cursor, dest_cursor, 'plan_produkcji_agro', 'data_planu', date_str, map_agro_plan)
        
        # Now update zasyp_id relationships in the destination plan_produkcji_agro
        for old_id, old_zasyp_id in old_zasyp_relations.items():
            new_id = agro_plan_map.get(old_id)
            new_zasyp_id = agro_plan_map.get(old_zasyp_id)
            if new_id and new_zasyp_id:
                dest_cursor.execute(
                    "UPDATE plan_produkcji_agro SET zasyp_id = %s WHERE id = %s",
                    (new_zasyp_id, new_id)
                )
                print(f"  Updated plan_produkcji_agro self-FK: ID {new_id} zasyp_id -> {new_zasyp_id}")
                
        # 3. Copy szarze (PSD Batches)
        def map_szarze(row_dict):
            old_plan_id = row_dict['plan_id']
            row_dict['plan_id'] = psd_plan_map.get(old_plan_id)
            return row_dict if row_dict['plan_id'] is not None else None
            
        szarze_map = copy_table_data_in_set(src_cursor, dest_cursor, 'szarze', 'plan_id', psd_plan_map.keys(), map_szarze)
        
        # 4. Copy szarze_agro (AGRO Batches)
        def map_szarze_agro(row_dict):
            old_plan_id = row_dict['plan_id']
            row_dict['plan_id'] = agro_plan_map.get(old_plan_id)
            return row_dict if row_dict['plan_id'] is not None else None
            
        szarze_agro_map = copy_table_data_in_set(src_cursor, dest_cursor, 'szarze_agro', 'plan_id', agro_plan_map.keys(), map_szarze_agro)
        
        # 5. Copy palety_workowanie (PSD Pallets)
        def map_palety_workowanie(row_dict):
            old_plan_id = row_dict['plan_id']
            row_dict['plan_id'] = psd_plan_map.get(old_plan_id)
            return row_dict if row_dict['plan_id'] is not None else None
            
        palety_workowanie_map = copy_table_data_in_set(src_cursor, dest_cursor, 'palety_workowanie', 'plan_id', psd_plan_map.keys(), map_palety_workowanie)
        
        # 6. Copy palety_agro (AGRO Pallets)
        def map_palety_agro(row_dict):
            old_plan_id = row_dict['plan_id']
            row_dict['plan_id'] = agro_plan_map.get(old_plan_id)
            return row_dict if row_dict['plan_id'] is not None else None
            
        palety_agro_map = copy_table_data_in_set(src_cursor, dest_cursor, 'palety_agro', 'plan_id', agro_plan_map.keys(), map_palety_agro)
        
        # 7. Copy magazyn_palety (PSD Warehouse)
        def map_magazyn_palety(row_dict):
            old_plan_id = row_dict['plan_id']
            old_paleta_id = row_dict['paleta_workowanie_id']
            row_dict['plan_id'] = psd_plan_map.get(old_plan_id) if old_plan_id else None
            row_dict['paleta_workowanie_id'] = palety_workowanie_map.get(old_paleta_id) if old_paleta_id else None
            return row_dict
            
        # Copy based on plan_id
        copy_table_data_in_set(src_cursor, dest_cursor, 'magazyn_palety', 'plan_id', psd_plan_map.keys(), map_magazyn_palety)
        
        # 8. Copy magazyn_palety_agro (AGRO Warehouse)
        def map_magazyn_palety_agro(row_dict):
            old_plan_id = row_dict['plan_id']
            old_paleta_id = row_dict['paleta_workowanie_id']
            row_dict['plan_id'] = agro_plan_map.get(old_plan_id) if old_plan_id else None
            row_dict['paleta_workowanie_id'] = palety_agro_map.get(old_paleta_id) if old_paleta_id else None
            return row_dict
            
        copy_table_data_in_set(src_cursor, dest_cursor, 'magazyn_palety_agro', 'plan_id', agro_plan_map.keys(), map_magazyn_palety_agro)
        
        # 9. Copy bufor (PSD Buffer)
        def map_bufor(row_dict):
            old_zasyp_id = row_dict['zasyp_id']
            row_dict['zasyp_id'] = psd_plan_map.get(old_zasyp_id)
            return row_dict if row_dict['zasyp_id'] is not None else None
            
        copy_table_data_in_set(src_cursor, dest_cursor, 'bufor', 'zasyp_id', psd_plan_map.keys(), map_bufor)
        
        # 10. Copy bufor_agro (AGRO Buffer)
        def map_bufor_agro(row_dict):
            old_zasyp_id = row_dict['zasyp_id']
            row_dict['zasyp_id'] = agro_plan_map.get(old_zasyp_id)
            return row_dict if row_dict['zasyp_id'] is not None else None
            
        copy_table_data_in_set(src_cursor, dest_cursor, 'bufor_agro', 'zasyp_id', agro_plan_map.keys(), map_bufor_agro)
        
        # 11. Copy dosypki (PSD Additives)
        def map_dosypki(row_dict):
            old_plan_id = row_dict['plan_id']
            old_szarza_id = row_dict['szarza_id']
            row_dict['plan_id'] = psd_plan_map.get(old_plan_id)
            row_dict['szarza_id'] = szarze_map.get(old_szarza_id) if old_szarza_id else None
            return row_dict if row_dict['plan_id'] is not None else None
            
        copy_table_data_in_set(src_cursor, dest_cursor, 'dosypki', 'plan_id', psd_plan_map.keys(), map_dosypki)
        
        # 12. Copy dosypki_agro (AGRO Additives)
        # Check if table exists in dest first (it exists in source)
        dest_cursor.execute("SHOW TABLES LIKE 'dosypki_agro'")
        if dest_cursor.fetchone():
            def map_dosypki_agro(row_dict):
                old_plan_id = row_dict['plan_id']
                old_szarza_id = row_dict.get('szarza_id')
                row_dict['plan_id'] = agro_plan_map.get(old_plan_id)
                if old_szarza_id and 'szarza_id' in row_dict:
                    row_dict['szarza_id'] = szarze_agro_map.get(old_szarza_id)
                return row_dict if row_dict['plan_id'] is not None else None
                
            copy_table_data_in_set(src_cursor, dest_cursor, 'dosypki_agro', 'plan_id', agro_plan_map.keys(), map_dosypki_agro)
            
        # 13. Copy zasyp_etapy
        # Filtered by date
        def map_zasyp_etapy(row_dict):
            linia = str(row_dict['linia']).upper()
            old_plan_id = row_dict['plan_id']
            if linia == 'PSD':
                row_dict['plan_id'] = psd_plan_map.get(old_plan_id)
            elif linia == 'AGRO':
                row_dict['plan_id'] = agro_plan_map.get(old_plan_id)
            return row_dict if row_dict['plan_id'] is not None else None
            
        copy_table_data(src_cursor, dest_cursor, 'zasyp_etapy', 'data_planu', date_str, map_zasyp_etapy)
        
        # 14. Copy zasyp_etapy_parametry
        def map_zasyp_etapy_param(row_dict):
            linia = str(row_dict['linia']).upper()
            old_plan_id = row_dict['plan_id']
            if linia == 'PSD':
                row_dict['plan_id'] = psd_plan_map.get(old_plan_id)
            elif linia == 'AGRO':
                row_dict['plan_id'] = agro_plan_map.get(old_plan_id)
            return row_dict if row_dict['plan_id'] is not None else None
            
        copy_table_data(src_cursor, dest_cursor, 'zasyp_etapy_parametry', 'data_planu', date_str, map_zasyp_etapy_param)
        
        # 15. Copy mom_rozliczenia
        def map_mom_rozl(row_dict):
            old_plan_id = row_dict['plan_id']
            row_dict['plan_id'] = agro_plan_map.get(old_plan_id)
            return row_dict if row_dict['plan_id'] is not None else None
            
        mom_rozl_map = copy_table_data(src_cursor, dest_cursor, 'mom_rozliczenia', 'data_planu', date_str, map_mom_rozl)
        
        # 16. Copy mom_pozycje (linked to copied mom_rozliczenia)
        if mom_rozl_map:
            def map_mom_pozycje(row_dict):
                old_mom_id = row_dict['mom_id']
                row_dict['mom_id'] = mom_rozl_map.get(old_mom_id)
                return row_dict if row_dict['mom_id'] is not None else None
                
            copy_table_data_in_set(src_cursor, dest_cursor, 'mom_pozycje', 'mom_id', mom_rozl_map.keys(), map_mom_pozycje)
            
        # 17. Copy agro_workowanie_rozliczenie
        def map_agro_work_rozl(row_dict):
            old_plan_id = row_dict['plan_id']
            row_dict['plan_id'] = agro_plan_map.get(old_plan_id)
            return row_dict if row_dict['plan_id'] is not None else None
            
        copy_table_data_in_set(src_cursor, dest_cursor, 'agro_workowanie_rozliczenie', 'plan_id', agro_plan_map.keys(), map_agro_work_rozl)
        
        # 18. Copy palety_historia
        # We query any movements on 2026-05-19 OR movements pointing to any of the copied pallet IDs
        pallet_p_old_ids = list(palety_workowanie_map.keys())
        pallet_a_old_ids = list(palety_agro_map.keys())
        
        conditions = ["DATE(data_ruchu) = %s"]
        params = [date_str]
        
        if pallet_p_old_ids:
            conditions.append(f"(linia = 'PSD' AND paleta_id IN ({','.join(['%s']*len(pallet_p_old_ids))}))")
            params.extend(pallet_p_old_ids)
            
        if pallet_a_old_ids:
            conditions.append(f"(linia = 'AGRO' AND paleta_id IN ({','.join(['%s']*len(pallet_a_old_ids))}))")
            params.extend(pallet_a_old_ids)
            
        history_query = f"SELECT * FROM palety_historia WHERE {' OR '.join(conditions)}"
        src_cursor.execute(history_query, tuple(params))
        history_rows = src_cursor.fetchall()
        
        print(f"Copying {len(history_rows)} records from palety_historia...")
        history_columns = get_common_columns_except_auto(src_cursor, dest_cursor, 'palety_historia')
        
        for row in history_rows:
            old_id = row['id']
            # We construct a row_dict containing only common columns
            row_dict = {col: row[col] for col in history_columns if col in row}
            
            linia = str(row_dict.get('linia', '')).upper()
            old_paleta_id = row_dict.get('paleta_id')
            
            if old_paleta_id:
                if linia == 'PSD':
                    row_dict['paleta_id'] = palety_workowanie_map.get(old_paleta_id)
                elif linia == 'AGRO':
                    row_dict['paleta_id'] = palety_agro_map.get(old_paleta_id)
                    
            # Insert history
            ins_cols = list(row_dict.keys())
            ins_vals = list(row_dict.values())
            ins_query = f"INSERT INTO palety_historia ({', '.join(ins_cols)}) VALUES ({', '.join(['%s']*len(ins_cols))})"
            dest_cursor.execute(ins_query, ins_vals)
            print(f"  Inserted palety_historia record: Old ID {old_id} -> New ID {dest_cursor.lastrowid}")
            
        # Commit the transaction!
        dest_conn.commit()
        print("\nSUCCESS: All data from 19.05.2026 successfully copied and transaction committed!")
        
    except Exception as e:
        dest_conn.rollback()
        print("\nERROR occurred, rolling back destination transaction! Details:")
        import traceback
        traceback.print_exc()
    finally:
        src_cursor.close()
        dest_cursor.close()
        src_conn.close()
        dest_conn.close()

if __name__ == '__main__':
    main()
