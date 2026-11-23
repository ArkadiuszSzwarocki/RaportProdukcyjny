"""Administration of warehouse minimum-stock thresholds."""
from flask import flash, redirect, render_template, request, url_for
from app.decorators import login_required, roles_required
from app.db import get_db_connection
from app.services.packaging_stock_alerts import (
    CATEGORY_ORDER, STOCK_TYPE_PACKAGING, catalog, ensure_schema,
    make_stock_key, normalize_material_key, normalize_stock_type, parse_minimum, send_summary,
)
from app.services.stock_alert_commands import (
    delete_stock_threshold, save_recipient_group, toggle_rule_email_enabled, upsert_stock_threshold,
)
from app.services.stock_alert_queries import enrich_materials_and_rules, fetch_rules


def _resolve_catalog_entry(known_by_key, known_by_name, raw_material, raw_type='', unit=''):
    """Resolve a submitted material name and optional stock_type/unit to a catalog entry."""
    if raw_type:
        explicit_type = normalize_stock_type(raw_type)
        if not explicit_type:
            return None
        return known_by_key.get(make_stock_key(explicit_type, raw_material))
    candidates = known_by_name.get(normalize_material_key(raw_material), [])
    if len(candidates) == 1:
        return candidates[0]
    inferred_type = normalize_stock_type('', unit=unit)
    if inferred_type:
        for entry in candidates:
            if entry[1] == inferred_type:
                return entry
    return None


def _build_material_indexes(materials):
    """Index catalog items by composite (stock_type, name) and fallback name."""
    known_by_key = {}
    known_by_name = {}
    for row in materials:
        material_name = str(row['material']).strip()
        item_type = normalize_stock_type(
            row.get('stock_type') or row.get('category'),
            unit=row.get('default_unit', ''),
        ) or STOCK_TYPE_PACKAGING
        entry = (material_name, item_type)
        key = make_stock_key(item_type, material_name)
        if key not in known_by_key:
            known_by_key[key] = entry
            known_by_name.setdefault(normalize_material_key(material_name), []).append(entry)
    return known_by_key, known_by_name


def prepare_typed_bulk_rules(form, materials):
    """Validate bulk rule selections and return (material, stock_type, minimum, unit) tuples."""
    selected = list(dict.fromkeys(form.getlist('selected')))
    if not selected:
        raise ValueError('Zaznacz przynajmniej jeden materiał.')
    known_by_key, known_by_name = _build_material_indexes(materials)
    rows = []
    seen = set()
    for index in selected:
        if not index.isdigit():
            raise ValueError('Nieprawidłowy wybór materiału.')
        raw_material = form.get('material_' + index, '')
        raw_type = form.get('stock_type_' + index, '') or form.get('category_' + index, '')
        unit = form.get('unit_' + index, '')
        resolved = _resolve_catalog_entry(known_by_key, known_by_name, raw_material, raw_type, unit)
        if not resolved:
            raise ValueError('Lista materiałów zmieniła się. Otwórz okno ponownie.')
        material, stock_type = resolved
        dedup_key = make_stock_key(stock_type, material)
        if dedup_key in seen:
            raise ValueError('Lista materiałów zmieniła się. Otwórz okno ponownie.')
        seen.add(dedup_key)
        try:
            minimum = parse_minimum(form.get('minimum_' + index, ''))
        except ValueError as error:
            raise ValueError(f'{material}: {error}') from None
        if unit not in ('szt.', 'kg', 'm', 'rolki'):
            raise ValueError(f'{material}: wybierz jednostkę magazynową.')
        rows.append((material, stock_type, minimum, unit))
    return rows


def prepare_bulk_rules(form, materials):
    """Legacy wrapper returning 3-tuples for callers not needing stock_type."""
    return [
        (material, minimum, unit)
        for material, _stock_type, minimum, unit in prepare_typed_bulk_rules(form, materials)
    ]


def register_packaging_alert_routes(bp):
    """Register standalone warehouse minimum-stock threshold management routes."""
    @bp.route('/admin/ustawienia/stany-minimalne', methods=['GET', 'POST'])
    @login_required
    @roles_required(['admin', 'masteradmin', 'zarzad', 'lider'])
    def packaging_alerts():
        connection = get_db_connection()
        cursor = None
        try:
            ensure_schema(connection)
            cursor = connection.cursor(dictionary=True)
            materials = catalog(cursor)
            if request.method == 'POST':
                try:
                    action = request.form.get('action')
                    if action == 'bulk_rules':
                        rows = prepare_typed_bulk_rules(request.form, materials)
                        connection.commit()
                        connection.start_transaction()
                        for material, stock_type, minimum, unit in rows:
                            upsert_stock_threshold(cursor, material, stock_type, minimum, unit)
                    elif action == 'rule':
                        known_by_key, known_by_name = _build_material_indexes(materials)
                        unit = request.form.get('unit', '')
                        resolved = _resolve_catalog_entry(
                            known_by_key,
                            known_by_name,
                            request.form.get('material', ''),
                            request.form.get('stock_type', '') or request.form.get('category', ''),
                            unit,
                        )
                        if not resolved:
                            raise ValueError('Wybierz pozycję z ewidencji magazynowej.')
                        material, stock_type = resolved
                        minimum = parse_minimum(request.form.get('minimum', ''))
                        if unit not in ('szt.', 'kg', 'm', 'rolki'):
                            raise ValueError('Wybierz jednostkę zgodną z ewidencją magazynową.')
                        upsert_stock_threshold(cursor, material, stock_type, minimum, unit)
                    elif action == 'delete':
                        delete_stock_threshold(cursor, request.form.get('id', '0'))
                    elif action == 'group':
                        # Legacy compatibility delegate; primary UI lives under admin.stock_alert_emails.
                        save_recipient_group(
                            cursor,
                            request.form.get('recipients', ''),
                            request.form.get('cc_recipients', ''),
                            request.form.get('group_id', ''),
                        )
                    elif action == 'toggle':
                        toggle_rule_email_enabled(cursor, request.form.get('id', '0'))
                    elif action == 'summary':
                        success, message = send_summary(connection, int(request.form.get('group_id', '0')))
                        flash(message, 'success' if success else 'error')
                        return redirect(url_for('admin.packaging_alerts'))
                    else:
                        raise ValueError('Nieznana operacja.')
                    connection.commit()
                    flash('Zapisano stany minimalne magazynu.', 'success')
                except (ValueError, TypeError) as error:
                    connection.rollback()
                    flash(str(error), 'error')
                return redirect(url_for('admin.packaging_alerts'))

            rules = fetch_rules(cursor)
            materials, rules, rules_by_key = enrich_materials_and_rules(materials, rules)
            return render_template(
                'admin/packaging_alerts.html',
                rules=rules,
                materials=materials,
                categories=list(CATEGORY_ORDER),
                rules_by_key=rules_by_key,
                low_count=sum(1 for rule in rules if rule['is_low']),
                total_rules=len(rules),
            )
        finally:
            if cursor is not None:
                cursor.close()
            connection.close()
