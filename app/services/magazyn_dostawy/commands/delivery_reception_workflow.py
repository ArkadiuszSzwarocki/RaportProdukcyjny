"""Delivery reception workflow state machine.

Manages the 4-step WMS-grade delivery lifecycle:
  SZKIC -> AWIZOWANE -> W_STREFIE_PRZYJEC -> PUTAWAY_IN_PROGRESS -> COMPLETED

Backward compatible: legacy deliveries with status OCZEKUJE/COMPLETED continue to work.
"""

from enum import Enum
from typing import Tuple, Optional


class DeliveryStatus(str, Enum):
    SZKIC = 'SZKIC'
    AWIZOWANE = 'AWIZOWANE'
    W_STREFIE_PRZYJEC = 'W_STREFIE_PRZYJEC'
    PUTAWAY_IN_PROGRESS = 'PUTAWAY_IN_PROGRESS'
    COMPLETED = 'COMPLETED'
    CANCELLED = 'CANCELLED'
    # Legacy statuses (backward compatibility)
    OCZEKUJE = 'OCZEKUJE'
    IN_PROGRESS = 'IN_PROGRESS'


class PalletItemStatus(str, Enum):
    AWAITING_LABEL = 'AWAITING_LABEL'
    IN_RECEPTION_ZONE = 'IN_RECEPTION_ZONE'
    PUTAWAY_PENDING = 'PUTAWAY_PENDING'
    STORED = 'STORED'
    REJECTED = 'REJECTED'


# Allowed transitions: { current_status: [allowed_next_statuses] }
_TRANSITIONS = {
    DeliveryStatus.SZKIC: [DeliveryStatus.AWIZOWANE, DeliveryStatus.CANCELLED],
    DeliveryStatus.AWIZOWANE: [DeliveryStatus.W_STREFIE_PRZYJEC, DeliveryStatus.CANCELLED],
    DeliveryStatus.W_STREFIE_PRZYJEC: [DeliveryStatus.PUTAWAY_IN_PROGRESS, DeliveryStatus.CANCELLED],
    DeliveryStatus.PUTAWAY_IN_PROGRESS: [DeliveryStatus.COMPLETED, DeliveryStatus.CANCELLED],
    # Legacy statuses can transition to new flow or directly complete
    DeliveryStatus.OCZEKUJE: [DeliveryStatus.COMPLETED, DeliveryStatus.CANCELLED, DeliveryStatus.AWIZOWANE],
    DeliveryStatus.IN_PROGRESS: [DeliveryStatus.COMPLETED, DeliveryStatus.CANCELLED],
    DeliveryStatus.COMPLETED: [],
    DeliveryStatus.CANCELLED: [],
}

# Labels for UI display
STATUS_LABELS = {
    DeliveryStatus.SZKIC: {'label': 'Szkic', 'color': '#94a3b8', 'icon': 'edit_note', 'step': 0},
    DeliveryStatus.AWIZOWANE: {'label': 'Awizowane', 'color': '#f59e0b', 'icon': 'fact_check', 'step': 1},
    DeliveryStatus.W_STREFIE_PRZYJEC: {'label': 'W strefie przyjęć', 'color': '#3b82f6', 'icon': 'local_shipping', 'step': 2},
    DeliveryStatus.PUTAWAY_IN_PROGRESS: {'label': 'Rozlokowanie w toku', 'color': '#8b5cf6', 'icon': 'forklift', 'step': 3},
    DeliveryStatus.COMPLETED: {'label': 'Zakończone', 'color': '#10b981', 'icon': 'check_circle', 'step': 4},
    DeliveryStatus.CANCELLED: {'label': 'Anulowane', 'color': '#ef4444', 'icon': 'cancel', 'step': -1},
    DeliveryStatus.OCZEKUJE: {'label': 'Oczekuje (legacy)', 'color': '#f59e0b', 'icon': 'hourglass_empty', 'step': 1},
    DeliveryStatus.IN_PROGRESS: {'label': 'W trakcie (legacy)', 'color': '#3b82f6', 'icon': 'sync', 'step': 2},
}


class DeliveryReceptionWorkflow:
    """State machine enforcing allowed delivery status transitions."""

    @staticmethod
    def can_transition(current_status: str, target_status: str) -> bool:
        """Check if a transition from current to target status is allowed."""
        try:
            current = DeliveryStatus(current_status)
        except ValueError:
            return False
        try:
            target = DeliveryStatus(target_status)
        except ValueError:
            return False
        return target in _TRANSITIONS.get(current, [])

    @staticmethod
    def validate_transition(current_status: str, target_status: str) -> Tuple[bool, str]:
        """Validate and return a descriptive error if transition is disallowed."""
        if DeliveryReceptionWorkflow.can_transition(current_status, target_status):
            return True, ''
        try:
            current_enum = DeliveryStatus(current_status)
        except ValueError:
            current_enum = None
        try:
            target_enum = DeliveryStatus(target_status)
        except ValueError:
            target_enum = None
        current_label = STATUS_LABELS.get(current_enum, {}).get('label', current_status)
        target_label = STATUS_LABELS.get(target_enum, {}).get('label', target_status)
        return False, f"Niedozwolone przejście statusu: '{current_label}' → '{target_label}'"

    @staticmethod
    def get_next_allowed(current_status: str) -> list:
        """Return list of allowed next statuses from the current state."""
        try:
            current = DeliveryStatus(current_status)
        except ValueError:
            return []
        return [s.value for s in _TRANSITIONS.get(current, [])]

    @staticmethod
    def is_legacy(status: str) -> bool:
        """Check if the status belongs to the legacy flow (pre-WMS)."""
        return status in (DeliveryStatus.OCZEKUJE, DeliveryStatus.IN_PROGRESS)

    @staticmethod
    def is_terminal(status: str) -> bool:
        """Check if the delivery is in a terminal state."""
        return status in (DeliveryStatus.COMPLETED, DeliveryStatus.CANCELLED)

    @staticmethod
    def get_status_meta(status: str) -> dict:
        """Return UI metadata (label, color, icon, step) for a status."""
        try:
            s = DeliveryStatus(status)
        except ValueError:
            return {'label': status, 'color': '#94a3b8', 'icon': 'help_outline', 'step': -1}
        return STATUS_LABELS.get(s, {'label': status, 'color': '#94a3b8', 'icon': 'help_outline', 'step': -1})

    @staticmethod
    def compute_item_status(item: dict) -> str:
        """Derive the pallet-level status from item flags."""
        if item.get('rejected'):
            return PalletItemStatus.REJECTED
        if item.get('putaway_confirmed_at'):
            return PalletItemStatus.STORED
        if item.get('putaway_suggested_location'):
            return PalletItemStatus.PUTAWAY_PENDING
        if item.get('sscc_generated_at') or item.get('nr_palety'):
            return PalletItemStatus.IN_RECEPTION_ZONE
        return PalletItemStatus.AWAITING_LABEL
