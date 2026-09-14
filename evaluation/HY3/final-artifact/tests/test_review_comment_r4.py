"""R4 回顾评论的回归测试（Review Comment 是否成立）。

Review Comment:
  "退款执行前会先读取售后状态，再决定是否退款。如果两个 Worker 同时读取到
   相同状态，是否可能重复退款？累计退款金额的检查是否也存在类似问题？"

结论：该评论在「当前实现」下不成立（NOT 成立）。
原因（详见 store.py）：
  * 读状态 -> 判断 -> 写回，全部落在 `refund_transaction` 内的单个
    `BEGIN IMMEDIATE` 事务中（store.py:258）。`BEGIN IMMEDIATE` 在事务一开始就
    取得 SQLite 写锁，使多个 Worker 的退款被数据库层串行化，因此"读状态"并非一个
    脱离锁的、可被并发穿插的独立步骤；
  * 即便串行化被绕过，还叠加两层"条件 UPDATE"做二次保护：
      - 售后：`UPDATE after_sales ... WHERE id=? AND status='APPROVED'`
        （store.py:319），只有真正把 APPROVED 翻成 REFUNDED 的那个 Worker 成功；
        输家读到的已是 REFUNDED，直接返回既有结果；
      - 累计额度：`UPDATE orders ... WHERE id=? AND refunded_amount + ? <= amount`
        （store.py:340），SQL 层原子"校验并写回"。

本文件用两种最贴近评论原话的场景做回归测试，证明"两个 Worker 同时读到相同状态"
并不会导致重复退款，也不会突破累计退款上限：

  A) 线程级 + 同步屏障：让 N 个线程在同一时刻同时发起退款（最大化"同时读到
     APPROVED"的概率），断言累计金额不被翻倍；
  B) 进程级：派生多个进程各自连同一 SQLite 文件，模拟真正的"两个 Worker"。
"""
import multiprocessing as mp
import os
import tempfile
import threading
from datetime import datetime, timezone
from typing import List, Tuple

import pytest
from fastapi.testclient import TestClient

from app import app
from store import Store, Order, AfterSale, OrderStatus, AfterSaleStatus
from store import store  # 全局单例（默认落在共享 tempfile SQLite 文件）


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
# A) 线程级 + 同步屏障：最大化"同时读到相同状态"的概率
# ---------------------------------------------------------------------------


def test_review_comment_simultaneous_read_same_after_sale_no_duplicate_refund():
    """两个（N 个）Worker 同时读到 APPROVED 并同时尝试退款同一售后：
    断言不重复退款，累计金额恒为订单金额。"""
    store.reset()
    oid, aid = "r4o1", "r4a1"
    _paid_order(oid, amount=100.0)
    _approved_after_sale(aid, oid)

    N = 8
    barrier = threading.Barrier(N)
    results: List[Tuple[int, dict]] = [None] * N  # type: ignore

    def work(i: int):
        barrier.wait()  # 所有线程在此对齐，最大化"同时读到 APPROVED"的概率
        sc, body = store.refund_transaction(aid, None, None)
        results[i] = (sc, body)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # —— 业务结果校验 ——
    order = store.get_order(oid)
    assert order.refunded_amount == 100.0, "累计退款不应被翻倍（评论担心的重复退款未发生）"
    assert order.status == OrderStatus.REFUNDED
    asale = store.get_after_sale(aid)
    assert asale.status == AfterSaleStatus.REFUNDED
    assert asale.refund_amount == 100.0
    # 所有线程都拿到 200（赢家写入 / 输家返回既有结果），但金额恒为 100
    for sc, body in results:
        assert sc == 200
        assert body["refund_amount"] == 100.0


def test_review_comment_cumulative_cap_under_simultaneous_reads():
    """两个 Worker 同时读到各自 APPROVED，且都按"剩余全额"申请退款：
    断言累计退款不超过订单金额（评论担心的累计额度问题未发生）。"""
    store.reset()
    oid = "r4o2"
    _paid_order(oid, amount=100.0)
    aids = ["r4a0", "r4a1"]
    for aid in aids:
        _approved_after_sale(aid, oid)

    # 两个线程各按"剩余全部"退款（都读到的剩余最初都是 100）
    barrier = threading.Barrier(2)
    results: List[Tuple[int, dict]] = [None] * 2  # type: ignore

    def work(i: int):
        barrier.wait()
        sc, body = store.refund_transaction(aids[i], None, None)
        results[i] = (sc, body)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    order = store.get_order(oid)
    assert order.refunded_amount == 100.0, "累计退款不得超过订单金额"
    assert order.status == OrderStatus.REFUNDED
    refunded = [
        a for a in aids if store.get_after_sale(a).status == AfterSaleStatus.REFUNDED
    ]
    assert len(refunded) == 1, f"恰好一个售后应成功退款，实际 {len(refunded)}"


# ---------------------------------------------------------------------------
# B) 进程级：模拟真正的"两个 Worker"各自连同一 SQLite 文件
# ---------------------------------------------------------------------------


def _rc_worker(db_path: str, after_sale_id: str, requested):
    """独立 Worker 进程中执行一次退款。"""
    s = Store(db_path)
    s.refund_transaction(after_sale_id, requested, None)


def _rc_setup(db_path: str, oid: str, amount: float, aids):
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


def test_review_comment_two_workers_same_after_sale_no_double():
    """真正的两个 Worker 进程同时退款同一售后：断言不重复退款。"""
    db = os.path.join(tempfile.gettempdir(), f"hy3_rc_same_{os.getpid()}.db")
    if os.path.exists(db):
        os.remove(db)
    _rc_setup(db, "r4o", 100.0, ["r4a"])

    procs = [
        mp.Process(target=_rc_worker, args=(db, "r4a", None)),
        mp.Process(target=_rc_worker, args=(db, "r4a", None)),
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30)

    final = Store(db)
    order = final.get_order("r4o")
    assert order.refunded_amount == 100.0, "跨进程：同一售后不应被重复退款"
    assert order.status == OrderStatus.REFUNDED
    asale = final.get_after_sale("r4a")
    assert asale.status == AfterSaleStatus.REFUNDED
    assert asale.refund_amount == 100.0


def test_review_comment_two_workers_cumulative_cap_no_breach():
    """真正的两个 Worker 进程各自退款一个售后、都按剩余全额申请：
    断言累计退款不超过订单金额。"""
    db = os.path.join(tempfile.gettempdir(), f"hy3_rc_cap_{os.getpid()}.db")
    if os.path.exists(db):
        os.remove(db)
    aids = ["r4a0", "r4a1"]
    _rc_setup(db, "r4o", 100.0, aids)

    procs = [
        mp.Process(target=_rc_worker, args=(db, "r4a0", None)),
        mp.Process(target=_rc_worker, args=(db, "r4a1", None)),
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30)

    final = Store(db)
    order = final.get_order("r4o")
    assert order.refunded_amount == 100.0, "跨进程：累计退款不得超过订单金额"
    assert order.status == OrderStatus.REFUNDED
    refunded = [
        a for a in aids if final.get_after_sale(a).status == AfterSaleStatus.REFUNDED
    ]
    assert len(refunded) == 1, f"跨进程：恰好一个售后应成功退款，实际 {len(refunded)}"
