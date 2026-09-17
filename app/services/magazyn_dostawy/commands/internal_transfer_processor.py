import json
from typing import Tuple, List, Dict, Any, Set
from app.db import get_table_name
from app.services.magazyn_dostawy.commands.delivery_order_validator import norm_loc, is_route_conflict


class InternalTransferProcessor:
    """Processes internal warehouse transfer orders (MM) and pallet reservations strictly against active database state."""

    @classmethod
    def _find_active_pallet_by_sscc(cls, cursor, p_nr: str, linia: str) -> Tuple[dict | None, str | None]:
        """Strictly searches the database for an active pallet by its SSCC/nr_palety with positive stock."""
        clean_nr = str(p_nr).strip().upper()
        
        # Check all possible lines and warehouse tables
        for l_code in [linia, 'PSD', 'AGRO']:
            table_sur = get_table_name('magazyn_surowce', l_code)
            table_opk = get_table_name('magazyn_opakowania', l_code)
            table_got = get_table_name('magazyn_palety', l_code)

            for tbl, t_type in [(table_sur, 'surowiec'), (table_opk, 'opakowanie')]:
                cursor.execute(
                    f"SELECT id, nr_palety, stan_magazynowy, lokalizacja, nazwa FROM {tbl} "
                    f"WHERE UPPER(COALESCE(nr_palety, '')) = %s AND stan_magazynowy > 0 LIMIT 1",
                    (clean_nr,)
                )
                res = cursor.fetchone()
                if res:
                    return res, t_type

            cursor.execute(
                f"SELECT id, nr_palety, stan_magazynowy, lokalizacja, nazwa FROM magazyn_dodatki "
                f"WHERE UPPER(COALESCE(nr_palety, '')) = %s AND stan_magazynowy > 0 LIMIT 1",
                (clean_nr,)
            )
            res = cursor.fetchone()
            if res:
                return res, 'dodatek'

            cursor.execute(
                f"SELECT id, nr_palety, waga_netto AS stan_magazynowy, COALESCE(lokalizacja, 'MGW01') AS lokalizacja, "
                f"COALESCE(produkt, nazwa) AS nazwa FROM {table_got} "
                f"WHERE UPPER(COALESCE(nr_palety, '')) = %s AND waga_netto > 0 LIMIT 1",
                (clean_nr,)
            )
            res = cursor.fetchone()
            if res:
                return res, 'wyrob_gotowy'

        return None, None

    @classmethod
    def _is_pallet_archived_or_zero(cls, cursor, p_nr: str, p_id: Any = None) -> Tuple[bool, str]:
        """Checks if a pallet has been archived or consumed to 0 kg in the database."""
        clean_nr = str(p_nr or '').strip().upper()
        if clean_nr:
            cursor.execute(
                "SELECT id, original_id, nr_palety, waga_ostatnia, lokalizacja_ostatnia, data_archiwizacji "
                "FROM magazyn_archiwum WHERE UPPER(COALESCE(nr_palety, '')) = %s "
                "ORDER BY data_archiwizacji DESC LIMIT 1",
                (clean_nr,)
            )
            arch = cursor.fetchone()
            if arch:
                dt_str = arch['data_archiwizacji'].strftime('%Y-%m-%d %H:%M') if arch.get('data_archiwizacji') else ''
                return True, f"Paleta {clean_nr} została zarchiwizowana / zużyta do 0 kg ({dt_str}, lok: {arch.get('lokalizacja_ostatnia')})."

        if p_id:
            try:
                cursor.execute(
                    "SELECT id, original_id, nr_palety, data_archiwizacji FROM magazyn_archiwum WHERE original_id = %s OR id = %s LIMIT 1",
                    (p_id, p_id)
                )
                arch = cursor.fetchone()
                if arch:
                    return True, f"Paleta #{p_id} została już zużyta do 0 kg i zarchiwizowana."
            except Exception:
                pass

        return False, ""

    @classmethod
    def process_transfer(
        cls, cursor, items: List[Dict[str, Any]], linia: str, dostawa_id: str,
        lokalizacja_do: str, order_ref: str, global_skip_lookup: bool, login: str
    ) -> Tuple[bool, Any]:
        # Collect reserved items from other pending transfers
        cursor.execute(
            "SELECT id, items FROM magazyn_dostawy WHERE status = 'OCZEKUJE' AND id <> %s",
            (dostawa_id,)
        )
        other_pending = cursor.fetchall()
        reserved_other_nrs: Set[str] = set()
        reserved_other_ids: Set[str] = set()

        for pending in other_pending:
            raw_items = pending.get('items')
            if not raw_items:
                continue
            try:
                pending_items = json.loads(raw_items) if isinstance(raw_items, str) else raw_items
            except Exception:
                continue
            if not isinstance(pending_items, list):
                continue

            for pit in pending_items:
                if not isinstance(pit, dict) or pit.get('accepted') or pit.get('rejected'):
                    continue

                pit_nr = norm_loc(pit.get('sourcePalletNo') or pit.get('nr_palety'))
                if pit_nr:
                    reserved_other_nrs.add(pit_nr)

                pit_id = pit.get('sourcePalletId')
                pit_type = str(pit.get('scannedType') or pit.get('type') or '').strip().lower()
                if pit_id not in (None, '') and pit_type:
                    reserved_other_ids.add(f"{pit_type}:{pit_id}")

        updated_items: List[Dict[str, Any]] = []
        used_request_nrs: Set[str] = set()
        used_request_ids: Set[str] = set()

        for idx, item in enumerate(items):
            if item.get('id') in (None, ''):
                item['id'] = f"item_{idx}_{int(__import__('datetime').datetime.now().timestamp())}"

            if item.get('accepted'):
                updated_items.append(item)
                continue

            source_spot = norm_loc(item.get('sourceSpot'))
            p_name = item.get('productName')
            p_id = item.get('sourcePalletId')
            p_nr = item.get('sourcePalletNo') or item.get('nr_palety')
            p_nr_norm = norm_loc(p_nr)

            # Strict check: check if pallet is already in archive or consumed to 0 kg
            is_arch, arch_msg = cls._is_pallet_archived_or_zero(cursor, p_nr, p_id)
            if is_arch:
                return False, f"BŁĄD BAZY DANYCH: {arch_msg} Nie można dodać jej do zlecenia przesunięcia!"

            if p_nr_norm:
                if p_nr_norm in used_request_nrs:
                    return False, f"Paleta {p_nr_norm} została dodana wielokrotnie w tym samym zleceniu."
                if p_nr_norm in reserved_other_nrs:
                    return False, f"Paleta {p_nr_norm} jest już zarezerwowana w innym oczekującym przesunięciu."
                used_request_nrs.add(p_nr_norm)

            # Strict lookup by SSCC/nr_palety in DB
            p_res = None
            p_type = None

            if p_nr:
                p_res, p_type = cls._find_active_pallet_by_sscc(cursor, p_nr, linia)

            # Fallback to ID lookup only if SSCC not provided
            if not p_res and p_id and not p_nr:
                for l_code in [linia, 'PSD', 'AGRO']:
                    for tbl, t_type in [
                        (get_table_name('magazyn_surowce', l_code), 'surowiec'),
                        (get_table_name('magazyn_opakowania', l_code), 'opakowanie')
                    ]:
                        cursor.execute(
                            f"SELECT id, nr_palety, stan_magazynowy, lokalizacja, nazwa FROM {tbl} "
                            f"WHERE id = %s AND stan_magazynowy > 0 LIMIT 1",
                            (p_id,)
                        )
                        p_res = cursor.fetchone()
                        if p_res:
                            p_type = t_type
                            break
                    if p_res:
                        break

            if not p_res:
                return False, f"Paleta {p_nr or p_name or p_id} nie istnieje w bazie lub jej stan magazynowy wynosi 0 kg!"

            # Verify actual physical location from DB
            db_actual_spot = norm_loc(p_res.get('lokalizacja'))
            if not source_spot:
                source_spot = db_actual_spot

            if source_spot and is_route_conflict(source_spot, lokalizacja_do):
                return False, f"Operacja niemożliwa: paleta {p_nr} ma tę samą lokalizację źródłową i docelową ({lokalizacja_do})."

            actual_id = p_res['id']
            actual_nr = p_res.get('nr_palety') or p_nr
            actual_nr_norm = norm_loc(actual_nr)

            resolved_id_key = f"{p_type}:{actual_id}"
            if resolved_id_key in used_request_ids:
                return False, f"Paleta {actual_nr_norm or actual_id} została dodana wielokrotnie w tym samym zleceniu."
            if resolved_id_key in reserved_other_ids:
                return False, f"Paleta {actual_nr_norm or actual_id} jest już zarezerwowana w innym oczekującym przesunięciu."
            used_request_ids.add(resolved_id_key)

            item['originalSpot'] = db_actual_spot or source_spot
            item['sourceSpot'] = db_actual_spot or source_spot
            item['sourcePalletId'] = actual_id
            item['scannedType'] = p_type
            item['sourcePalletNo'] = actual_nr
            item['nr_palety'] = actual_nr
            item['accepted'] = False

            cursor.execute(
                "SELECT id FROM palety_historia WHERE (paleta_id = %s OR nr_palety = %s) AND komentarz LIKE %s LIMIT 1",
                (actual_id, actual_nr or '-', f"%{order_ref}%")
            )
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO palety_historia (paleta_id, nr_palety, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login) "
                    "VALUES (%s, %s, %s, %s, 'WYDANIE_PRZESUNIECIE', %s, %s, %s, %s)",
                    (actual_id, actual_nr, linia, p_type, item['sourceSpot'], lokalizacja_do, f"Zlecenie przesunięcia {order_ref}: {item['sourceSpot']} -> {lokalizacja_do}", login)
                )

            updated_items.append(item)

        return True, updated_items
