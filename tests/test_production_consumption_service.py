import unittest
from app.core.factory import create_app
from app.db import get_db_connection
from app.services.production_consumption_service import ProductionConsumptionService


class TestProductionConsumptionService(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        self.app_context.pop()

    def test_lookup_and_consume_pallet_flow(self):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Wstaw testowy surowiec
        test_sscc = 'TEST_SSCC_9988776655'
        cursor.execute("""
            INSERT INTO magazyn_surowce (nr_palety, nazwa, stan_magazynowy, lokalizacja, nr_partii)
            VALUES (%s, %s, %s, %s, %s)
        """, (test_sscc, 'TESTOWY SUROWIEC MĄCZKA', 750.0, 'R010101', 'BATCH-9988'))
        conn.commit()
        inserted_id = cursor.lastrowid

        try:
            # 1. Lookup
            pallet = ProductionConsumptionService.lookup_pallet_for_consumption(test_sscc, preferred_line='PSD')
            self.assertIsNotNone(pallet)
            self.assertEqual(pallet['productName'], 'TESTOWY SUROWIEC MĄCZKA')
            self.assertEqual(pallet['amount'], 750.0)
            self.assertEqual(pallet['type'], 'Surowiec')

            # 2. Consume & Archive
            success, msg, archived = ProductionConsumptionService.consume_and_archive_pallet(
                pallet_id=inserted_id,
                pallet_type='Surowiec',
                linia='PSD',
                worker_login='Tester_Magazynier'
            )
            self.assertTrue(success)
            self.assertIsNotNone(archived)
            self.assertEqual(archived['waga_ostatnia'], 750.0)

            # 3. Sprawdź czy usunięto z aktywnego magazynu
            cursor.execute("SELECT * FROM magazyn_surowce WHERE id = %s", (inserted_id,))
            active_row = cursor.fetchone()
            self.assertIsNone(active_row)

            # 4. Sprawdź czy jest w archiwum
            cursor.execute("SELECT * FROM magazyn_archiwum WHERE original_id = %s AND typ_palety = 'Surowiec'", (inserted_id,))
            archive_row = cursor.fetchone()
            self.assertIsNotNone(archive_row)
            self.assertIn('Zużycie w produkcji', archive_row['komentarz'])

            # 5. Sprawdź dzienną historię
            history = ProductionConsumptionService.get_daily_consumption_history()
            self.assertTrue(any(h['nr_palety'] == test_sscc for h in history))

        finally:
            # Czyszczenie po teście
            cursor.execute("DELETE FROM magazyn_surowce WHERE id = %s", (inserted_id,))
            cursor.execute("DELETE FROM magazyn_archiwum WHERE nr_palety = %s", (test_sscc,))
            cursor.execute("DELETE FROM palety_historia WHERE paleta_id = %s", (inserted_id,))
            conn.commit()
            conn.close()


if __name__ == '__main__':
    unittest.main()
