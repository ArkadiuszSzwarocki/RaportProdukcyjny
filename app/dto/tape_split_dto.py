"""Immutable DTOs for direct scanner tape-to-rolls splitting."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TapePrintOptions:
    """Printer options for post-split ZPL roll labels."""

    enabled: bool = True
    printer_ip: str | None = None
    printer_name: str | None = None
    copies: int = 2


@dataclass(frozen=True)
class TapeSplitCommand:
    """Command payload for splitting a packaging tape pallet into rolls."""

    pallet_id: int | str | None
    nr_palety: str
    rolls_szt: list[int]
    bag_weight_kg: float | str | None = None
    save_bag_weight: bool = False
    printing: TapePrintOptions = TapePrintOptions()
