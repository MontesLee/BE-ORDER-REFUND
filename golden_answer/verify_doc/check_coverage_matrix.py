"""Assert the golden suite still contains everything the benchmark requires.

Two things are checked against the *actually collected* pytest nodes (not against
a document claiming what exists):

1. every golden test ``T01``–``T18`` from the benchmark specification is present;
2. every test category demanded by R8 has at least one real test behind it.

Usage::

    python verify_doc/check_coverage_matrix.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: golden test id -> (category, node id, human description)
REQUIRED: dict = {
    "T01": ("business", "tests/test_refund.py::test_normal_full_refund", "normal refund"),
    "T02": ("business", "tests/test_refund.py::test_unpaid_order_cannot_be_refunded", "unpaid refund"),
    "T03": ("business", "tests/test_amount.py::test_multiple_partial_refunds", "multiple partial refunds"),
    "T04": ("business", "tests/test_amount.py::test_over_refund_is_rejected", "over-refund"),
    "T05": ("third-party", "tests/test_failure_retry.py::test_failed_refund_does_not_consume_quota", "failed refund does not consume quota"),
    "T06": ("idempotency", "tests/test_idempotency.py::test_duplicate_submit_creates_one_after_sale", "duplicate submission"),
    "T07": ("idempotency", "tests/test_idempotency.py::test_duplicate_execute_creates_one_refund", "duplicate execute"),
    "T08": ("state", "tests/test_state_machine.py::test_illegal_state_transitions_rejected", "illegal state"),
    "T09": ("third-party", "tests/test_failure_retry.py::test_failed_refund_can_be_retried", "failure retry"),
    "T10": ("state", "tests/test_state_machine.py::test_refunded_is_terminal", "success then no retry"),
    "T11": ("third-party", "tests/test_failure_retry.py::test_third_party_failure_is_not_marked_success", "third-party failure"),
    "T12": ("third-party", "tests/test_failure_retry.py::test_incident_regression_provider_failure", "incident regression"),
    "T13": ("concurrency", "tests/test_concurrency.py::test_concurrent_same_after_sale", "concurrent same AfterSale"),
    "T14": ("concurrency", "tests/test_concurrency.py::test_concurrent_multiple_after_sales", "concurrent multiple AfterSale"),
    "T15": ("security", "tests/test_security.py::test_unauthorized_order_access", "unauthorized order"),
    "T16": ("security", "tests/test_security.py::test_unauthorized_after_sale_access", "unauthorized AfterSale"),
    "T17": ("security", "tests/test_security.py::test_normal_user_cannot_execute_refund", "protected refund execution"),
    "T18": ("performance", "tests/test_performance.py::test_indexed_queries_and_bounded_loading", "index + bounded loading"),
}

#: R8 categories -> golden ids that must exist for the category to be covered
CATEGORIES = {
    "business": ["T01", "T02", "T03", "T04"],
    "state": ["T08", "T10"],
    "idempotency": ["T06", "T07"],
    "concurrency": ["T13", "T14"],
    "third-party": ["T05", "T09", "T11", "T12"],
    "security": ["T15", "T16", "T17"],
}


def collected_nodes() -> set:
    # ``-o addopts=`` clears the ``-q`` already declared in pytest.ini; doubled
    # quiet flags make pytest print per-file counts instead of node ids.
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests",
            "--collect-only",
            "-q",
            "--no-header",
            "-o",
            "addopts=",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=300,
    )
    nodes = set()
    for line in proc.stdout.splitlines():
        line = line.strip()
        if "::" in line and line.startswith("tests/"):
            nodes.add(line.split(" ")[0])
    return nodes


def main() -> int:
    nodes = collected_nodes()
    print(f"== collected {len(nodes)} test nodes from {ROOT / 'tests'}")
    print()

    missing = []
    for golden_id in sorted(REQUIRED, key=lambda k: int(k[1:])):
        category, node, description = REQUIRED[golden_id]
        present = node in nodes
        if not present:
            missing.append((golden_id, node))
        print(f"[{'OK  ' if present else 'MISS'}] {golden_id} {description:<36} {node}  ({category})")

    print()
    category_ok = True
    for category, golden_ids in CATEGORIES.items():
        absent = [g for g in golden_ids if REQUIRED[g][1] not in nodes]
        ok = not absent
        category_ok = category_ok and ok
        print(
            f"[{'OK  ' if ok else 'MISS'}] category {category:<12} "
            f"{len(golden_ids) - len(absent)}/{len(golden_ids)} golden tests present"
        )

    print()
    if not missing and category_ok:
        print(f"== coverage OK: {len(REQUIRED)}/{len(REQUIRED)} golden tests, "
              f"{len(CATEGORIES)}/{len(CATEGORIES)} categories")
        return 0
    print(f"== coverage INCOMPLETE: missing {missing}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
