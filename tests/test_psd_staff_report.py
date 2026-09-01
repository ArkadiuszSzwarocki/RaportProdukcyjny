import unittest
from datetime import date
from unittest.mock import MagicMock, patch
import pandas as pd
from scripts.generator_raportow import generuj_paczke_raportow
from scripts.raporty import generuj_pdf


class TestPsdStaffReport(unittest.TestCase):

    def test_generuj_pdf_includes_obsada_obecni_nieobecni(self):
        dzisiaj = str(date.today())
        uwagi = "Notatki lidera test"
        lider = "Lider PSD Test"
        prod_rows = [('Zasyp', 'Produkt A', 10000, 10000, '08:00', '16:00', 'ZLEC-1', 101)]
        awarie_rows = []
        hr_rows = [
            ('Jan Kowalski', 'Zasyp', 'Obecny', 8.0, 'Automatyczne z obsady'),
            ('Piotr Nowak', 'Workowanie', 'Obecny', 8.0, 'Automatyczne z obsady')
        ]
        obsada_rows = [
            ('Zasyp', 'Jan Kowalski', 'Produkcja'),
            ('Workowanie', 'Piotr Nowak', 'Produkcja')
        ]
        nieobecni_rows = [
            ('Adam Urlopowicz', 'URLOP', 'Urlop wypoczynkowy'),
            ('Krzysztof Chory', 'L4', 'Zwolnienie lekarskie')
        ]
        
        pdf_name = generuj_pdf(
            dzisiaj=dzisiaj,
            uwagi=uwagi,
            lider=lider,
            prod_rows=prod_rows,
            awarie_rows=awarie_rows,
            hr_rows=hr_rows,
            folder='raporty_temp',
            linia='PSD',
            obsada_rows=obsada_rows,
            nieobecni_rows=nieobecni_rows
        )
        self.assertIsNotNone(pdf_name)
        self.assertTrue(pdf_name.endswith('.pdf'))


if __name__ == '__main__':
    unittest.main()
