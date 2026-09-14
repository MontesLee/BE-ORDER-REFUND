"""The AfterSale state machine.

::

    PENDING  --approve-->  APPROVED  --execute-->  REFUNDING
                                                      |  ^
                                       third-party OK |  | third-party failed
                                                      v  | (retry)
                                                  REFUNDED   REFUND_FAILED

Rules
-----
* ``PENDING  -> REFUNDED``   is illegal (must be approved first).
* ``REFUNDED -> *``          is illegal: ``REFUNDED`` is terminal.
* ``REFUNDING -> APPROVED``  is illegal (no going back).
* Only ``APPROVED`` and ``REFUND_FAILED`` may start a refund attempt, which is
  what makes "retry" legal and "duplicate execute" harmless.

The table below is the single source of truth. Every status write in the
service layer goes through :func:`assert_transition`; nothing writes a status
literal directly.
"""

from __future__ import annotations

from typing import Dict, FrozenSet

AFTER_SALE_TRANSITIONS: Dict[str, FrozenSet[str]] = {
    "PENDING": frozenset({"APPROVED"}),
    "APPROVED": frozenset({"REFUNDING"}),
    "REFUNDING": frozenset({"REFUNDED", "REFUND_FAILED"}),
    "REFUND_FAILED": frozenset({"REFUNDING"}),
    "REFUNDED": frozenset(),  # terminal
}

#: States from which a (new or retried) refund attempt may be started.
REFUND_START_STATES: FrozenSet[str] = frozenset({"APPROVED", "REFUND_FAILED"})

#: Terminal states never leave the state machine.
TERMINAL_STATES: FrozenSet[str] = frozenset({"REFUNDED"})

#: States in which an attempt is already in flight.
IN_FLIGHT_STATES: FrozenSet[str] = frozenset({"REFUNDING"})


class IllegalStateTransition(Exception):
    """Raised when a caller asks for a transition the state machine forbids."""

    def __init__(self, source: str, target: str) -> None:
        self.source = source
        self.target = target
        super().__init__(f"illegal after-sale transition: {source} -> {target}")


def can_transition(source: str, target: str) -> bool:
    return target in AFTER_SALE_TRANSITIONS.get(source, frozenset())


def assert_transition(source: str, target: str) -> None:
    if not can_transition(source, target):
        raise IllegalStateTransition(source, target)


def can_start_refund(status: str) -> bool:
    return status in REFUND_START_STATES


def is_terminal(status: str) -> bool:
    return status in TERMINAL_STATES


def allowed_targets(source: str) -> FrozenSet[str]:
    return AFTER_SALE_TRANSITIONS.get(source, frozenset())
