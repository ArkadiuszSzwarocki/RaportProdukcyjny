from typing import Tuple, List, Dict, Any
from app.db import get_db_connection, get_table_name
from app.services.magazyn_dostawy.commands.delivery_order_validator import norm_loc


class DraftPalletSyncService:
    """Synchronizes draft items strictly with current warehouse DB state and purges zero/archived pallets."""

    @classmethod
    def _is_archived_or_consumed(cls, cursor, sscc: str) -> bool:
        """Checks if pallet is in magazyn_archiwum."""
        clean_sscc = str(sscc or '').strip().upper()
        if not clean_sscc:
            return False
        cursor.execute(
            "SELECT id FROM magazyn_archiwum WHERE UPPER(COALESCE(nr_palety, '')) = %s LIMIT 1",
            (clean_sscc,)
        )
        return cursor.fetchone() is not None

    @classmethod
    def sync_draft_pallets(cls, items: List[Dict[str, Any]], linia: str = 'AGRO', user_login: str = 'system') -> Tuple[bool, Any]:
        if not items:
            return True, {"items": [], "changes": []}

        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            updated_items = []
            changes = []

            for it in items:
                item_copy = dict(it)
                pnr = it.get('sourcePalletNo') or it.get('nr_palety')
                clean_sscc = str(pnr or '').strip().upper()

                # If SSCC is archived, remove from draft
                if clean_sscc and cls._is_archived_or_consumed(cursor, clean_sscc):
                    changes.append({
                        'nr_palety': clean_sscc,
                        'removed': True,
                        'reason': 'Paleta została zarchiwizowana / zużyta do 0 kg w bazie danych.'
                    })
                    continue

                curr_row = None
                found_tbl = None

                # Strict search by SSCC across warehouse tables in all lines
                for l_code in [linia, 'AGRO' if str(linia).upper() == 'PSD' else 'PSD']:
                    for tbl, qty_field in [
                        (get_table_name('magazyn_surowce', l_code), 'stan_magazynowy'),
                        (get_table_name('magazyn_opakowania', l_code), 'stan_magazynowy'),
                        ('magazyn_dodatki', 'stan_magazynowy'),
                        (get_table_name('magazyn_palety', l_code), 'waga_netto')
                    ]:
                        if clean_sscc:
                            cursor.execute(
                                f"SELECT * FROM {tbl} WHERE UPPER(COALESCE(nr_palety, '')) = %s AND {qty_field} > 0 LIMIT 1",
                                (clean_sscc,)
                            )
                            curr_row = cursor.fetchone()
                            if curr_row:
                                found_tbl = tbl
                                break
                    if curr_row:
                        break

                if not curr_row and clean_sscc:
                    # Pallet has 0 kg in DB or does not exist
                    changes.append({
                        'nr_palety': clean_sscc,
                        'removed': True,
                        'reason': 'Paleta nie istnieje w bazie lub ma 0 kg stanu magazynowego.'
                    })
                    continue

                if curr_row:
                    old_loc = norm_loc(item_copy.get('sourceSpot') or item_copy.get('lokalizacja_z'))
                    new_loc = norm_loc(curr_row.get('lokalizacja'))
                    if new_loc and old_loc != new_loc:
                        changes.append({
                            'nr_palety': clean_sscc,
                            'old_location': old_loc,
                            'new_location': new_loc
                        })
                        item_copy['sourceSpot'] = new_loc
                        item_copy['originalSpot'] = new_loc
                        item_copy['lokalizacja_z'] = new_loc

                    qty_col = 'waga_netto' if 'magazyn_palety' in (found_tbl or '') else 'stan_magazynowy'
                    if qty_col in curr_row and curr_row[qty_col] is not None:
                        item_copy['quantity'] = float(curr_row[qty_col])
                        item_copy['ilosc'] = float(curr_row[qty_col])

                    # Lock pallet in DB
                    if found_tbl and curr_row.get('id'):
                        try:
                            cursor.execute(f"UPDATE {found_tbl} SET is_blocked = 1 WHERE id = %s", (curr_row['id'],))
                        except Exception:
                            pass

                updated_items.append(item_copy)

            conn.commit()
            return True, {"items": updated_items, "changes": changes}
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()
