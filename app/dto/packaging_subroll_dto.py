"""Immutable DTOs for Nested Handling Unit packaging sub-rolls."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SubrollInsertSpec:
    """Specification for creating a single sub-roll inside a master pallet."""

    parent_id: int
    kod_rolki: str
    nr_rolki: int
    ilosc_szt: int
    waga_kg: float | None = None
    zrodlo: str = 'PODZIAL'
    created_by: str | None = None


@dataclass(frozen=True)
class SubrollDispatchCommand:
    """Command to detach a specific sub-roll from its master pallet onto LP01."""

    subroll_id: int
    user_login: str
    plan_id: int | None = None
    roll_role: str = 'prepared'
    request_key: str | None = None
    previous_remaining: float | str | None = None


@dataclass(frozen=True)
class SubrollReturnCommand:
    """Command to attach an LP01 leftover roll back onto a master pallet as a sub-roll."""

    lp01_item_id: int
    mother_identifier: str | int
    user_login: str
    amount: float | None = None
