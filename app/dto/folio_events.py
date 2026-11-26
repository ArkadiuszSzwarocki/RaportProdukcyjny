"""Immutable domain event DTOs for AGRO film roll ledger operations."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FoilSourceSnapshot:
    """Snapshot of source packaging stock before and after film withdrawal."""

    source_id: int
    source_sscc: str
    source_name: str
    source_location: str
    qty_before: float
    qty_after: float


@dataclass(frozen=True)
class FoilRollTarget:
    """Target LP01 roll created or reused during film withdrawal."""

    roll_id: int
    roll_sscc: str
    amount: float


@dataclass(frozen=True)
class FoilWithdrawalEvent:
    """Value object describing a film withdrawal from warehouse or LP01."""

    source: FoilSourceSnapshot
    roll: FoilRollTarget
    plan_id: int
    link_id: int
    user_login: str
    request_key: str | None = None

    @property
    def reused_lp01_roll(self) -> bool:
        """Return True when an existing unassigned LP01 roll was attached directly."""
        return self.source.source_location.upper() in ('LP01', 'MASZYNA') and (
            self.roll.roll_id == self.source.source_id
        )


@dataclass(frozen=True)
class FoilClosureEvent:
    """Value object describing a film roll settlement on LP01."""

    opakowanie_id: int
    opak_nazwa: str
    nr_palety: str
    plan_id: int
    stan_poczatkowy: float
    pozostalo_szt: float
    user_login: str

    @property
    def fizycznie_zuzyto(self) -> float:
        """Return physical bag count consumed from this roll."""
        return max(float(self.stan_poczatkowy) - float(self.pozostalo_szt), 0.0)
