"""Hy3-specific pytest fixtures for the Golden test suite.

Adapts the canonical conftest (golden_answer/tests/conftest.py) to Hy3's
module layout:
  * Hy3 is a flat package (app.py / store.py / gateway.py / models.py /
    schemas.py) rooted at ``D:\\Workspace\\BE-ORDER-REFUND\\evaluation\\HY3\\final-artifact``
    (the frozen R0-R9 artifact); there is no ``app.main`` subpackage and no
    ``repository`` module.
  * The gateway is injected by mutating the module-level ``store`` singleton.
  * The two-process cluster is launched from Hy3's directory; Hy3 exposes no
    ``/health`` and no ``/users`` endpoint, so health/self-check use
    ``/openapi.json`` and Hy3's real paths instead.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest

HY3 = Path(r"D:\Workspace\BE-ORDER-REFUND\evaluation\HY3\final-artifact")
for entry in (str(HY3),):
    if entry not in sys.path:
        sys.path.insert(0, entry)

import store as hy3store                      # noqa: E402
import gateway as hy3gateway                   # noqa: E402
import app as hy3app                           # noqa: E402

HTTP_TIMEOUT = 60.0


def http_client(**kwargs) -> httpx.Client:
    kwargs.setdefault("timeout", HTTP_TIMEOUT)
    return httpx.Client(trust_env=False, **kwargs)


# --------------------------------------------------------------------------
# In-process application
# --------------------------------------------------------------------------


@pytest.fixture()
def db_file(tmp_path, monkeypatch):
    """Point Hy3's singleton store at a fresh SQLite file for this test."""
    path = tmp_path / "refund_test.db"
    monkeypatch.setenv("REFUND_DB_PATH", str(path))
    # Drop any cached thread-local connection and retarget the shared file.
    hy3store.store._local = threading.local()
    hy3store.store.db_path = str(path)
    hy3store.store.reset()
    return str(path)


class Hy3TestGateway:
    """Bridges the Golden tests' ``fail_always`` / ``fail_first_n`` controls
    onto Hy3's gateway protocol (``RefundResult``)."""

    def __init__(self) -> None:
        self.fail_always = False
        self.fail_first_n = 0
        self._calls = 0

    def refund(self, *, payment_ref: str, after_sale_id: str, amount: float):
        self._calls += 1
        if self.fail_always:
            return hy3gateway.RefundResult(success=False, error="forced failure")
        if self.fail_first_n and self._calls <= self.fail_first_n:
            return hy3gateway.RefundResult(success=False, error="forced failure (first_n)")
        return hy3gateway.RefundResult(
            success=True, channel_refund_id=f"test-{after_sale_id}-{amount}"
        )


@pytest.fixture()
def gateway():
    gw = Hy3TestGateway()
    hy3store.store.gateway = gw
    yield gw
    hy3store.store.gateway = hy3gateway.SuccessRefundGateway()


@pytest.fixture()
def client(db_file, gateway):
    from fastapi.testclient import TestClient

    with TestClient(hy3app.app) as test_client:
        yield test_client


# --------------------------------------------------------------------------
# Multi-worker cluster (two real uvicorn processes over one SQLite file)
# --------------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _log_tail(log_path: Path, limit: int = 2000) -> str:
    try:
        return log_path.read_text(encoding="utf-8", errors="replace")[-limit:]
    except OSError:
        return "<no log>"


def _wait_for_health(url: str, deadline: float, process, log_path: Path) -> None:
    last_error = "no attempt made"
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"uvicorn exited early with code {process.returncode}\n"
                f"--- {log_path} ---\n{_log_tail(log_path)}"
            )
        try:
            with http_client(timeout=1.0) as probe:
                if probe.get(f"{url}/openapi.json").status_code == 200:
                    return
        except Exception as exc:  # noqa: BLE001
            last_error = repr(exc)
        time.sleep(0.2)
    raise RuntimeError(
        f"worker at {url} never became healthy ({last_error})\n"
        f"--- {log_path} ---\n{_log_tail(log_path)}"
    )


@pytest.fixture(scope="module")
def cluster(tmp_path_factory):
    workdir = tmp_path_factory.mktemp("cluster")
    db_file = workdir / "cluster.db"
    log_dir = workdir / "logs"
    log_dir.mkdir()

    ports = [_free_port(), _free_port()]
    urls = [f"http://127.0.0.1:{port}" for port in ports]

    env = dict(os.environ)
    env["REFUND_DB_PATH"] = str(db_file)
    # No REFUND_CHANNEL_URL -> Hy3 defaults to the success gateway (happy path).
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONPATH"] = str(HY3) + os.pathsep + env.get("PYTHONPATH", "")

    processes = []
    handles = []
    log_paths = []
    try:
        for port in ports:
            log_path = log_dir / f"uvicorn-{port}.log"
            handle = open(log_path, "w", encoding="utf-8")
            handles.append(handle)
            log_paths.append(log_path)
            processes.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "app:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(port),
                        "--log-level",
                        "info",
                    ],
                    cwd=str(HY3),
                    env=env,
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                )
            )
        deadline = time.time() + 90
        for url, process, log_path in zip(urls, processes, log_paths):
            _wait_for_health(url, deadline, process, log_path)

        for url, log_path in zip(urls, log_paths):
            with http_client(timeout=5.0) as probe:
                spec = probe.get(f"{url}/openapi.json").json()
            paths = sorted(spec.get("paths", {}).keys())
            assert "/orders" in paths and "/after-sales" in paths, (
                f"worker at {url} is not serving the refund app: {paths}\n"
                f"--- {log_path} ---\n{_log_tail(log_path)}"
            )

        yield {
            "urls": urls,
            "db": str(db_file),
            "log_dir": str(log_dir),
            "workdir": str(workdir),
            "worker_pids": [process.pid for process in processes],
        }
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        for handle in handles:
            handle.close()


@pytest.fixture()
def cluster_apis(cluster):
    from harness import Api

    apis = []
    for url in cluster["urls"]:
        for _ in range(4):
            apis.append(Api(http_client(), base_url=url))
    yield apis
    for api in apis:
        api.client.close()
