import json
from app.core.database import get_db_connection

class TraceabilityService:
    @staticmethod
    def get_pallet_trace(nr_palety):
        """Trace a finished pallet bottom-up to its raw materials."""
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            # 1. Find the pallet
            query_pallet = """
                SELECT id, nr_palety, plan_id, 'PSD' as linia, produkt, waga_netto, data_potwierdzenia, 'WYROB_GOTOWY' as type 
                FROM magazyn_palety WHERE nr_palety = %s
                UNION ALL
                SELECT id, nr_palety, plan_id, 'AGRO' as linia, produkt, waga_netto, data_potwierdzenia, 'WYROB_GOTOWY' as type 
                FROM magazyn_palety_agro WHERE nr_palety = %s
                UNION ALL
                SELECT id, nr_palety, plan_id, 'PSD' as linia, 'W trakcie workowania' as produkt, waga_brutto as waga_netto, data_dodania as data_potwierdzenia, 'W_WORKOWANIU' as type 
                FROM palety_workowanie WHERE nr_palety = %s
                UNION ALL
                SELECT id, nr_palety, plan_id, 'AGRO' as linia, 'W trakcie workowania' as produkt, waga_brutto as waga_netto, data_dodania as data_potwierdzenia, 'W_WORKOWANIU' as type 
                FROM palety_agro WHERE nr_palety = %s
            """
            cursor.execute(query_pallet, (nr_palety, nr_palety, nr_palety, nr_palety))
            pallet = cursor.fetchone()
            
            if not pallet:
                return {"error": "Paleta nie została znaleziona"}
                
            plan_id = pallet.get('plan_id')
            if not plan_id:
                return {
                    "pallet": pallet,
                    "plan": None,
                    "materials": [],
                    "message": "Paleta nie ma powiązanego zlecenia produkcyjnego (plan_id)."
                }
            
            # 2. Find the plan based on pallet's line
            linia = pallet.get('linia', 'PSD')
            if linia == 'AGRO':
                query_plan = """
                    SELECT id, data_planu, produkt, nazwa_zlecenia, typ_produkcji, data_produkcji, zasyp_id, real_start, real_stop, 'AGRO' as linia,
                           COALESCE(nr_receptury, '') as nr_receptury
                    FROM plan_produkcji_agro WHERE id = %s
                """
            else:
                query_plan = """
                    SELECT id, data_planu, produkt, nazwa_zlecenia, typ_produkcji, data_produkcji, 'PSD' as linia,
                           '' as nr_receptury
                    FROM plan_produkcji WHERE id = %s
                """
            cursor.execute(query_plan, (plan_id,))
            plan = cursor.fetchone()

            # 3. Find raw materials consumed
            materials = []
            if linia == 'AGRO' and plan:
                import datetime
                
                # Check for direct moves on this plan (packing plan)
                cursor.execute("""
                    SELECT r.id, r.surowiec_id, COALESCE(s.nazwa, r.surowiec_nazwa) as surowiec_nazwa, r.nr_partii, r.ilosc as zuzycie, r.typ_ruchu, r.autor_data, r.status, r.zbiornik
                    FROM magazyn_agro_ruch r
                    LEFT JOIN magazyn_agro_opakowania s ON r.surowiec_id = s.id
                    WHERE r.plan_id = %s AND r.typ_ruchu IN ('PRODUKCJA', 'ZUZYCIE', 'POBRANIE_DO_PRODUKCJI')
                    ORDER BY r.autor_data DESC
                """, (plan_id,))
                for r in cursor.fetchall():
                    name = r['surowiec_nazwa']
                    partia = r['nr_partii']
                    if not name and r['surowiec_id']:
                        cursor.execute("SELECT nazwa, nr_partii FROM magazyn_opakowania WHERE id = %s", (r['surowiec_id'],))
                        op_row = cursor.fetchone()
                        if op_row:
                            name = op_row['nazwa']
                            partia = op_row['nr_partii']
                    materials.append({
                        'id': r['id'],
                        'surowiec_id': r['surowiec_id'],
                        'surowiec_nazwa': name or 'Opakowanie/Folia',
                        'nr_partii': partia or 'Brak',
                        'zuzycie': r['zuzycie'],
                        'typ_ruchu': r['typ_ruchu'],
                        'autor_data': r['autor_data'],
                        'status': r['status'],
                        'zbiornik': r['zbiornik'] or 'Workowanie',
                        'linia': 'AGRO'
                    })
                
                # We trace raw materials from the associated mixing plan (zasyp_id) or fallback to this plan
                target_mix_id = plan.get('zasyp_id') or plan_id
                cursor.execute("SELECT id, real_start, real_stop FROM plan_produkcji_agro WHERE id = %s", (target_mix_id,))
                mix_plan = cursor.fetchone()
                
                if mix_plan and mix_plan.get('real_start'):
                    m_start = mix_plan['real_start']
                    m_stop = mix_plan.get('real_stop') or datetime.datetime.now()
                    
                    # A. Fetch active tank allocations at start time
                    q_active_start = """
                        SELECT r.id as ruch_id, r.surowiec_id, COALESCE(s.nazwa, r.surowiec_nazwa) as surowiec_nazwa, s.nr_partii, r.zbiornik, r.autor_data, r.ilosc
                        FROM magazyn_agro_ruch r
                        LEFT JOIN magazyn_agro_surowce s ON r.surowiec_id = s.id
                        WHERE r.typ_ruchu = 'PRODUKCJA' AND r.status = 'POTWIERDZONE'
                          AND r.autor_data <= %s
                          AND r.zbiornik IS NOT NULL AND TRIM(r.zbiornik) <> ''
                          AND NOT EXISTS (
                              SELECT 1 FROM magazyn_agro_ruch z 
                              WHERE z.ruch_zrodlowy_id = r.id AND z.typ_ruchu = 'ZWROT' 
                                AND z.autor_data <= %s
                          )
                    """
                    cursor.execute(q_active_start, (m_start, m_start))
                    for r in cursor.fetchall():
                        # Check if replaced before start_time
                        cursor.execute(
                            "SELECT id FROM magazyn_agro_ruch WHERE typ_ruchu = 'PRODUKCJA' AND status = 'POTWIERDZONE' AND zbiornik = %s AND id > %s AND autor_data <= %s",
                            (r['zbiornik'], r['ruch_id'], m_start)
                        )
                        if not cursor.fetchone():
                            materials.append({
                                'id': r['ruch_id'],
                                'surowiec_id': r['surowiec_id'],
                                'surowiec_nazwa': r['surowiec_nazwa'] or 'Surowiec',
                                'nr_partii': r['nr_partii'] or 'Brak',
                                'zuzycie': r['ilosc'],
                                'typ_ruchu': 'ZASYP (ZBIORNIK)',
                                'autor_data': r['autor_data'],
                                'status': 'POTWIERDZONE',
                                'zbiornik': r['zbiornik'],
                                'linia': 'AGRO'
                            })
                    
                    # B. Fetch tank allocations loaded during the plan run
                    q_during = """
                        SELECT r.id as ruch_id, r.surowiec_id, COALESCE(s.nazwa, r.surowiec_nazwa) as surowiec_nazwa, s.nr_partii, r.zbiornik, r.autor_data, r.ilosc
                        FROM magazyn_agro_ruch r
                        LEFT JOIN magazyn_agro_surowce s ON r.surowiec_id = s.id
                        WHERE r.typ_ruchu = 'PRODUKCJA' AND r.status = 'POTWIERDZONE'
                          AND r.autor_data > %s AND r.autor_data <= %s
                          AND r.zbiornik IS NOT NULL AND TRIM(r.zbiornik) <> ''
                    """
                    cursor.execute(q_during, (m_start, m_stop))
                    for r in cursor.fetchall():
                        materials.append({
                            'id': r['ruch_id'],
                            'surowiec_id': r['surowiec_id'],
                            'surowiec_nazwa': r['surowiec_nazwa'] or 'Surowiec',
                            'nr_partii': r['nr_partii'] or 'Brak',
                            'zuzycie': r['ilosc'],
                            'typ_ruchu': 'ZASYP (ZBIORNIK)',
                            'autor_data': r['autor_data'],
                            'status': 'POTWIERDZONE',
                            'zbiornik': r['zbiornik'],
                            'linia': 'AGRO'
                        })
                
                # C. Fetch dosypki manualne for the mixing plan
                q_dosypki = """
                    SELECT d.id, d.nazwa as surowiec_nazwa, d.kg as zuzycie, d.data_potwierdzenia as autor_data
                    FROM dosypki_agro d
                    WHERE d.plan_id = %s AND d.potwierdzone = 1 AND d.anulowana = 0
                    ORDER BY d.data_potwierdzenia ASC
                """
                cursor.execute(q_dosypki, (target_mix_id,))
                for r in cursor.fetchall():
                    materials.append({
                        'id': r['id'],
                        'surowiec_id': None,
                        'surowiec_nazwa': r['surowiec_nazwa'],
                        'nr_partii': 'Dosypka manualna',
                        'zuzycie': -r['zuzycie'],
                        'typ_ruchu': 'DOSYPKA',
                        'autor_data': r['autor_data'],
                        'status': 'POTWIERDZONE',
                        'zbiornik': 'Dosypka',
                        'linia': 'AGRO'
                    })
            else:
                # PSD
                query_materials = """
                    SELECT id, surowiec_id, surowiec_nazwa, nr_partii, ilosc as zuzycie, typ_ruchu, autor_data, status, 'PSD' as linia 
                    FROM magazyn_ruch 
                    WHERE plan_id = %s AND typ_ruchu IN ('PRODUKCJA', 'ZUZYCIE')
                    ORDER BY autor_data DESC
                """
                cursor.execute(query_materials, (plan_id,))
                materials = cursor.fetchall()
            
            # D. Fetch receptura (recipe template) if plan has nr_receptury
            receptura = []
            nr_receptury_plan = (plan or {}).get('nr_receptury') or ''

            # Fallback: if Workowanie plan doesn't have nr_receptury, check linked Zasyp plan
            if linia == 'AGRO' and not nr_receptury_plan and plan:
                zasyp_id_for_rec = plan.get('zasyp_id')
                if zasyp_id_for_rec:
                    try:
                        cursor.execute(
                            "SELECT COALESCE(nr_receptury, '') as nr_receptury FROM plan_produkcji_agro WHERE id = %s",
                            (zasyp_id_for_rec,)
                        )
                        zr = cursor.fetchone()
                        if zr:
                            nr_receptury_plan = zr.get('nr_receptury') or ''
                    except Exception:
                        pass

            if linia == 'AGRO' and nr_receptury_plan:
                try:
                    cursor.execute("""
                        SELECT skladnik_nazwa, ilosc_kg_szarza, typ, kolejnosc
                        FROM receptury_agro_skladniki
                        WHERE nr_receptury = %s AND aktywny = 1
                        ORDER BY kolejnosc ASC, id ASC
                    """, (nr_receptury_plan,))
                    receptura = cursor.fetchall() or []
                except Exception:
                    receptura = []

            return {
                "pallet": pallet,
                "plan": plan,
                "materials": materials,
                "receptura": receptura,
                "nr_receptury": nr_receptury_plan,
            }
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def get_lot_trace(nr_partii):
        """Trace a lot (nr_partii) top-down to its usage and pallets."""
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            # 1. Find Receipts (Dostawy) containing this lot
            # MySQL might not support JSON_SEARCH perfectly if version is old, so we do LIKE
            search_str = f"%{nr_partii}%"
            cursor.execute("SELECT id, supplier, delivery_date, status, items, created_at, potwierdzone_przez FROM magazyn_dostawy WHERE items LIKE %s ORDER BY created_at DESC", (search_str,))
            deliveries = cursor.fetchall()
            
            parsed_deliveries = []
            for d in deliveries:
                items_str = d.get('items')
                matched_items = []
                if items_str:
                    try:
                        items = json.loads(items_str)
                        for item in items:
                            if item.get('nr_partii') == nr_partii or nr_partii.lower() in str(item.get('nr_partii', '')).lower():
                                matched_items.append(item)
                    except:
                        pass
                if matched_items:
                    d['matched_items'] = matched_items
                    del d['items']
                    parsed_deliveries.append(d)
            
            # 2. Find specific consumptions in production
            query_consumptions = """
                SELECT id, plan_id, surowiec_id, surowiec_nazwa, ilosc as zuzycie, autor_data, 'PSD' as linia 
                FROM magazyn_ruch WHERE nr_partii = %s AND plan_id IS NOT NULL AND typ_ruchu IN ('PRODUKCJA', 'ZUZYCIE')
                UNION ALL
                SELECT id, plan_id, surowiec_id, surowiec_nazwa, ilosc as zuzycie, autor_data, 'AGRO' as linia 
                FROM magazyn_agro_ruch WHERE nr_partii = %s AND plan_id IS NOT NULL AND typ_ruchu IN ('PRODUKCJA', 'ZUZYCIE')
            """
            cursor.execute(query_consumptions, (nr_partii, nr_partii))
            consumptions = cursor.fetchall()
            
            plans = []
            if consumptions:
                plan_ids_psd = list(set([c['plan_id'] for c in consumptions if c['linia'] == 'PSD']))
                plan_ids_agro = list(set([c['plan_id'] for c in consumptions if c['linia'] == 'AGRO']))
                
                if plan_ids_psd:
                    format_strings = ','.join(['%s'] * len(plan_ids_psd))
                    cursor.execute(f"SELECT id, data_planu, produkt, nazwa_zlecenia, typ_produkcji, 'PSD' as linia FROM plan_produkcji WHERE id IN ({format_strings})", tuple(plan_ids_psd))
                    plans.extend(cursor.fetchall())
                
                if plan_ids_agro:
                    format_strings = ','.join(['%s'] * len(plan_ids_agro))
                    cursor.execute(f"SELECT id, data_planu, produkt, nazwa_zlecenia, typ_produkcji, 'AGRO' as linia FROM plan_produkcji_agro WHERE id IN ({format_strings})", tuple(plan_ids_agro))
                    plans.extend(cursor.fetchall())
            
            # 3. Find produced pallets for those plans
            pallets = []
            all_plan_ids = [p['id'] for p in plans]
            if all_plan_ids:
                format_strings = ','.join(['%s'] * len(all_plan_ids))
                # PSD Palety
                cursor.execute(f"SELECT id, nr_palety, plan_id, 'PSD' as linia, produkt, waga_netto, data_potwierdzenia FROM magazyn_palety WHERE plan_id IN ({format_strings})", tuple(all_plan_ids))
                pallets.extend(cursor.fetchall())
                # AGRO Palety
                cursor.execute(f"SELECT id, nr_palety, plan_id, 'AGRO' as linia, produkt, waga_netto, data_potwierdzenia FROM magazyn_palety_agro WHERE plan_id IN ({format_strings})", tuple(all_plan_ids))
                pallets.extend(cursor.fetchall())
                
            return {
                "deliveries": parsed_deliveries,
                "consumptions": consumptions,
                "plans": plans,
                "pallets": pallets
            }
        finally:
            cursor.close()
            conn.close()
