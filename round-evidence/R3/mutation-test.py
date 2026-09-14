"""Differentiation check: do the golden tests actually catch the target failure modes?

Each mutant is a copy of ``golden_answer`` with one realistic weakness injected
(the kind a model plausibly produces).  If the suite is well designed, every
mutant must make at least one test FAIL, and the untouched golden answer must
pass everything.

This is the evidence behind the S5 (differentiation) gate, behind the
"failure mode -> test" mapping in ``../../evaluation-report.md`` §4, and behind
the Rubric verification notes.

Run from this directory::

    python mutation-test.py

Result of the last run is stored next to this file in ``mutation-report.json``.
Expects the same interpreter that can import the project's requirements
(``pip install -r ../../golden_answer/requirements.txt``).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[1]              # BE-ORDER-REFUND/
GOLDEN = BASE / "golden_answer"
REPORT = HERE / "mutation-report.json"
PYTHON = sys.executable

EXCLUDE_DIRS = {".venv", "data", "__pycache__", ".pytest_cache"}

# --------------------------------------------------------------------------
# Mutants: (id, description, {relative file: [(old, new), ...]}, tests to run)
# --------------------------------------------------------------------------

MUTANTS = [
    (
        "M1",
        "check-then-write race: deferred transaction, no DB-level invariant guard",
        {
            "app/repository.py": [
                ('conn.execute("BEGIN IMMEDIATE")', 'conn.execute("BEGIN")'),
                (
                    "CREATE UNIQUE INDEX IF NOT EXISTS ux_refunds_one_success",
                    "CREATE INDEX IF NOT EXISTS ux_refunds_one_success",
                ),
                ("    CHECK (refunded_amount <= paid_amount),\n", ""),
                (
                    "           AND payment_status = 'PAID'\n"
                    "           AND refunded_amount + ? <= paid_amount\n"
                    '        """,\n'
                    "        (amount, utcnow(), order_id, amount),",
                    "           AND payment_status = 'PAID'\n"
                    '        """,\n'
                    "        (amount, utcnow(), order_id),",
                ),
            ],
        },
        ["tests/test_concurrency.py", "tests/test_amount.py"],
    ),
    (
        "M2",
        "third-party failure ignored: local record always settled as successful",
        {
            "app/service.py": [
                ("        if result.ok:\n            settled = repository.mark_refund_settled(\n"
                 "                conn,\n                refund_id,\n"
                 '                RefundStatus.REFUNDED.value,',
                 "        if True:\n            settled = repository.mark_refund_settled(\n"
                 "                conn,\n                refund_id,\n"
                 '                RefundStatus.REFUNDED.value,'),
            ],
        },
        ["tests/test_failure_retry.py"],
    ),
    (
        "M3",
        "idempotency ignored: duplicate submissions create new rows",
        {
            "app/repository.py": [
                (
                    "CREATE UNIQUE INDEX IF NOT EXISTS ux_after_sales_idempotency",
                    "CREATE INDEX IF NOT EXISTS ux_after_sales_idempotency",
                ),
            ],
            "app/service.py": [
                (
                    "            if idempotency_key:\n"
                    "                existing = repository.get_after_sale_by_idempotency_key(conn, idempotency_key)",
                    "            if False:\n"
                    "                existing = repository.get_after_sale_by_idempotency_key(conn, idempotency_key)",
                ),
                (
                    '                    conn, order_id, actor["id"], amount, idempotency_key, repository.utcnow()',
                    '                    conn, order_id, actor["id"], amount, None, repository.utcnow()',
                ),
            ],
        },
        ["tests/test_idempotency.py"],
    ),
    (
        "M4",
        "ownership not verified: existence check only, no tenant isolation",
        {
            "app/auth.py": [
                (
                    '    """Ownership check shared by every read path."""\n    if is_agent(user):\n        return',
                    '    """Ownership check shared by every read path."""\n    return\n    if is_agent(user):\n        return',
                ),
            ],
        },
        ["tests/test_security.py"],
    ),
    (
        "M5",
        "illegal transition allowed: PENDING may jump straight to a refund attempt",
        {
            "app/state_machine.py": [
                (
                    'REFUND_START_STATES: FrozenSet[str] = frozenset({"APPROVED", "REFUND_FAILED"})',
                    'REFUND_START_STATES: FrozenSet[str] = frozenset(\n'
                    '    {"PENDING", "APPROVED", "REFUND_FAILED"}\n)',
                ),
            ],
        },
        ["tests/test_state_machine.py"],
    ),
    (
        "M6",
        "failed attempt keeps its reservation: quota silently burned by a failure",
        {
            "app/service.py": [
                (
                    "            # Provider refused -> the money never left, so the reservation\n"
                    "            # must go back. Otherwise a failure would silently burn quota.\n"
                    "            repository.release_refund_quota(conn, order_id, amount)",
                    "            pass  # mutant: reservation leaked on failure",
                ),
            ],
        },
        ["tests/test_failure_retry.py"],
    ),
]


def copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*EXCLUDE_DIRS))


def patch(root: Path, edits: dict) -> None:
    for relative, replacements in edits.items():
        target = root / relative
        text = target.read_text(encoding="utf-8")
        for old, new in replacements:
            if old not in text:
                raise SystemExit(f"patch anchor not found in {relative}: {old[:70]!r}")
            text = text.replace(old, new, 1)
        target.write_text(text, encoding="utf-8")


def run_tests(root: Path, tests: list) -> dict:
    db = root / "data" / "mutant.db"
    for suffix in ("", "-wal", "-shm"):
        stray = Path(str(db) + suffix)
        if stray.exists():
            stray.unlink()
    env = dict(os.environ)
    env.update(
        {
            "PYTHONPATH": str(root),
            "PYTHONUNBUFFERED": "1",
            "REFUND_DB_PATH": str(db),
            "REFUND_GATEWAY_MODE": "ok",
        }
    )
    proc = subprocess.run(
        [PYTHON, "-m", "pytest", *tests, "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        timeout=900,
    )
    combined = proc.stdout + proc.stderr
    failed_lines = [
        line.strip() for line in combined.splitlines() if line.startswith(("FAILED", "ERROR"))
    ]
    summary_lines = [
        line.strip() for line in combined.splitlines() if " passed" in line or " failed" in line
    ]
    return {
        "returncode": proc.returncode,
        "failed_tests": sorted(
            {
                line.split(" ")[1].split(" - ")[0] if " " in line else line
                for line in failed_lines
            }
        ),
        "summary": summary_lines[-1:] or [""],
    }


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="refund-mutants-"))
    report = []

    print("== baseline: unmodified golden answer ==")
    baseline_root = work / "M0-baseline"
    copy_tree(GOLDEN, baseline_root)
    baseline = run_tests(baseline_root, ["tests"])
    print("   ", baseline)
    report.append(
        {
            "id": "M0",
            "description": "unmodified golden answer (control)",
            "expected": "all tests pass",
            "tests": ["tests"],
            "returncode": baseline["returncode"],
            "summary": baseline["summary"],
            "failed_tests": baseline["failed_tests"],
            "killed": baseline["returncode"] == 0,
            "matched_expectation": baseline["returncode"] == 0,
        }
    )

    for mutant_id, description, edits, tests in MUTANTS:
        root = work / mutant_id
        copy_tree(GOLDEN, root)
        patch(root, edits)
        result = run_tests(root, tests)
        killed = result["returncode"] != 0
        print(f"== {mutant_id}: {description} -> killed={killed} {result['summary']}")
        report.append(
            {
                "id": mutant_id,
                "description": description,
                "expected": "at least one test fails",
                "tests": tests,
                "returncode": result["returncode"],
                "summary": result["summary"],
                "failed_tests": result["failed_tests"],
                "killed": killed,
                "matched_expectation": killed,
            }
        )

    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n== report: {REPORT}")
    all_ok = all(item["matched_expectation"] for item in report)
    print("== differentiation check:", "OK" if all_ok else "PROBLEM")
    shutil.rmtree(work, ignore_errors=True)
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
