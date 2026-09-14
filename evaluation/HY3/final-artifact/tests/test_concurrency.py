"""并发安全测试（多 Worker 场景）。

目标：验证当多个 Worker 同时处理
  1) 同一个 AfterSale；
  2) 同一 Order 下的多个 AfterSale；
时，仍满足：
  * 同一个 AfterSale 最多一个成功退款；
  * 成功退款累计金额不超过订单实际支付金额。

当前数据落在共享的 SQLite 文件，退款在 `store.refund_transaction` 内的单个
`BEGIN IMMEDIATE` 事务 + 条件 UPDATE 中完成。本文件用两种方式触发真实并发：

  A) 线程级：同进程内多个线程各自持独立 DB 连接，直接调用 refund_transaction，
     并发在数据库层真实发生（非被单把 Python 锁串行化）。
  B) 进程级：派生多个进程，各自连接同一个 SQLite 文件，模拟真正的多 Worker。

所有断言都检查「最终业务结果」（订单/售后的落库状态与累计退款金额），
而非仅仅检查请求是否被同时发出。
"""
import multiprocessing as mp
import os
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import List

import pytest
from fastapi.testclient import TestClient

from app import app
from store import Store, Order, AfterSale, OrderStatus, AfterSaleStatus

# 线程级测试复用全局 store（默认落在 tempfile 的共享 SQLite 文件）。
from store import store


def _now():
    return datetime.now(timezone.utc)


def _paid_order(oid: str, amount: float = 100.0):
    store.insert_order(
        Order(
            id=oid,
            user_id="u",
            amount=amount,
            status=OrderStatus.PAID,
            created_at=_now(),
        )
    )


def _approved_after_sale(aid: str, oid: str):
    store.insert_after_sale(
        AfterSale(
            id=aid,
            order_id=oid,
            reason="r",
            status=AfterSaleStatus.APPROVED,
            created_at=_now(),
        )
    )


# ---------------------------------------------------------------------------
# A) 线程级（同进程，多连接，真实数据库并发）
# ---------------------------------------------------------------------------


def test_thread_concurrent_same_after_sale_only_one_refund():
    """同一个 AfterSale 被 10 个线程同时退款：最多一个成功，累计金额不被翻倍。"""
    store.reset()
    oid, aid = "o1", "a1"
    _paid_order(oid, amount=100.0)
    _approved_after_sale(aid, oid)

    N = 10
    results: List = [None] * N

    def work(i: int):
        sc, body = store.refund_transaction(aid, None, None)
        results[i] = (sc, body)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # —— 实际业务结果校验 ——
    order = store.get_order(oid)
    assert order.refunded_amount == 100.0, "累计退款不应被翻倍"
    assert order.status == OrderStatus.REFUNDED
    asale = store.get_after_sale(aid)
    assert asale.status == AfterSaleStatus.REFUNDED
    assert asale.refund_amount == 100.0
    # 所有线程都拿到 200（赢家写入 / 输家返回既有结果），但金额恒为 100
    for sc, body in results:
        assert sc == 200
        assert body["refund_amount"] == 100.0


def test_thread_concurrent_multiple_after_sales_over_budget():
    """同一 Order 下 5 个 AfterSale 各想退全额 100（共 500 >> 100）：
    恰好一个成功，其余因额度不足被拒，累计不超过订单金额。"""
    store.reset()
    oid = "o2"
    _paid_order(oid, amount=100.0)
    aids = [f"a{i}" for i in range(5)]
    for aid in aids:
        _approved_after_sale(aid, oid)

    N = len(aids)
    results: List = [None] * N

    def work(i: int):
        # 每个售后都申请退全额 100
        sc, body = store.refund_transaction(aids[i], 100.0, None)
        results[i] = (sc, body)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    order = store.get_order(oid)
    assert order.refunded_amount == 100.0, "累计退款不得超过订单金额"
    assert order.status == OrderStatus.REFUNDED

    ok = [r for r in results if r[0] == 200]
    rejected = [r for r in results if r[0] == 409]
    assert len(ok) == 1, f"恰好一个售后应成功退款，实际 {len(ok)}"
    assert len(rejected) == 4, f"其余应因超额被拒，实际 {len(rejected)}"


def test_thread_concurrent_multiple_after_sales_exact_fill():
    """同一 Order 下 2 个 AfterSale 分别退 60 / 40（正好凑满 100）：
    两个都成功，累计恰为订单金额。"""
    store.reset()
    oid = "o3"
    _paid_order(oid, amount=100.0)
    _approved_after_sale("a0", oid)
    _approved_after_sale("a1", oid)

    args = [("a0", 60.0), ("a1", 40.0)]
    results: List = [None] * 2

    def work(i: int):
        aid, amt = args[i]
        sc, body = store.refund_transaction(aid, amt, None)
        results[i] = (sc, body)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    order = store.get_order(oid)
    assert order.refunded_amount == 100.0
    assert order.status == OrderStatus.REFUNDED
    for sc, _ in results:
        assert sc == 200


def test_http_concurrent_same_after_sale_only_one_refund():
    """经 HTTP 接口并发退款同一个 AfterSale：验证端点层同样安全。"""
    store.reset()
    oid, aid = "o4", "a4"
    _paid_order(oid, amount=100.0)
    _approved_after_sale(aid, oid)

    client = TestClient(app)

    def fire(_):
        return client.post(f"/after-sales/{aid}/refund")

    with ThreadPoolExecutor(max_workers=10) as ex:
        responses = list(ex.map(fire, range(10)))

    # 业务结果：累计退款恒为 100
    order = store.get_order(oid)
    assert order.refunded_amount == 100.0
    assert order.status == OrderStatus.REFUNDED
    for r in responses:
        assert r.status_code == 200
        assert r.json()["refund_amount"] == 100.0


# ---------------------------------------------------------------------------
# B) 进程级（多进程共享同一 SQLite 文件，模拟真实多 Worker）
# ---------------------------------------------------------------------------


def _mp_worker(db_path: str, after_sale_id: str, requested, key: str):
    """在独立的 Worker 进程中执行一次退款。"""
    s = Store(db_path)
    s.refund_transaction(after_sale_id, requested, key)


def _mp_setup(db_path: str, oid: str, amount: float, aids):
    s = Store(db_path)
    s.reset()
    s.insert_order(
        Order(
            id=oid,
            user_id="u",
            amount=amount,
            status=OrderStatus.PAID,
            created_at=_now(),
        )
    )
    for aid in aids:
        s.insert_after_sale(
            AfterSale(
                id=aid,
                order_id=oid,
                reason="r",
                status=AfterSaleStatus.APPROVED,
                created_at=_now(),
            )
        )


def _run_processes(db_path, jobs):
    procs = [
        mp.Process(target=_mp_worker, args=(db_path, aid, req, key))
        for (aid, req, key) in jobs
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30)
    # 子进程退出后，新连接读取最终落库状态
    return Store(db_path)


def test_multiprocess_same_after_sale_only_one_refund():
    db = os.path.join(tempfile.gettempdir(), f"hy3_mp_same_{os.getpid()}.db")
    if os.path.exists(db):
        os.remove(db)
    _mp_setup(db, "o", 100.0, ["a1"])
    jobs = [("a1", None, f"k{i}") for i in range(6)]
    final = _run_processes(db, jobs)

    order = final.get_order("o")
    assert order.refunded_amount == 100.0, "跨进程：同一售后不应被重复退款"
    assert order.status == OrderStatus.REFUNDED
    asale = final.get_after_sale("a1")
    assert asale.status == AfterSaleStatus.REFUNDED
    assert asale.refund_amount == 100.0


def test_multiprocess_multiple_after_sales_over_budget():
    db = os.path.join(tempfile.gettempdir(), f"hy3_mp_multi_{os.getpid()}.db")
    if os.path.exists(db):
        os.remove(db)
    aids = [f"a{i}" for i in range(5)]
    _mp_setup(db, "o", 100.0, aids)
    # 5 个进程各退全额 100（共 500 >> 100）
    jobs = [(aid, 100.0, f"k-{aid}") for aid in aids]
    final = _run_processes(db, jobs)

    order = final.get_order("o")
    assert order.refunded_amount == 100.0, "跨进程：累计退款不得超过订单金额"
    assert order.status == OrderStatus.REFUNDED
    refunded = [a for a in aids if final.get_after_sale(a).status == AfterSaleStatus.REFUNDED]
    assert len(refunded) == 1, f"跨进程：恰好一个售后应成功退款，实际 {len(refunded)}"


