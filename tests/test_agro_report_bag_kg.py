from app.blueprints.agro_warehouse.api_reports import _extract_bag_kg, _resolve_report_bag_kg

class DummyCursor:
    def __init__(self, fetchone_rows=None):
        self._fetchone_rows = list(fetchone_rows or [])
        self.executed = []

    def execute(self, query, params):
        self.executed.append((query, params))

    def fetchone(self):
        if not self._fetchone_rows:
            return None
        return self._fetchone_rows.pop(0)


def test_extract_bag_kg_parses_numeric_value():
    assert _extract_bag_kg("worki_zgrzewane_20") == 20.0
    assert _extract_bag_kg("20,5kg") == 20.5
    assert _extract_bag_kg("agro") is None


def test_resolve_bag_kg_prefers_settlement_value_over_plan_type():
    cursor = DummyCursor()
    plan = {"typ_produkcji": "worki_zgrzewane_25", "zasyp_typ_produkcji": "worki_zgrzewane_25", "produkt": "X"}
    settlements = [{"kg_na_worek": 20.0}]

    bag_kg = _resolve_report_bag_kg(cursor, plan, settlements, {})

    assert bag_kg == 20.0


def test_resolve_bag_kg_uses_plan_type_when_available():
    cursor = DummyCursor()
    plan = {"typ_produkcji": "worki_zgrzewane_20", "zasyp_typ_produkcji": "agro", "produkt": "X"}

    bag_kg = _resolve_report_bag_kg(cursor, plan, [], {})

    assert bag_kg == 20.0


def test_resolve_bag_kg_uses_zasyp_type_when_work_type_is_generic():
    cursor = DummyCursor()
    plan = {"typ_produkcji": "agro", "zasyp_typ_produkcji": "worki_zgrzewane_20", "produkt": "X"}

    bag_kg = _resolve_report_bag_kg(cursor, plan, [], {})

    assert bag_kg == 20.0


def test_resolve_bag_kg_falls_back_to_product_registry_and_caches_result():
    cursor = DummyCursor(fetchone_rows=[{"typ_produkcji": "worki_zgrzewane_20"}])
    cache = {}
    plan = {"typ_produkcji": "agro", "zasyp_typ_produkcji": "agro", "produkt": "KREMOWKA LEN"}

    first = _resolve_report_bag_kg(cursor, plan, [], cache)
    second = _resolve_report_bag_kg(cursor, plan, [], cache)

    assert first == 20.0
    assert second == 20.0
    assert len(cursor.executed) == 1


def test_resolve_bag_kg_uses_heuristic_for_milk_name():
    cursor = DummyCursor(fetchone_rows=[None])
    plan = {"typ_produkcji": "agro", "zasyp_typ_produkcji": "agro", "produkt": "MILK SPECIAL"}

    bag_kg = _resolve_report_bag_kg(cursor, plan, [], {})

    assert bag_kg == 20.0


def test_resolve_bag_kg_defaults_to_25_when_no_source_available():
    cursor = DummyCursor(fetchone_rows=[None])
    plan = {"typ_produkcji": "agro", "zasyp_typ_produkcji": "agro", "produkt": "PREMIX"}

    bag_kg = _resolve_report_bag_kg(cursor, plan, [], {})

    assert bag_kg == 25.0
