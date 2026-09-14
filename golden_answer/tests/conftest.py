"""Shared pytest fixtures.

Two execution modes are supported:

* ``client``  -- in-process ``TestClient`` on a throw-away SQLite file. Used by
  every functional test, and fast enough to run on every change.
* ``cluster`` -- **two real uvicorn processes** sharing one SQLite file. Used by
  the concurrency tests, because a process-local ``threading.Lock`` would pass
  an in-process test and still be wrong in production. Concurrency must be
  proven across processes or it is not proven at all.

Proxy note
----------
Every HTTP client here is created with ``trust_env=False``.  A CI/dev shell may
export ``HTTP_PROXY`` (pointing at a local service gateway); an HTTP client that
honours it will send an absolute-form request line to a loopback address on
*reused* connections, which any server correctly rejects as an unknown path.
Loopback traffic must never be routed through an ambient proxy, so the suite
opts out explicitly instead of depending on ``NO_PROXY``.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = Path(__file__).resolve().parent
for entry in (str(TESTS_DIR), str(ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from app import refund_gateway, repository  # noqa: E402

HTTP_TIMEOUT = 60.0


def http_client(**kwargs) -> httpx.Client:
    """A loopback-safe client: no ambient proxy, no env-derived defaults."""
    kwargs.setdefault("timeout", HTTP_TIMEOUT)
    return httpx.Client(trust_env=False, **kwargs)


# --------------------------------------------------------------------------
# In-process application
# --------------------------------------------------------------------------


@pytest.fixture()
def db_file(tmp_path, monkeypatch):
    """Point the application at a fresh SQLite file for this test."""
    path = tmp_path / "refund_test.db"
    monkeypatch.setenv("REFUND_DB_PATH", str(path))
    repository.init_schema()
    return str(path)


@pytest.fixture()
def gateway():
    """A deterministic, scriptable third-party gateway wired into the app."""
    from app.main import app

    stub = refund_gateway.StubRefundGateway()
    app.state.gateway = stub
    refund_gateway.set_gateway(stub)
    yield stub
    app.state.gateway = None
    refund_gateway.set_gateway(refund_gateway.StubRefundGateway())


@pytest.fixture()
def client(db_file, gateway):
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


# --------------------------------------------------------------------------
# Multi-worker cluster
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


def _wait_for_health(
    url: str, deadline: float, process: subprocess.Popen, log_path: Path
) -> None:
    last_error = "no attempt made"
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"uvicorn exited early with code {process.returncode}\n"
                f"--- {log_path} ---\n{_log_tail(log_path)}"
            )
        try:
            with http_client(timeout=1.0) as probe:
                if probe.get(f"{url}/health").status_code == 200:
                    return
        except Exception as exc:  # noqa: BLE001 - startup race, retry
            last_error = repr(exc)
        time.sleep(0.2)
    raise RuntimeError(
        f"worker at {url} never became healthy ({last_error})\n"
        f"--- {log_path} ---\n{_log_tail(log_path)}"
    )


@pytest.fixture(scope="module")
def cluster(tmp_path_factory):
    """Two independent uvicorn workers over one SQLite database file."""
    workdir = tmp_path_factory.mktemp("cluster")
    db_file = workdir / "cluster.db"
    log_dir = workdir / "logs"
    log_dir.mkdir()

    ports = [_free_port(), _free_port()]
    urls = [f"http://127.0.0.1:{port}" for port in ports]

    env = dict(os.environ)
    env["REFUND_DB_PATH"] = str(db_file)
    env["REFUND_GATEWAY_MODE"] = "ok"
    # Widen the claim -> settle window on purpose. Without it the race is a
    # few hundred microseconds wide and a broken implementation can pass by
    # luck, which would destroy the differentiation this round exists for.
    env["REFUND_GATEWAY_LATENCY"] = os.environ.get("CLUSTER_GATEWAY_LATENCY", "0.15")
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")

    processes = []
    handles = []
    log_paths = []
    try:
        for port in ports:
            log_path = log_dir / f"uvicorn-{port}.log"
            log_paths.append(log_path)
            handle = open(log_path, "w", encoding="utf-8")
            handles.append(handle)
            processes.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "app.main:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(port),
                        "--log-level",
                        "info",
                    ],
                    cwd=str(ROOT),
                    env=env,
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                )
            )
        deadline = time.time() + 90
        for url, process, log_path in zip(urls, processes, log_paths):
            _wait_for_health(url, deadline, process, log_path)

        # Self-check: the workers must be serving *this* application, not some
        # other process that happens to answer /health.
        for url, log_path in zip(urls, log_paths):
            with http_client(timeout=5.0) as probe:
                spec = probe.get(f"{url}/openapi.json").json()
            paths = sorted(spec.get("paths", {}).keys())
            assert "/users" in paths and "/orders" in paths, (
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
            except subprocess.TimeoutExpired:  # pragma: no cover - defensive
                process.kill()
                process.wait(timeout=5)
        for handle in handles:
            handle.close()


@pytest.fixture()
def cluster_apis(cluster):
    """One :class:`harness.Api` per worker slot, spread evenly over the workers."""
    from harness import Api

    apis = []
    for url in cluster["urls"]:
        for _ in range(4):
            apis.append(Api(http_client(), base_url=url))
    yield apis
    for api in apis:
        api.client.close()
