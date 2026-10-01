"""
Walidacja lokalizacji magazynowych.

Zapobiega używaniu kodów zbiorników produkcyjnych (BB*, MZ*, KO*) 
jako lokalizacji w magazynie surowców, opakowań i wyrobów gotowych.
"""
import re

# Wzorce kodów zbiorników produkcyjnych (NIE mogą być lokalizacjami magazynowymi!)
# Canonical sets of production stations
VALID_BB_TANK_CODES = [f"BB{i:02d}" for i in range(1, 25) if i not in (7, 8, 9, 10, 23, 24)]
VALID_MZ_TANK_CODES = ["MZ07", "MZ08", "MZ09", "MZ10", "MZ23", "MZ24"]
VALID_KO_TANK_CODES = [f"KO{i:02d}" for i in range(1, 41)]
VALID_CZ_TANK_CODES = [f"CZ{i:02d}" for i in range(1, 100)]
VALID_WZ_TANK_CODES = ["WZ04"]
VALID_PRODUCTION_TANK_CODES = set(VALID_BB_TANK_CODES + VALID_MZ_TANK_CODES + VALID_KO_TANK_CODES + VALID_CZ_TANK_CODES + VALID_WZ_TANK_CODES)

DELETED_STATION_CODES = {
    'BB07', 'BB08', 'BB09', 'BB10', 'BB23', 'BB24',
    'BB7', 'BB8', 'BB9', 'BB10', 'BB23', 'BB24',
    'MZ01', 'MZ02', 'MZ03', 'MZ04', 'MZ05', 'MZ06',
    'MZ1', 'MZ2', 'MZ3', 'MZ4', 'MZ5', 'MZ6',
    'MZ11', 'MZ12', 'MZ13', 'MZ14', 'MZ15', 'MZ16', 'MZ17', 'MZ18', 'MZ19', 'MZ20', 'MZ21', 'MZ22',
    'MZ05-01', 'MZ06-01'
}

# Wzorce kodów zbiorników produkcyjnych (NIE mogą być lokalizacjami magazynowymi!)
PRODUCTION_TANK_PATTERNS = [
    r'^BB\d+$',
    r'^MZ\d+$',
    r'^KO\d+$',
    r'^CZ\d+$',
    r'^WZ\d+$',
    r'^PSD\d*$',
    r'^MIX\d*$',
]


def normalize_production_tank_code(location_code):
    """Normalize station/tank code to standard 2-digit format (e.g. BB2 -> BB02, MZ7 -> MZ07, KO1 -> KO01)."""
    if not location_code:
        return ""
    val = str(location_code).strip().upper()
    val = re.sub(r'[\s\-_]+', '', val)
    m = re.match(r'^([A-Z]+)(\d+)$', val)
    if m:
        prefix, num = m.group(1), int(m.group(2))
        if prefix in ('BB', 'MZ', 'KO', 'CZ', 'WZ'):
            return f"{prefix}{num:02d}"
    return val


def is_deleted_station_code(location_code):
    """Sprawdza czy kod to usunięta ze stanowisk stacja BB lub MZ."""
    if not location_code:
        return False
    normalized = normalize_production_tank_code(location_code)
    raw_norm = str(location_code).strip().upper()
    return normalized in DELETED_STATION_CODES or raw_norm in DELETED_STATION_CODES


def is_valid_production_tank_code(location_code):
    """Sprawdza czy kod to poprawna, istniejąca stacja produkcyjna."""
    if not location_code:
        return False
    norm = normalize_production_tank_code(location_code)
    return norm in VALID_PRODUCTION_TANK_CODES


def validate_production_tank(location_code):
    """Validate production tank code, returning (is_valid, normalized_code, error_message)."""
    if not location_code or not str(location_code).strip():
        return False, "", "⚠️ Brak kodu stacji/zbiornika!"
    
    norm = normalize_production_tank_code(location_code)
    if is_deleted_station_code(location_code) or is_deleted_station_code(norm):
        return False, norm, f"❌ Stacja/zbiornik {norm} została wycofana/usunięta z systemu! Dozwolone: BB01-BB06, BB11-BB22, MZ07-MZ10, MZ23-MZ24, KO01-KO40."
    
    if norm not in VALID_PRODUCTION_TANK_CODES:
        return False, norm, f"❌ Stacja/zbiornik '{norm}' nie istnieje! Dozwolone: BB01-BB06, BB11-BB22, MZ07-MZ10, MZ23-MZ24, KO01-KO40, CZ01-CZ99, WZ04."
    
    return True, norm, None


def is_production_tank_code(location_code):
    """
    Sprawdza czy podany kod to kod zbiornika produkcyjnego.
    Lokalizacje buforowe i magazynowe (BF_MS01, BF_MP01, BFOS itp.) ZAWSZE zwracają False.
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
        
    norm_tank = normalize_production_tank_code(normalized)
    if norm_tank in VALID_PRODUCTION_TANK_CODES or norm_tank in DELETED_STATION_CODES:
        return True

    for pattern in PRODUCTION_TANK_PATTERNS:
        if re.match(pattern, normalized) or re.match(pattern, norm_tank):
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
    if clean_norm.startswith(('BFMS', 'BFMP', 'BFOS', 'BF', 'MS', 'MP', 'MOP', 'MDM', 'MGW', 'MDO', 'MD', 'PSD', 'RAMPA', 'MIX', 'OSIP', 'R0', 'LP')):
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
    """
    if not location_code or str(location_code).strip() == '':
        if allow_empty:
            return True, None
        else:
            return False, "Lokalizacja jest wymagana"
    
    normalized = str(location_code).strip().upper()
    clean_norm = normalized.replace('_', '').replace('-', '').replace(' ', '')
    
    # Wyjątek: Magazyny, bufory (BFMS01, BFMP01, BFOS, BF_*), stacje maszyn (LP01, MASZYNA) są dozwolonymi lokalizacjami magazynowymi
    if clean_norm.startswith(('BFMS', 'BFMP', 'BFOS', 'BF', 'MS', 'MP', 'MOP', 'MDM', 'MGW', 'MDO', 'MD', 'PSD', 'RAMPA', 'MIX', 'OSIP', 'R0', 'LP')) or clean_norm == 'MASZYNA':
        return True, None

    norm_tank = normalize_production_tank_code(normalized)

    if is_deleted_station_code(normalized) or is_deleted_station_code(norm_tank):
        return False, (
            f"Lokalizacja {normalized} to wycofana/usunięta stacja produkcyjna. "
            "Użyj kodów regałów magazynowych (np. R021002, R030601)"
        )

    if is_production_tank_code(normalized) or is_production_tank_code(norm_tank):
        return False, (
            f"{normalized} to kod stacji/zbiornika produkcyjnego. "
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


def is_mp01_warehouse_location(location_code: str) -> bool:
    """
    Sprawdza czy lokalizacja należy do Magazynu MP01:
    - MP01, BF_MP01, BFMP01
    - Wszystkie regały wysokiego składowania i półkowe: R01..R99 (np. R010101, R020302 itp.)
    """
    if not location_code:
        return False
    loc = str(location_code).strip().upper()
    loc_clean = loc.replace(' ', '').replace('-', '').replace('_', '')
    if loc_clean in ('MP01', 'BFMP01'):
        return True
    if loc.startswith(('MP01', 'BF_MP01', 'BFMP01')):
        return True
    if re.match(r'^R\d{2}', loc) or is_rack_location(loc):
        return True
    return False


def is_ms01_warehouse_location(location_code: str) -> bool:
    """
    Sprawdza czy lokalizacja należy do Magazynu MS01:
    - MS01, BF_MS01, BFMS01
    - PSD, PSD01
    """
    if not location_code:
        return False
    loc = str(location_code).strip().upper()
    loc_clean = loc.replace(' ', '').replace('-', '').replace('_', '')
    if loc_clean in ('MS01', 'BFMS01', 'PSD', 'PSD01'):
        return True
    if loc in ('MS01', 'BF_MS01', 'BFMS01', 'PSD', 'PSD01'):
        return True
    if loc.startswith(('BF_MS01', 'BFMS01', 'MS01')):
        return True
    return False


def get_warehouse_zone(location_code: str) -> str:
    """Zwraca strefę magazynu: 'MP01', 'MS01', 'OSIP', 'SPECIAL' lub 'OTHER'."""
    if not location_code:
        return 'OTHER'
    loc = str(location_code).strip().upper()
    if loc in ('EXPEDITION', 'ARCHIWUM', 'W_TRANZYCIE_OSIP', 'OCZEKUJĄCE', 'OCZEKUJACE', 'OCZEKUJE', 'RAMPA', 'DOSTAWA'):
        return 'SPECIAL'
    if is_osip_location(loc):
        return 'OSIP'
    if is_mp01_warehouse_location(loc):
        return 'MP01'
    if is_ms01_warehouse_location(loc):
        return 'MS01'
    return 'OTHER'


def validate_inter_warehouse_move(source_location: str, target_location: str, pallet_id=None, nr_palety=None) -> tuple[bool, str | None]:
    """
    Weryfikuje regułę rozdziału magazynów:
    1. Magazyn MP01 (MP01, BF_MP01 oraz regały i lokalizacje R01..R99) to JEDEN magazyn.
    2. Magazyn MS01 (MS01, bufor BF_MS01, PSD, PSD01) to DRUGI magazyn.
    3. Przesunięcia między Magazynem MS01 a Magazynem MP01 mogą odbywać się
       TYLKO I WYŁĄCZNIE poprzez formalne przesunięcia magazynowe (magazyn_dostawy).
    Bezpośrednie przenoszenie palet bez aktywnego zlecenia przesunięcia jest blokowane.
    """
    if not source_location or not target_location:
        return True, None

    src_zone = get_warehouse_zone(source_location)
    tgt_zone = get_warehouse_zone(target_location)

    # Ruch wewnątrz tego samego magazynu jest dozwolony (np. MP01 -> R010101, lub MS01 -> BF_MS01)
    if src_zone == tgt_zone:
        return True, None

    # Statusy specjalne / tranzytowe
    if src_zone == 'SPECIAL' or tgt_zone == 'SPECIAL':
        return True, None

    # Granica Centrala <-> OSIP
    if src_zone == 'OSIP' or tgt_zone == 'OSIP':
        return validate_centrala_osip_move(source_location, target_location, pallet_id=pallet_id, nr_palety=nr_palety)

    # Granica MS01 <-> MP01 (MS01, BF_MS01, PSD, PSD01 <-> MP01, BF_MP01, regały R01..R99)
    if (src_zone == 'MS01' and tgt_zone == 'MP01') or (src_zone == 'MP01' and tgt_zone == 'MS01'):
        from app.services.magazyn_dostawy.delivery_queries import DeliveryQueries
        in_transfer, trf_ref = DeliveryQueries.is_pallet_in_pending_transfer(pallet_id=pallet_id, nr_palety=nr_palety)
        if in_transfer:
            return True, None

        if src_zone == 'MS01' and tgt_zone == 'MP01':
            dir_str = f"z Magazynu MS01 ({source_location}) do Magazynu MP01 / regałów ({target_location})"
        else:
            dir_str = f"z Magazynu MP01 / regałów ({source_location}) do Magazynu MS01 ({target_location})"

        return False, (
            f"BŁĄD: Bezpośrednie przesunięcie palety {dir_str} jest zablokowane! "
            f"Magazyn MP01 (wraz z regałami) oraz Magazyn MS01 (MS01, bufor BF_MS01, PSD, PSD01) "
            f"to odrębne magazyny. Przesunięcie między nimi wymaga utworzenia i zrealizowania "
            f"systemowego Przesunięcia Magazynowego."
        )

    return True, None


def validate_reception_warehouse_destination(source_location: str, planned_destination: str, putaway_location: str, is_external: bool = False) -> tuple[bool, str | None]:
    """
    Waliduje odstawienie palety podczas przyjęcia/realizacji zlecenia (przyjęcie surowców / dostawy / transferu).
    Gwarantuje, że paleta pochodząca z Magazynu MS01 lub zadeklarowana do Magazynu MS01
    nie zostanie odstawiona do Magazynu MP01 (na regały R...) poza zatwierdzonym przesunięciem magazynowym.
    """
    if not putaway_location:
        return True, None

    put_zone = get_warehouse_zone(putaway_location)
    src_zone = get_warehouse_zone(source_location)
    plan_zone = get_warehouse_zone(planned_destination)

    # 1. Towar z Magazynu MS01 trafiający do Magazynu MP01 (na regały)
    if src_zone == 'MS01' and put_zone == 'MP01':
        # Dozwolone wyłącznie gdy samo zlecenie przesunięcia zostało wystawione z celem w Magazynie MP01
        if plan_zone != 'MP01':
            return False, (
                f"BŁĄD: Paleta pochodzi z Magazynu MS01 ({source_location}), a to zlecenie "
                f"nie jest przesunięciem do Magazynu MP01 (cel w zleceniu: {planned_destination or 'MS01'}). "
                f"Odstawienie do Magazynu MP01 / na regały ({putaway_location}) jest zablokowane! "
                f"Wymagane jest formalne zlecenie przesunięcia magazynowego do Magazynu MP01."
            )

    # 2. Towar z Magazynu MP01 trafiający do Magazynu MS01
    if src_zone == 'MP01' and put_zone == 'MS01':
        if plan_zone != 'MS01':
            return False, (
                f"BŁĄD: Paleta pochodzi z Magazynu MP01 ({source_location}), a to zlecenie "
                f"nie jest przesunięciem do Magazynu MS01 (cel w zleceniu: {planned_destination or 'MP01'}). "
                f"Odstawienie do Magazynu MS01 ({putaway_location}) jest zablokowane!"
            )

    # 3. Dostawa zewnętrzna zadeklarowana do Magazynu MS01 nie może być bezpośrednio odłożona na MP01 / regały
    if is_external and plan_zone == 'MS01' and put_zone == 'MP01':
        return False, (
            f"BŁĄD: Dostawa została zadeklarowana do Magazynu MS01 ({planned_destination}). "
            f"Bezpośrednie przyjęcie na regały / do Magazynu MP01 ({putaway_location}) jest zablokowane! "
            f"Przyjmij towar do Magazynu MS01, a następnie wykonaj formalne przesunięcie magazynowe do MP01."
        )

    # 4. Dostawa zewnętrzna zadeklarowana do Magazynu MP01 nie może być odłożona na MS01
    if is_external and plan_zone == 'MP01' and put_zone == 'MS01':
        return False, (
            f"BŁĄD: Dostawa została zadeklarowana do Magazynu MP01 ({planned_destination}). "
            f"Bezpośrednie przyjęcie do Magazynu MS01 ({putaway_location}) jest zablokowane!"
        )

    return True, None

