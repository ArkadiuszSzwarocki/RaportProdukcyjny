from datetime import datetime
import json
import uuid
from flask import current_app, request, session

from app.core.audit import audit_log
from app.db import get_db_connection, get_table_name
from app.utils.pallet_id import generate_pallet_id
from app.utils.validation import require_field
from app.utils.pallet_label import lookup_raw_material_details_by_sscc, _format_date


class PalletConfirmationService:
    """Service handling pallet confirmation by warehouse roles, weight verification, reclassification, and storage."""

    @staticmethod
    def _handle_czyszczenie_reclassification(cursor, conn, paleta_id, plan_id, linia, nr_palety, table_pal,
                                            netto_val, stored_netto, data_produkcji, user_login, lokalizacja):
        """Handle reclassifying cleaning products to raw material with dedicated delivery entry."""
        table_plan = get_table_name('plan_produkcji', linia)
        mother_sscc = None
        try:
            cursor.execute(
                f"SELECT skan_sscc FROM {table_plan} WHERE (id = %s OR id = (SELECT COALESCE(zasyp_id, -1) FROM {table_plan} WHERE id = %s)) AND skan_sscc IS NOT NULL AND TRIM(skan_sscc) <> '' LIMIT 1",
                (plan_id, plan_id)
            )
            sscc_row = cursor.fetchone()
            if sscc_row and sscc_row[0]:
                mother_sscc = str(sscc_row[0]).strip()
        except Exception as sscc_err:
            current_app.logger.warning('Failed to find mother skan_sscc for plan %s: %s', plan_id, sscc_err)

        child_sscc = nr_palety
        if not child_sscc or child_sscc == mother_sscc:
            child_sscc = generate_pallet_id(linia, 'surowiec')
            cursor.execute(f"UPDATE {table_pal} SET nr_palety=%s WHERE id=%s", (child_sscc, paleta_id))
            nr_palety = child_sscc

        orig_meta = lookup_raw_material_details_by_sscc(cursor, mother_sscc or nr_palety)
        orig_partia = str(orig_meta.get('nr_partii') or (request.form.get('nr_partii') if request else '') or '').strip()
        orig_data_prod = _format_date(orig_meta.get('data_produkcji')) or data_produkcji
        orig_data_przyd = _format_date(orig_meta.get('data_przydatnosci')) or (request.form.get('data_przydatnosci') if request else '') or ''

        dostawa_id = str(uuid.uuid4())
        item_name = "Mąka mix do Lnu"
        final_amount = float(netto_val if netto_val and netto_val > 0 else stored_netto or 0)
        items = [{
            "id": str(uuid.uuid4()),
            "type": "surowiec",
            "name": item_name,
            "productName": item_name,
            "amount": final_amount,
            "netWeight": final_amount,
            "quantity": final_amount,
            "unit": "kg",
            "confirmed": False,
            "nr_palety": nr_palety,
            "sourcePalletNo": mother_sscc or nr_palety,
            "nr_partii": orig_partia,
            "data_produkcji": orig_data_prod,
            "data_przydatnosci": orig_data_przyd
        }]
        try:
            cursor.execute("""
                INSERT INTO magazyn_dostawy
                    (id, order_ref, supplier, delivery_date, status, items,
                     created_by, created_at, requires_lab, linia)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (dostawa_id, f"Czyszczenie Zlecenie #{plan_id}", "PRODUKCJA", data_produkcji, "OCZEKUJE",
                  json.dumps(items), user_login, datetime.now(), 0, linia))

            cursor.execute(f"UPDATE {table_pal} SET status='przeklasyfikowana' WHERE id=%s", (paleta_id,))

            if mother_sscc:
                try:
                    cursor.execute("""
                        SELECT linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login, data_ruchu
                        FROM palety_historia
                        WHERE (nr_palety IS NOT NULL AND nr_palety = %s)
                        ORDER BY data_ruchu ASC, id ASC
                    """, (mother_sscc,))
                    mother_history = cursor.fetchall() or []
                    for h in mother_history:
                        h_linia = (h.get('linia') if isinstance(h, dict) else h[0]) or linia
                        h_typ = (h.get('typ_palety') if isinstance(h, dict) else h[1]) or 'surowiec'
                        h_akcja = (h.get('akcja') if isinstance(h, dict) else h[2])
                        h_zrodlo = (h.get('lokalizacja_zrodlowa') if isinstance(h, dict) else h[3])
                        h_cel = (h.get('lokalizacja_docelowa') if isinstance(h, dict) else h[4])
                        h_kom = (h.get('komentarz') if isinstance(h, dict) else h[5])
                        h_user = (h.get('user_login') if isinstance(h, dict) else h[6])
                        h_data = (h.get('data_ruchu') if isinstance(h, dict) else h[7]) or datetime.now()
                        cursor.execute("""
                            INSERT INTO palety_historia
                            (paleta_id, nr_palety, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login, data_ruchu)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            paleta_id, nr_palety, h_linia, h_typ, h_akcja,
                            h_zrodlo, h_cel, h_kom, h_user, h_data
                        ))
                except Exception as hist_copy_err:
                    current_app.logger.warning('Failed to copy mother pallet history for %s: %s', nr_palety, hist_copy_err)

            reclass_comment = f"Przeklasyfikowano na surowiec: {item_name} z palety matki {mother_sscc}. Oczekuje w dostawach" if mother_sscc else f"Przeklasyfikowano na surowiec: {item_name}. Oczekuje w dostawach"
            cursor.execute(
                "INSERT INTO palety_historia (paleta_id, nr_palety, linia, typ_palety, akcja, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, %s, 'surowiec', 'PRZEKLASYFIKOWANIE', %s, %s, %s)",
                (paleta_id, nr_palety, linia, lokalizacja, reclass_comment, user_login)
            )

            if mother_sscc:
                try:
                    cursor.execute(
                        "INSERT INTO palety_historia (nr_palety, linia, typ_palety, akcja, komentarz, user_login) VALUES (%s, %s, 'surowiec', 'PRZEKLASYFIKOWANIE_POTOMNA', %s, %s)",
                        (mother_sscc, linia, f"Wykorzystano do czyszczenia w zleceniu #{plan_id}. Nowa paleta potomna: {nr_palety} ({item_name}, {final_amount} kg)", user_login)
                    )
                except Exception as m_log_err:
                    current_app.logger.warning('Failed to log child link on mother pallet %s: %s', mother_sscc, m_log_err)
        except Exception as e:
            current_app.logger.error('Database error for Czyszczenie dostawa: %s', e)

    @staticmethod
    def _trigger_closing_report_print(cursor, plan_id, table_plan, table_pal):
        """Check if this is the last pallet of completed plan and trigger office print report."""
        try:
            cursor.execute(f"SELECT status FROM {table_plan} WHERE id=%s", (plan_id,))
            plan_status_row = cursor.fetchone()
            if plan_status_row and str(plan_status_row[0]).strip().lower() in ('zakończone', 'zakończony', 'zakonczone'):
                cursor.execute(f"SELECT COUNT(id) FROM {table_pal} WHERE plan_id=%s", (plan_id,))
                total_pallets = cursor.fetchone()[0] or 0

                cursor.execute(f"SELECT COUNT(id) FROM {table_pal} WHERE plan_id=%s AND status IN ('przyjeta', 'w_magazynie')", (plan_id,))
                accepted_pallets = cursor.fetchone()[0] or 0

                if total_pallets > 0 and total_pallets == accepted_pallets:
                    current_app.logger.info("Magazynier przyjął ostatnią paletę zlecenia %s. Wyzwalanie wydruku biurowego.", plan_id)
                    from app.services.office_print_service import trigger_office_print
                    trigger_office_print(plan_id)
                    return "Zlecenie zamknięte - przyjęto ostatnią paletę. Raport został wysłany na drukarkę."
        except Exception as print_err:
            current_app.logger.error('Failed to check/trigger auto-print for plan %s: %s', plan_id, print_err)
        return None

    @staticmethod
    def potwierdz_palete(paleta_id, linia, user_login, app_obj, update_paleta_workowanie, update_paleta_magazyn, is_ajax, safe_return_url):
        """Confirm paleta acceptance with warehouse manager/lider."""
        linia = linia
        table_plan = get_table_name('plan_produkcji', linia)
        table_pal = get_table_name('palety_workowanie', linia)
        table_mag = get_table_name('magazyn_palety', linia)

        role = str(session.get('rola', '')).strip()
        if role not in ['magazynier', 'lider', 'admin', 'masteradmin']:
            current_app.logger.warning(
                '[WAREHOUSE-AUTH] User %s with role=%s tried to confirm paleta %s - insufficient permissions',
                user_login,
                role,
                paleta_id,
            )
            return ({'success': False, 'message': 'Brak uprawnień do zatwierdzania palet'}, 403, None)

        provided_netto = None
        provided_brutto = None
        deklarowana_waga = None
        weight_difference = None
        has_weight_difference = False
        check_only_request = False
        force_accept_request = False
        status_updated = False
        error_message = None

        conn = get_db_connection()
        try:
            cursor = conn.cursor()

            tara = 25
            try:
                cursor.execute(f"SELECT COALESCE(tara,25) FROM {table_pal} WHERE id=%s", (paleta_id,))
                trow = cursor.fetchone()
                tara = int(trow[0]) if trow and trow[0] is not None else 25
            except Exception as error:
                current_app.logger.warning('Failed to fetch tara for paleta %s: %s', paleta_id, error)

            try:
                if request and request.form.get('waga_palety'):
                    try:
                        provided_netto = int(float(require_field(request.form, 'waga_palety').replace(',', '.')))
                    except (ValueError, Exception):
                        provided_netto = None
                elif request and request.form.get('waga_brutto'):
                    try:
                        provided_brutto = int(float(require_field(request.form, 'waga_brutto').replace(',', '.')))
                    except (ValueError, Exception):
                        provided_brutto = None
                    if provided_brutto is not None:
                        netto_val = provided_brutto - int(tara)
                        provided_netto = netto_val if netto_val >= 0 else 0
            except Exception as error:
                current_app.logger.error('Failed to parse provided weight for paleta %s: %s', paleta_id, error, exc_info=True)

            if request:
                check_only_request = str(request.form.get('check_only', '')).strip().lower() in ('1', 'true', 'yes')
                force_accept_request = str(request.form.get('force_accept', '')).strip().lower() in ('1', 'true', 'yes')

            try:
                cursor.execute(f"SELECT waga FROM {table_pal} WHERE id=%s", (paleta_id,))
                drow = cursor.fetchone()
                if drow and drow[0] is not None:
                    deklarowana_waga = int(drow[0])
            except Exception as error:
                current_app.logger.debug('Failed to fetch declared weight for paleta %s: %s', paleta_id, error)

            if deklarowana_waga is not None and provided_netto is not None:
                try:
                    weight_difference = round(abs(provided_netto - deklarowana_waga), 1)
                    has_weight_difference = bool(weight_difference > 1)
                except Exception:
                    weight_difference = None
                    has_weight_difference = False

            if is_ajax and check_only_request:
                return (
                    {
                        'success': True,
                        'check_only': True,
                        'has_difference': has_weight_difference,
                        'difference': weight_difference,
                        'requires_confirmation': has_weight_difference,
                    }, 200, None
                )

            try:
                if provided_netto is not None:
                    cursor.execute(f"UPDATE {table_pal} SET waga_potwierdzona=%s WHERE id=%s", (provided_netto, paleta_id))
                if provided_brutto is not None:
                    cursor.execute(f"UPDATE {table_pal} SET waga_brutto=%s WHERE id=%s", (provided_brutto, paleta_id))
                if provided_netto is not None or provided_brutto is not None:
                    conn.commit()
            except Exception as error:
                current_app.logger.error('Failed to persist weights for paleta %s: %s', paleta_id, error, exc_info=True)
                try:
                    conn.rollback()
                except Exception:
                    pass

            prev_status = ''
            plan_id = None
            stored_netto = None
            nr_palety = None
            nr_plomby = None
            try:
                cursor.execute(
                    f"SELECT plan_id, COALESCE(status,''), COALESCE(waga_potwierdzona, waga, 0), nr_palety, nr_plomby FROM {table_pal} WHERE id=%s",
                    (paleta_id,),
                )
                prev_row = cursor.fetchone()
                if prev_row:
                    plan_id = prev_row[0]
                    prev_status = prev_row[1]
                    stored_netto = int(prev_row[2] or 0)
                    nr_palety = prev_row[3]
                    nr_plomby = prev_row[4] if len(prev_row) > 4 else None
            except Exception as error:
                current_app.logger.warning('Failed to fetch plan_id/status/weights for paleta %s: %s', paleta_id, error)

            try:
                if linia == 'AGRO':
                    cursor.execute(
                        f"UPDATE {table_pal} SET status='przyjeta', "
                        "data_potwierdzenia = DATE_ADD(data_dodania, INTERVAL TIMESTAMPDIFF(SECOND, data_dodania, NOW()) SECOND), "
                        "czas_potwierdzenia_s = TIMESTAMPDIFF(SECOND, data_dodania, NOW()), "
                        "czas_rzeczywistego_potwierdzenia = SEC_TO_TIME(TIMESTAMPDIFF(SECOND, data_dodania, NOW())) "
                        f"WHERE id=%s",
                        (paleta_id,),
                    )
                else:
                    cursor.execute(f"UPDATE {table_pal} SET status='przyjeta' WHERE id=%s", (paleta_id,))
                conn.commit()
                status_updated = True
            except Exception as error:
                current_app.logger.warning('Complex update failed for paleta %s: %s, retrying simple update', paleta_id, error)
                try:
                    cursor.execute(f"UPDATE {table_pal} SET status='przyjeta' WHERE id=%s", (paleta_id,))
                    conn.commit()
                    status_updated = True
                except Exception as second_error:
                    current_app.logger.error('Simple status update also failed for paleta %s: %s', paleta_id, second_error, exc_info=True)
                    error_message = str(second_error)
                    try:
                        conn.rollback()
                    except Exception:
                        pass

            if not status_updated:
                if is_ajax:
                    return ({'success': False, 'message': f'Nie udało się zatwierdzić palety: {error_message or "błąd zapisu statusu"}'}, 500, None)
                return ('OK', 302, safe_return_url)

            if plan_id:
                netto_val = provided_netto if provided_netto is not None else stored_netto

                try:
                    cursor.execute(f"SELECT data_planu, produkt, data_produkcji FROM {table_plan} WHERE id=%s", (plan_id,))
                    row = cursor.fetchone()
                    if row and prev_status not in ('przyjeta', 'w_magazynie'):
                        if linia == 'AGRO':
                            mp_id = plan_id
                        else:
                            cursor.execute(f"SELECT id FROM {table_plan} WHERE data_planu=%s AND produkt=%s AND sekcja='Magazyn' LIMIT 1", (row[0], row[1]))
                            mp = cursor.fetchone()
                            mp_id = mp[0] if mp else None

                        nr_partii = request.form.get('nr_partii') if request else None

                        data_produkcji = request.form.get('data_produkcji') if request else None
                        if not data_produkcji or not data_produkcji.strip():
                            plan_prod_date = row[2]
                            if plan_prod_date:
                                if hasattr(plan_prod_date, 'strftime'):
                                    data_produkcji = plan_prod_date.strftime('%Y-%m-%d')
                                else:
                                    data_produkcji = str(plan_prod_date)
                            else:
                                plan_date = row[0]
                                if plan_date:
                                    if hasattr(plan_date, 'strftime'):
                                        data_produkcji = plan_date.strftime('%Y-%m-%d')
                                else:
                                    data_produkcji = datetime.now().strftime('%Y-%m-%d')

                        data_przydatnosci = request.form.get('data_przydatnosci') if request else None
                        lokalizacja = request.form.get('lokalizacja') if request else None
                        if not lokalizacja or not str(lokalizacja).strip():
                            lokalizacja = 'OCZEKUJĄCE'

                        prod_name_str = str(row[1] or '').strip()
                        is_czyszczenie_product = (
                            prod_name_str in ('Czyszczenie', 'Maka Mix do Lnu', 'Mąka mix do Lnu')
                            or 'czyszczenie' in prod_name_str.lower()
                            or 'maka mix do lnu' in prod_name_str.lower()
                            or 'mąka mix do lnu' in prod_name_str.lower()
                        )

                        if is_czyszczenie_product:
                            PalletConfirmationService._handle_czyszczenie_reclassification(
                                cursor, conn, paleta_id, plan_id, linia, nr_palety, table_pal,
                                netto_val, stored_netto, data_produkcji, user_login, lokalizacja
                            )
                        else:
                            try:
                                pw_lp_val = None
                                try:
                                    cursor.execute(f"SHOW COLUMNS FROM {table_pal} LIKE 'nr_palety_lp'")
                                    if cursor.fetchone():
                                        cursor.execute(f"SELECT nr_palety_lp FROM {table_pal} WHERE id = %s", (paleta_id,))
                                        pw_lp_row = cursor.fetchone()
                                        pw_lp_val = pw_lp_row[0] if pw_lp_row else None
                                except Exception:
                                    pw_lp_val = None

                                has_mag_lp = False
                                try:
                                    cursor.execute(f"SHOW COLUMNS FROM {table_mag} LIKE 'nr_palety_lp'")
                                    has_mag_lp = bool(cursor.fetchone())
                                except Exception:
                                    has_mag_lp = False

                                if has_mag_lp:
                                    cursor.execute(
                                        f"INSERT IGNORE INTO {table_mag} (paleta_workowanie_id, plan_id, data_planu, produkt, waga_netto, waga_brutto, tara, user_login, nr_partii, data_produkcji, data_przydatnosci, lokalizacja, nr_palety, nr_plomby, nr_palety_lp) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                                        (paleta_id, mp_id, row[0], row[1], netto_val, provided_brutto if provided_brutto is not None else 0, tara, user_login, nr_partii, data_produkcji, data_przydatnosci, lokalizacja, nr_palety, nr_plomby, pw_lp_val),
                                    )
                                else:
                                    cursor.execute(
                                        f"INSERT IGNORE INTO {table_mag} (paleta_workowanie_id, plan_id, data_planu, produkt, waga_netto, waga_brutto, tara, user_login, nr_partii, data_produkcji, data_przydatnosci, lokalizacja, nr_palety, nr_plomby) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                                        (paleta_id, mp_id, row[0], row[1], netto_val, provided_brutto if provided_brutto is not None else 0, tara, user_login, nr_partii, data_produkcji, data_przydatnosci, lokalizacja, nr_palety, nr_plomby),
                                    )

                                from app.services.warehouse_history_service import WarehouseHistoryService
                                cols_ph = WarehouseHistoryService._get_table_columns(cursor, 'palety_historia')
                                loc_target = lokalizacja or 'OCZEKUJĄCE'
                                hist_kom = f"Rejestracja wyrobu i przyjęcie na {loc_target}: {row[1]}, partia: {nr_partii}"
                                if 'nr_palety' in cols_ph:
                                    cursor.execute(
                                        "INSERT INTO palety_historia (paleta_id, nr_palety, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, %s, 'wyrob_gotowy', 'PRZYJECIE', %s, %s, %s, %s)",
                                        (paleta_id, nr_palety, linia, f"Produkcja {linia}", loc_target, hist_kom, user_login)
                                    )
                                else:
                                    cursor.execute(
                                        "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, 'wyrob_gotowy', 'PRZYJECIE', %s, %s, %s, %s)",
                                        (paleta_id, linia, f"Produkcja {linia}", loc_target, hist_kom, user_login)
                                    )
                            except Exception as e:
                                current_app.logger.debug('Database error for paleta %s in %s: %s', paleta_id, table_mag, e)

                        if cursor.rowcount > 0:
                            current_app.logger.info(
                                'Potwierdzono paletę ID=%s: waga_netto=%s kg, produkt=%s, użytkownik=%s, lokalizacja=%s',
                                paleta_id,
                                netto_val,
                                row[1] if len(row) > 1 else '—',
                                user_login,
                                lokalizacja
                            )
                            audit_log('Potwierdził paletę', f'ID={paleta_id}, produkt={row[1] if len(row) > 1 else "—"}, waga_netto={netto_val} kg, lokalizacja={lokalizacja}')
                        else:
                            current_app.logger.debug('Paleta ID=%s już jest w magazynie (INSERT IGNORE pominął duplikat), waga=%s kg', paleta_id, netto_val)

                        cursor.execute(
                            f"UPDATE {table_plan} SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga_netto),0) FROM {table_mag} WHERE plan_id = {table_plan}.id) WHERE data_planu=%s AND produkt=%s AND sekcja='Magazyn'",
                            (row[0], row[1]),
                        )
                        conn.commit()

                        printed_msg = PalletConfirmationService._trigger_closing_report_print(
                            cursor, plan_id, table_plan, table_pal
                        )

                except Exception as error:
                    current_app.logger.error('Failed to update Magazyn aggregates for paleta %s: %s', paleta_id, error, exc_info=True)
                    try:
                        conn.rollback()
                    except Exception:
                        pass

        except Exception as error:
            current_app.logger.error('Failed to potwierdz palete %s: %s', paleta_id, error, exc_info=True)
        finally:
            try:
                conn.close()
            except Exception:
                pass

        try:
            if is_ajax:
                response_data = {'success': True, 'paleta_id': paleta_id}
                if 'printed_msg' in locals() and printed_msg:
                    response_data['message'] = printed_msg
                if has_weight_difference and not force_accept_request:
                    response_data['has_difference'] = True
                    response_data['difference'] = weight_difference
                return (response_data, 200, None)
        except Exception:
            pass
        return ('OK', 302, safe_return_url)
