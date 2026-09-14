"""Third-party refund channel.

The service never talks to a payment provider directly: it talks to a
``RefundGateway``.  That seam exists for one concrete reason -- the failure
semantics of the external system (I4) must be *deterministically testable*.
A gateway that can only be exercised by really breaking the network cannot be
tested at all, so tests inject a gateway that fails on demand.

Contract
--------
``refund(...)`` is called **outside** any database transaction.

* It returns :class:`GatewayResult`; it does not raise for business failures
  (network error, provider rejection).  Only programming errors should raise.
* It is idempotent with respect to ``idempotency_key``: repeating a call with
  the same key returns the first recorded outcome instead of refunding twice.
  This is the provider-side half of I2; the database is the local half.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Dict, Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class GatewayResult:
    ok: bool
    third_party_ref: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    @classmethod
    def success(cls, ref: str) -> "GatewayResult":
        return cls(ok=True, third_party_ref=ref)

    @classmethod
    def failure(cls, code: str, message: str) -> "GatewayResult":
        return cls(ok=False, error_code=code, error_message=message)


@runtime_checkable
class RefundGateway(Protocol):
    name: str

    def refund(
        self,
        *,
        after_sale_id: int,
        order_id: int,
        amount: int,
        idempotency_key: str,
    ) -> GatewayResult:  # pragma: no cover - protocol
        ...


class StubRefundGateway:
    """Deterministic in-process gateway used by the service and by tests.

    Parameters
    ----------
    fail_first_n:
        Fail the first *n* distinct calls, then succeed.  Used to reproduce the
        R6 incident and to prove that a failed attempt does not consume quota.
    fail_always:
        Fail every call.  Used to assert that a local record is never marked
        ``REFUNDED`` when the provider refused.
    latency_seconds:
        Optional artificial delay, used to widen the concurrency window in
        multi-worker tests.  ``0`` by default so tests stay fast and stable.
    """

    name = "stub"

    def __init__(
        self,
        fail_first_n: int = 0,
        fail_always: bool = False,
        latency_seconds: float = 0.0,
    ) -> None:
        self.fail_first_n = fail_first_n
        self.fail_always = fail_always
        self.latency_seconds = latency_seconds
        self._lock = threading.Lock()
        self._calls = 0
        self._recorded: Dict[str, GatewayResult] = {}

    @property
    def call_count(self) -> int:
        with self._lock:
            return self._calls

    def refund(
        self,
        *,
        after_sale_id: int,
        order_id: int,
        amount: int,
        idempotency_key: str,
    ) -> GatewayResult:
        if self.latency_seconds:
            import time

            time.sleep(self.latency_seconds)

        with self._lock:
            recorded = self._recorded.get(idempotency_key)
            if recorded is not None:
                return recorded

            self._calls += 1
            should_fail = self.fail_always or self._calls <= self.fail_first_n
            if should_fail:
                result = GatewayResult.failure(
                    "PROVIDER_UNAVAILABLE",
                    "third-party refund channel returned a failure",
                )
            else:
                result = GatewayResult.success(
                    f"TP-{order_id}-{after_sale_id}-{self._calls}"
                )
            self._recorded[idempotency_key] = result
            return result


_GATEWAY: Optional[RefundGateway] = None


def get_gateway() -> RefundGateway:
    """Return the process-wide gateway, creating the default lazily."""
    global _GATEWAY
    if _GATEWAY is None:
        _GATEWAY = StubRefundGateway()
    return _GATEWAY


def set_gateway(gateway: Optional[RefundGateway]) -> None:
    """Swap the gateway (tests, or a real provider adapter at startup)."""
    global _GATEWAY
    _GATEWAY = gateway


def gateway_from_env() -> RefundGateway:
    """Build the gateway described by the environment.

    ``REFUND_GATEWAY_MODE``:
        ``ok`` (default) always succeeds, ``fail`` always fails, ``fail_first``
        fails the first ``REFUND_GATEWAY_FAIL_N`` calls and then succeeds.

    ``REFUND_GATEWAY_LATENCY``:
        artificial seconds of provider latency.  The multi-worker concurrency
        tests set this on purpose: it holds every request in the window between
        "claimed" and "settled", so a check-then-write race is *reproduced*
        instead of being left to luck.
    """
    mode = os.environ.get("REFUND_GATEWAY_MODE", "ok").lower()
    latency = float(os.environ.get("REFUND_GATEWAY_LATENCY", "0") or 0)
    if mode in ("fail", "always_fail"):
        return StubRefundGateway(fail_always=True, latency_seconds=latency)
    if mode == "fail_first":
        return StubRefundGateway(
            fail_first_n=int(os.environ.get("REFUND_GATEWAY_FAIL_N", "1")),
            latency_seconds=latency,
        )
    return StubRefundGateway(latency_seconds=latency)
