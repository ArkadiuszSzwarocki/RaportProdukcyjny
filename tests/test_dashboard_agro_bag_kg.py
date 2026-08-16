from app.services.dashboard_service import _extract_bag_kg, _resolve_agro_bag_kg


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


def test_extract_bag_kg_parses_value_with_comma():
    assert _extract_bag_kg("worki_zgrzewane_20") == 20.0
    assert _extract_bag_kg("20,5 kg") == 20.5
    assert _extract_bag_kg("agro") is None


def test_resolve_agro_bag_kg_prefers_history_kg_na_worek():
    cursor = DummyCursor()
    active_plan = {"typ_produkcji": "worki_zgrzewane_25", "produkt": "X"}
    history = [{"kg_na_worek": 20.0}]

    bag_kg = _resolve_agro_bag_kg(cursor, active_plan, history, {})

    assert bag_kg == 20.0


def test_resolve_agro_bag_kg_uses_plan_type():
    cursor = DummyCursor()
    active_plan = {"typ_produkcji": "worki_zgrzewane_20", "produkt": "X"}

    bag_kg = _resolve_agro_bag_kg(cursor, active_plan, [], {})

    assert bag_kg == 20.0


def test_resolve_agro_bag_kg_uses_zasyp_type_when_plan_generic():
    cursor = DummyCursor()
    active_plan = {"typ_produkcji": "agro", "zasyp_typ_produkcji": "worki_zgrzewane_20", "produkt": "X"}

    bag_kg = _resolve_agro_bag_kg(cursor, active_plan, [], {})

    assert bag_kg == 20.0


def test_resolve_agro_bag_kg_uses_product_registry_and_cache():
    cursor = DummyCursor(fetchone_rows=[{"typ_produkcji": "worki_zgrzewane_20"}])
    cache = {}
    active_plan = {"typ_produkcji": "agro", "produkt": "KREMOWKA LEN"}

    first = _resolve_agro_bag_kg(cursor, active_plan, [], cache)
    second = _resolve_agro_bag_kg(cursor, active_plan, [], cache)

    assert first == 20.0
    assert second == 20.0
    assert len(cursor.executed) == 1


def test_resolve_agro_bag_kg_defaults_to_25_without_sources():
    cursor = DummyCursor(fetchone_rows=[None])
    active_plan = {"typ_produkcji": "agro", "produkt": "PREMIX"}

    bag_kg = _resolve_agro_bag_kg(cursor, active_plan, [], {})

    assert bag_kg == 25.0
