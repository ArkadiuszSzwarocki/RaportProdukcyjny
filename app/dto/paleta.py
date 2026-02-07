from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional, Any, Dict, Tuple


@dataclass
class PaletaDTO:
    id: Optional[int] = None
    plan_id: Optional[int] = None
    waga: Optional[int] = None
    tara: Optional[int] = None
    waga_brutto: Optional[int] = None
    data_dodania: Optional[datetime] = None
    produkt: Optional[str] = None
    typ_produkcji: Optional[str] = None
    status: Optional[str] = None
    czas_potwierdzenia_s: Optional[int] = None

    @classmethod
    def from_db_row(cls, row: Any, columns: Optional[Tuple[str, ...]] = None) -> "PaletaDTO":
        """
        Stwórz DTO z wiersza zwróconego przez kursor DB.
        Obsługuje tuple/list (bez nazw kolumn) oraz dict (np. z cursor.fetchone()
        jeśli używany jest DictCursor).

        Jeśli przekazano `columns` (krotka nazw kolumn), zostanie użyta do mapowania
        wartości z tuple na atrybuty DTO.
        """
        if row is None:
            return cls()

        # Jeśli otrzymano słownik podobny do {col: val}
        if isinstance(row, dict):
            return cls(
                id=row.get('id'),
                plan_id=row.get('plan_id'),
                waga=row.get('waga'),
                tara=row.get('tara'),
                waga_brutto=row.get('waga_brutto'),
                data_dodania=row.get('data_dodania'),
                produkt=row.get('produkt'),
                typ_produkcji=row.get('typ_produkcji'),
            )

        # Jeśli otrzymano tuple/list: spróbuj dopasować według columns lub przyjąć znany porządek
        if columns:
            data = dict(zip(columns, row))
            return cls.from_db_row(data)

        # Fallback: przyjmij standardowy porządek (częste zapytania w projekcie)
        # (id, plan_id, waga, tara, waga_brutto, data_dodania, produkt, typ_produkcji, status, czas_potwierdzenia_s)
        try:
            return cls(
                id=row[0] if len(row) > 0 else None,
                plan_id=row[1] if len(row) > 1 else None,
                waga=row[2] if len(row) > 2 else None,
                tara=row[3] if len(row) > 3 else None,
                waga_brutto=row[4] if len(row) > 4 else None,
                data_dodania=row[5] if len(row) > 5 else None,
                produkt=row[6] if len(row) > 6 else None,
                typ_produkcji=row[7] if len(row) > 7 else None,
                status=row[8] if len(row) > 8 else None,
                czas_potwierdzenia_s=row[9] if len(row) > 9 else None,
            )
        except Exception:
            return cls()

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if isinstance(self.data_dodania, datetime):
            d['data_dodania'] = self.data_dodania.isoformat(sep=' ')
        return d

    def __repr__(self) -> str:  # more readable in logs
        return f"PaletaDTO(id={self.id}, plan_id={self.plan_id}, waga={self.waga}, tara={self.tara}, waga_brutto={self.waga_brutto})"
