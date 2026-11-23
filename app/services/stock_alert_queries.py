"""Read-only queries and view-model enrichment for minimum-stock rules."""
from decimal import Decimal
from app.services.packaging_stock_alerts import (
    CATEGORY_ORDER,
    STOCK_TYPE_PACKAGING,
    format_rule_key,
    make_stock_key,
    normalize_stock_type,
    resolve_rule_stock_type,
    stock_type_label,
)


def fetch_rules(cursor):
    """Fetch all configured threshold rules together with optional recipient metadata."""
    cursor.execute(
        '''SELECT r.*, g.recipients AS group_name, g.cc_recipients
           FROM packaging_alert_rules r
           LEFT JOIN packaging_alert_groups g ON g.id = r.group_id
           ORDER BY r.material'''
    )
    return cursor.fetchall() or []


def fetch_recipient_groups(cursor):
    """Fetch all configured e-mail recipient groups for stock shortage alerts."""
    cursor.execute('SELECT * FROM packaging_alert_groups ORDER BY recipients')
    return cursor.fetchall() or []


def enrich_materials_and_rules(materials, rules):
    """Attach live stock, shortages, categories, and composite keys to catalog and rule rows."""
    for item in materials:
        item_stock_type = normalize_stock_type(
            item.get('stock_type') or item.get('category'),
            unit=item.get('default_unit', ''),
        ) or STOCK_TYPE_PACKAGING
        item['stock_type'] = item_stock_type
        item['rule_key'] = format_rule_key(item_stock_type, item['material'])

    stocks = {make_stock_key(row['stock_type'], row['material']): row['stock'] for row in materials}
    categories_by_key = {make_stock_key(row['stock_type'], row['material']): row['category'] for row in materials}
    order_map = {cat: idx for idx, cat in enumerate(CATEGORY_ORDER)}

    for rule in rules:
        rule_stock_type = resolve_rule_stock_type(rule, stocks)
        key = make_stock_key(rule_stock_type, rule['material'])
        stock_val = stocks.get(key, Decimal(0))
        stock_dec = Decimal(str(stock_val or 0))
        minimum_dec = Decimal(str(rule['minimum'] or 0))
        rule['stock_type'] = rule_stock_type
        rule['material'] = str(rule['material']).strip()
        rule['stock'] = stock_val
        rule['shortage'] = max(Decimal(0), minimum_dec - stock_dec)
        rule['is_low'] = stock_dec <= minimum_dec
        rule['category'] = categories_by_key.get(key) or stock_type_label(rule_stock_type)
        rule['rule_key'] = format_rule_key(rule_stock_type, rule['material'])

    rules.sort(key=lambda rule: (order_map.get(rule['category'], 99), rule['material'].casefold()))
    rules_by_key = {rule['rule_key']: rule for rule in rules}
    return materials, rules, rules_by_key
