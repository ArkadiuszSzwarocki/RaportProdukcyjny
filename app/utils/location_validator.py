"""
Walidacja lokalizacji magazynowych.

Zapobiega używaniu kodów zbiorników produkcyjnych (BB*, MZ*, KO*) 
jako lokalizacji w magazynie surowców, opakowań i wyrobów gotowych.
"""
import re

# Wzorce kodów zbiorników produkcyjnych (NIE mogą być lokalizacjami magazynowymi!)
PRODUCTION_TANK_PATTERNS = [
    r'^BB(0[1-6]|1[1-9]|2[0-2])$',      # BB01-BB06, BB11-BB22 (BB07-BB10, BB23-BB24 usunięte)
    r'^MZ(0[7-9]|10|23|24)$',          # MZ07-MZ10, MZ23-MZ24 (MZ01-MZ06, MZ11-MZ22 usunięte)
    r'^KO\d{2}$',                      # KO01, KO02, ..., KO40
    r'^CZ\d{2}$',                      # CZ01, CZ02, ... (Czyszczenie)
    r'^WZ\d{2}$',                      # WZ04 (new production tank)
    r'^PSD\d*$',                       # PSD, PSD01, PSD02
    r'^MIX\d*$',                       # MIX, MIX01
]

DELETED_STATION_CODES = {
    'BB07', 'BB08', 'BB09', 'BB10', 'BB23', 'BB24',
    'MZ01', 'MZ02', 'MZ03', 'MZ04', 'MZ05', 'MZ06',
    'MZ11', 'MZ12', 'MZ13', 'MZ14', 'MZ15', 'MZ16', 'MZ17', 'MZ18', 'MZ19', 'MZ20', 'MZ21', 'MZ22',
    'MZ05-01', 'MZ06-01'
}

def is_deleted_station_code(location_code):
    """Sprawdza czy kod to usunięta ze stanowisk stacja BB lub MZ."""
    if not location_code:
        return False
    normalized = str(location_code).strip().upper()
    return normalized in DELETED_STATION_CODES

def is_production_tank_code(location_code):
    """
    Sprawdza czy podany kod to kod zbiornika produkcyjnego.
    Lokalizacje buforowe i magazynowe (BF_MS01, BF_MP01, BFOS itp.) ZAWSZE zwracają False,
    ponieważ są lokalizacjami magazynowymi, a NIE produkcyjnymi.
    
    Args:
        location_code: Kod lokalizacji do sprawdzenia
        
    Returns:
        True jeśli to kod zbiornika produkcyjnego (BB*, MZ*, KO*, CZ*, WZ*)
        False w przeciwnym wypadku (w tym dla BF_MS01, BF_MP01 itp.)
    """
    if not location_code:
        return False
    
    normalized = str(location_code).strip().upper()
    if not normalized:
        return False

    clean_norm = normalized.replace('_', '').replace('-', '').replace(' ', '')
    # Bufory magazynowe (BF_MS01, BF_MP01, BFOS, BF_*), stacje maszyn (LP01) to lokalizacje magazynowe, NIE produkcyjne
    if clean_norm.startswith(('BFMS', 'BFMP', 'BFOS', 'BF', 'MS01', 'MP01', 'MDM01', 'MOP01', 'MDO01', 'MGW01', 'MGW02', 'RAMPA', 'R0', 'LP01', 'LP')):
        return False
        
    for pattern in PRODUCTION_TANK_PATTERNS:
        if re.match(pattern, normalized):
            return True
    return False


def is_machine_location(location_code):
    """
    Sprawdza czy kod to lokalizacja maszyny / linii pakującej (LP01, MASZYNA).
    """
    if not location_code:
        return False
    norm = str(location_code).strip().upper()
    return norm in ('LP01', 'LP', 'MASZYNA')


def is_warehouse_location(location_code):
    """
    Sprawdza czy kod jest lokalizacją magazynową (regały, podłogi magazynowe, bufory BF_MS01, BF_MP01 itp., linia LP01).
    """
    if not location_code:
        return False
    normalized = str(location_code).strip().upper()
    if not normalized:
        return False
    clean_norm = normalized.replace('_', '').replace('-', '').replace(' ', '')
    if clean_norm.startswith(('BFMS', 'BFMP', 'BFOS', 'BF', 'MS', 'MP', 'MOP', 'MDM', 'MGW', 'MDO', 'MD', 'PSD', 'RAMPA', 'MIX', 'OSIP', 'KO', 'R0', 'LP')):
        return True
    return not is_production_tank_code(normalized)


def validate_warehouse_location(location_code, allow_empty=True):
    """
    Waliduje czy kod lokalizacji może być użyty w magazynie.
    
    Args:
        location_code: Kod lokalizacji do sprawdzenia
        allow_empty: Czy dozwolone są puste/None wartości
        
    Returns:
        Tuple (is_valid: bool, error_message: str)
        
    Examples:
        >>> validate_warehouse_location("R021002")
        (True, None)
        
        >>> validate_warehouse_location("BB15")
        (False, "BB15 to kod zbiornika produkcyjnego. Użyj kodów regałów (np. R021002)")
        
        >>> validate_warehouse_location(None, allow_empty=True)
        (True, None)
        
        >>> validate_warehouse_location(None, allow_empty=False)
        (False, "Lokalizacja jest wymagana")
    """
    if not location_code or str(location_code).strip() == '':
        if allow_empty:
            return True, None
        else:
            return False, "Lokalizacja jest wymagana"
    
    normalized = str(location_code).strip().upper()
    clean_norm = normalized.replace('_', '').replace('-', '').replace(' ', '')
    
    # Wyjątek: Magazyny, bufory (BFMS01, BFMP01, BFOS, BF_*), KO oraz stacje maszyn (LP01, MASZYNA) są dozwolonymi lokalizacjami magazynowymi
    if clean_norm.startswith(('BFMS', 'BFMP', 'BFOS', 'BF', 'MS', 'MP', 'MOP', 'MDM', 'MGW', 'MDO', 'MD', 'PSD', 'RAMPA', 'MIX', 'OSIP', 'KO', 'R0', 'LP')) or clean_norm == 'MASZYNA':
        return True, None

    if is_deleted_station_code(normalized):
        return False, (
            f"Lokalizacja {normalized} to wycofana/usunięta stacja produkcyjna. "
            "Użyj kodów regałów magazynowych (np. R021002, R030601)"
        )

    if is_production_tank_code(normalized):
        return False, (
            f"{normalized} to kod zbiornika produkcyjnego (BB/MZ są tylko do przypisywania surowców w produkcji). "
            "Użyj kodów regałów magazynowych (np. R021002, R030601)"
        )
    
    return True, None


def normalize_warehouse_location(location_code):
    """
    Normalizes warehouse location code (uppercase, trim) and auto-corrects common
    character typos such as the letter 'O' instead of digit '0' in standard warehouse
    zone and rack codes (e.g. MSO1 -> MS01, MPO1 -> MP01, RO01 -> R001, LPO1 -> LP01).
    
    Args:
        location_code: Location code string to normalize
        
    Returns:
        Normalized location code or None if empty
    """
    if not location_code:
        return None
    
    normalized = str(location_code).strip().upper()
    if not normalized:
        return None

    # Auto-correct common letter 'O' instead of digit '0' in standard prefixes
    for prefix in ('MS', 'MP', 'MD', 'MGW', 'MOP', 'MDM', 'MDO', 'MIX', 'PSD', 'KO', 'LP'):
        if normalized.startswith(f"{prefix}O") and len(normalized) > len(prefix) + 1 and normalized[len(prefix)+1].isdigit():
            normalized = f"{prefix}0{normalized[len(prefix)+1:]}"
        elif normalized == f"{prefix}O1":
            normalized = f"{prefix}01"

    if normalized.startswith(('BF_MSO', 'BFMSO')):
        normalized = normalized.replace('MSO', 'MS0')
    if normalized.startswith(('BF_MPO', 'BFMPO')):
        normalized = normalized.replace('MPO', 'MP0')
    if re.match(r'^RO\d+', normalized):
        normalized = 'R0' + normalized[2:]

    return normalized

def is_rack_location(location_code):
    """
    Sprawdza czy kod jest lokalizacją na regale.
    Zwykle kody regałów mają format R + cyfry (np. R010101).
    """
    if not location_code:
        return False
    normalized = str(location_code).strip().upper()
    return re.match(r'^R\d+$', normalized) is not None

def is_rack_level_1(location_code):
    """
    Sprawdza czy kod lokalizacji to poziom 1 na regale wysokiego składowania (np. R010101, R-01-01-01).
    Format regału: R + regał (2 cyfry) + kolumna/gniazdo (2 cyfry) + poziom (2 cyfry).
    Poziom 1 kończy się na '01'.
    """
    if not location_code:
        return False
    norm = normalize_warehouse_location(location_code)
    clean = re.sub(r'[^A-Z0-9]', '', str(norm or location_code).strip().upper())
    if clean.isdigit() and len(clean) == 6:
        clean = 'R' + clean
    m = re.match(r'^R(\d{2})(\d{2})(\d{2})$', clean)
    if m:
        return m.group(3) == '01'
    return False

def check_rack_location_availability(location_code, current_nr_palety=None, product_name=None):
    """
    Sprawdza czy miejsce paletowe na regale jest wolne (nie zajęte przez inną paletę).
    Zwraca (is_valid, error_msg).
    Dla regału półkowego R09 (R090101 - R090406) dozwolone jest przechowywanie wielu asortymentów / palet na jednej półce!
    Dla surowca Hydro dozwolone jest piętrowanie na poziomie 1 (np. R010101) - do 2 palet Hydro na jednym miejscu.
    """
    if not location_code or not is_rack_location(location_code):
        return True, None
        
    normalized = str(location_code).strip().upper()
    if normalized.startswith('R09'):
        return True, None
        
    from app.core.database import get_db_connection
    conn = get_db_connection()
    try:
        cur = conn.cursor(dictionary=True)

        # Jeśli nie podano nazwy produktu, ale podano nr_palety, sprawdź czy to surowiec Hydro
        if not product_name and current_nr_palety:
            try:
                for t_name in ['magazyn_surowce', 'magazyn_agro_surowce']:
                    cur.execute(f"SELECT nazwa FROM {t_name} WHERE nr_palety = %s LIMIT 1", (str(current_nr_palety).strip(),))
                    r_p = cur.fetchone()
                    if r_p and r_p.get('nazwa'):
                        product_name = r_p['nazwa']
                        break
            except Exception:
                pass

        is_lvl1 = is_rack_level_1(normalized)
        is_target_hydro = str(product_name or '').strip().lower() == 'hydro'

        tables = [
            ('magazyn_surowce', 'stan_magazynowy', 'nazwa'),
            ('magazyn_agro_surowce', 'stan_magazynowy', 'nazwa'),
            ('magazyn_opakowania', 'stan_magazynowy', 'nazwa'),
            ('magazyn_agro_opakowania', 'stan_magazynowy', 'nazwa'),
            ('magazyn_dodatki', 'stan_magazynowy', 'nazwa'),
            ('magazyn_palety', 'waga_netto', 'produkt'),
            ('magazyn_palety_agro', 'waga_netto', 'produkt')
        ]
        
        existing_pallets = []
        for t, qty_col, name_col in tables:
            try:
                query = f"SELECT nr_palety, {name_col} as product_name FROM {t} WHERE lokalizacja = %s AND {qty_col} > 0"
                params = [normalized]
                if current_nr_palety:
                    query += " AND (nr_palety IS NULL OR nr_palety != %s)"
                    params.append(str(current_nr_palety).strip())
                    
                cur.execute(query, tuple(params))
                rows = cur.fetchall()
                if rows:
                    existing_pallets.extend(rows)
            except Exception:
                pass

        if not existing_pallets:
            return True, None

        # Gniazdo ma już co najmniej 1 paletę
        if is_lvl1 and is_target_hydro:
            # Sprawdź czy wszystkie obecne palety to również Hydro
            all_existing_are_hydro = all(
                str(p.get('product_name') or '').strip().lower() == 'hydro'
                for p in existing_pallets
            )
            if not all_existing_are_hydro:
                first_other = next((p for p in existing_pallets if str(p.get('product_name') or '').strip().lower() != 'hydro'), existing_pallets[0])
                other_name = first_other.get('product_name') or 'inny towar'
                other_nr = first_other.get('nr_palety') or ''
                return False, f"Lokalizacja {normalized} jest zajęta przez {other_name} ({other_nr}). Piętrowanie Hydro jest możliwe tylko na innej palecie Hydro."
            
            if len(existing_pallets) >= 2:
                nr_list = ", ".join(str(p.get('nr_palety') or 'brak') for p in existing_pallets)
                return False, f"Lokalizacja {normalized} osiągnęła maksymalną pojemność (2 palety Hydro: {nr_list})!"

            # Dopuszczamy 2. paletę Hydro na poziomie 1
            return True, None

        # W każdym innym wypadku regał jest zajęty
        occupied_p = existing_pallets[0]
        occupied_name = occupied_p.get('product_name') or 'towar'
        occupied_nr = occupied_p.get('nr_palety') or ''
        if is_lvl1:
            return False, f"Lokalizacja {normalized} jest zajęta przez paletę {occupied_nr} ({occupied_name}). Piętrowanie na poziomie 1 dozwolone jest wyłącznie dla surowca Hydro."
        else:
            return False, f"Lokalizacja {normalized} jest zajęta przez paletę {occupied_nr} ({occupied_name})!"

    except Exception as e:
        return False, f"Błąd podczas sprawdzania dostępności lokalizacji: {e}"
    finally:
        conn.close()


def is_osip_location(location_code):
    """Sprawdza czy lokalizacja należy do Magazynu OSIP (A01..A99, BFOS, OS01..OS77, OSIP, W_TRANZYCIE_OSIP)."""
    if not location_code:
        return False
    loc = str(location_code).strip().upper()
    if loc in ('OSIP', 'BFOS', 'W_TRANZYCIE_OSIP'):
        return True
    if re.match(r'^A\d{2}$', loc) or re.match(r'^OS\d{2}$', loc):
        return True
    return False


def is_centrala_location(location_code):
    """Sprawdza czy lokalizacja należy do Centrali (MS01, MP01, MGW*, Regały R*, itp.)."""
    if not location_code:
        return False
    loc = str(location_code).strip().upper()
    if loc in ('EXPEDITION', 'ARCHIWUM', 'W_TRANZYCIE_OSIP', 'OCZEKUJĄCE', 'OCZEKUJE'):
        return False
    return not is_osip_location(loc)


def validate_centrala_osip_move(source_location, target_location, pallet_id=None, nr_palety=None):
    """
    Sprawdza czy ruch palety nie przekracza granicy Centrala <-> OSIP bez aktywnego transferu.
    Zwraca (is_valid: bool, error_msg: str | None).
    """
    if not source_location or not target_location:
        return True, None
        
    src_osip = is_osip_location(source_location)
    tgt_osip = is_osip_location(target_location)
    
    # Ruch wewnątrz Centrali lub wewnątrz OSIP jest dozwolony
    if src_osip == tgt_osip:
        return True, None
        
    # Wyjątki dla statusów specjalnych / tranzytowych
    tgt_upper = str(target_location).strip().upper()
    src_upper = str(source_location).strip().upper()
    if tgt_upper in ('EXPEDITION', 'ARCHIWUM') or src_upper in ('EXPEDITION', 'ARCHIWUM'):
        return True, None
    if tgt_upper == 'W_TRANZYCIE_OSIP' or src_upper == 'W_TRANZYCIE_OSIP':
        return True, None

    # Sprawdzenie czy paleta jest w aktywnym zleceniu transferu (PLANNED / IN_TRANSIT)
    from app.core.database import get_db_connection
    conn = get_db_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT t.id, t.transfer_code, t.status, ti.status as item_status
            FROM osip_transfers t
            JOIN osip_transfer_items ti ON t.id = ti.transfer_id
            WHERE t.status IN ('PLANNED', 'IN_TRANSIT')
              AND ti.status != 'RECEIVED'
              AND (ti.pallet_id = %s OR (ti.nr_palety IS NOT NULL AND ti.nr_palety != '' AND UPPER(ti.nr_palety) = UPPER(%s)))
            LIMIT 1
        """, (pallet_id, str(nr_palety or '').strip()))
        row = cur.fetchone()
        if row:
            return True, None
    except Exception as e:
        print(f"Błąd sprawdzania transferu OSIP: {e}")
    finally:
        conn.close()

    direction = "z Centrali do Magazynu OSIP" if tgt_osip else "z Magazynu OSIP do Centrali"
    return False, (
        f"BŁĄD: Bezpośrednie przenoszenie palet {direction} ({source_location} -> {target_location}) "
        "jest zablokowane! Przenoszenie między Centralą a OSIP jest możliwe wyłącznie poprzez Zlecenie Transferu OSIP."
    )

