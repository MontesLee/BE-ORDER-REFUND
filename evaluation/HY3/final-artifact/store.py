"""SQLite 存储层（多 Worker 安全）。

为什么需要改：上一版使用进程内存字典 + 一把 `threading.Lock`，但那把锁是
「进程内」的。当服务以多个 Worker（多个进程）部署时，每个 Worker 各持一份
内存数据与各自的锁，锁无法跨进程保护，于是会出现：

  * 两个 Worker 同时处理同一个 AfterSale -> 均读到 APPROVED -> 重复退款；
  * 两个 Worker 同时处理同一 Order 下的多个 AfterSale -> 均按同一剩余额度累加
    -> 累计退款金额突破订单实付金额。

本版把数据落到一个所有 Worker 共享的 SQLite 文件，并用「数据库层」的并发控制
保证上面两条业务不变量在多个进程下依然成立：

  * WAL 日志模式 + 较大的 busy_timeout：读写并发更友好，写冲突时自动等待而非报错；
  * 退款等写操作使用 `BEGIN IMMEDIATE` 获取数据库写锁，把并发写入串行化；
  * 关键更新使用「条件 UPDATE（WHERE 旧状态/旧额度）」+ 幂等键唯一约束，
    作为数据库层的二次保护（即便将来去掉全局锁也不会破坏不变量）。

测试可通过 Store.reset() 清空数据；也可通过 REFUND_DB_PATH 指定数据库文件，
便于多进程并发测试使用独立的临时库。
"""
import json
import os
import sqlite3
import tempfile
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from models import Order, AfterSale, OrderStatus, AfterSaleStatus
from gateway import build_refund_gateway, RefundGateway, RefundResult


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(s) if s else None


_SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL,
    amount        REAL NOT NULL,
    status        TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    paid_at       TEXT,
    refunded_amount REAL NOT NULL DEFAULT 0,
    refunded_at   TEXT
);
CREATE TABLE IF NOT EXISTS after_sales (
    id            TEXT PRIMARY KEY,
    order_id      TEXT NOT NULL,
    reason        TEXT NOT NULL,
    status        TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    reviewed_at   TEXT,
    refund_amount REAL,
    reviewer_note TEXT
);
CREATE TABLE IF NOT EXISTS idempotency (
    key         TEXT PRIMARY KEY,
    status_code INTEGER NOT NULL,
    body        TEXT NOT NULL
);

-- 性能：随着 after_sales / idempotency 行数增长，退款事务与外部查询都按
-- order_id / status / key 做点查或过滤；缺少索引会导致全表扫描。这里的索引
-- 把点查/过滤维持在 O(log n)，避免「Refund 数量增长后的明显查询退化」。
CREATE INDEX IF NOT EXISTS idx_after_sales_order_id ON after_sales(order_id);
CREATE INDEX IF NOT EXISTS idx_after_sales_status ON after_sales(status);
CREATE INDEX IF NOT EXISTS idx_idempotency_key ON idempotency(key);
"""

_DEFAULT_DB = os.environ.get(
    "REFUND_DB_PATH", os.path.join(tempfile.gettempdir(), "hy3_refund.db")
)


def _row_to_order(row: sqlite3.Row) -> Order:
    return Order(
        id=row["id"],
        user_id=row["user_id"],
        amount=round(row["amount"], 2),
        status=OrderStatus(row["status"]),
        created_at=_parse_dt(row["created_at"]),
        paid_at=_parse_dt(row["paid_at"]),
        refunded_amount=round(row["refunded_amount"], 2),
        refunded_at=_parse_dt(row["refunded_at"]),
    )


def _row_to_after_sale(row: sqlite3.Row) -> AfterSale:
    return AfterSale(
        id=row["id"],
        order_id=row["order_id"],
        reason=row["reason"],
        status=AfterSaleStatus(row["status"]),
        created_at=_parse_dt(row["created_at"]),
        reviewed_at=_parse_dt(row["reviewed_at"]),
        refund_amount=(
            round(row["refund_amount"], 2) if row["refund_amount"] is not None else None
        ),
        reviewer_note=row["reviewer_note"],
    )


class Store:
    def __init__(
        self, db_path: Optional[str] = None, gateway: Optional[RefundGateway] = None
    ) -> None:
        self.db_path = db_path or _DEFAULT_DB
        # 第三方退款渠道（可替换抽象）。默认按环境变量选择（未配置则占位成功网关），
        # 测试可显式注入 FakeRefundGateway 以确定性模拟成功/失败。
        self.gateway: RefundGateway = gateway or build_refund_gateway()
        # 每个线程一条连接：避免 sqlite3 的「跨线程使用」限制，同时让并发
        # 真正发生在数据库层（而不是被单把 Python 锁串行化）。
        self._local = threading.local()

    # ---- 连接管理（线程本地 + WAL + busy_timeout） ----

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(
                self.db_path, timeout=15.0, check_same_thread=False
            )
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=15000")
            conn.row_factory = sqlite3.Row
            conn.executescript(_SCHEMA)
            self._local.conn = conn
        return conn

    # ---- 数据维护 ----

    def reset(self) -> None:
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM idempotency")
        cur.execute("DELETE FROM after_sales")
        cur.execute("DELETE FROM orders")
        conn.commit()

    def insert_order(self, order: Order) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT INTO orders(id,user_id,amount,status,created_at,paid_at,"
            "refunded_amount,refunded_at) VALUES(?,?,?,?,?,?,?,?)",
            (
                order.id,
                order.user_id,
                order.amount,
                order.status.value,
                _now_iso() if order.created_at is None else order.created_at.isoformat(),
                order.paid_at.isoformat() if order.paid_at else None,
                order.refunded_amount,
                order.refunded_at.isoformat() if order.refunded_at else None,
            ),
        )
        conn.commit()

    def save_order(self, order: Order) -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE orders SET user_id=?, amount=?, status=?, created_at=?, "
            "paid_at=?, refunded_amount=?, refunded_at=? WHERE id=?",
            (
                order.user_id,
                order.amount,
                order.status.value,
                order.created_at.isoformat() if order.created_at else _now_iso(),
                order.paid_at.isoformat() if order.paid_at else None,
                order.refunded_amount,
                order.refunded_at.isoformat() if order.refunded_at else None,
                order.id,
            ),
        )
        conn.commit()

    def insert_after_sale(self, asale: AfterSale) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT INTO after_sales(id,order_id,reason,status,created_at,"
            "reviewed_at,refund_amount,reviewer_note) VALUES(?,?,?,?,?,?,?,?)",
            (
                asale.id,
                asale.order_id,
                asale.reason,
                asale.status.value,
                asale.created_at.isoformat() if asale.created_at else _now_iso(),
                asale.reviewed_at.isoformat() if asale.reviewed_at else None,
                asale.refund_amount,
                asale.reviewer_note,
            ),
        )
        conn.commit()

    def save_after_sale(self, asale: AfterSale) -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE after_sales SET order_id=?, reason=?, status=?, created_at=?, "
            "reviewed_at=?, refund_amount=?, reviewer_note=? WHERE id=?",
            (
                asale.order_id,
                asale.reason,
                asale.status.value,
                asale.created_at.isoformat() if asale.created_at else _now_iso(),
                asale.reviewed_at.isoformat() if asale.reviewed_at else None,
                asale.refund_amount,
                asale.reviewer_note,
                asale.id,
            ),
        )
        conn.commit()

    def get_order(self, order_id: str) -> Optional[Order]:
        row = self._conn().execute(
            "SELECT * FROM orders WHERE id=?", (order_id,)
        ).fetchone()
        return _row_to_order(row) if row else None

    def list_orders(
        self,
        user_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Order]:
        # 无界加载大量数据：限制返回行数（limit/offset 由调用方传入，默认 100）。
        limit = max(1, min(int(limit), 1000))
        offset = max(0, int(offset))
        if user_id is not None:
            rows = self._conn().execute(
                "SELECT * FROM orders WHERE user_id=? ORDER BY created_at LIMIT ? OFFSET ?",
                (user_id, limit, offset),
            ).fetchall()
        else:
            rows = self._conn().execute(
                "SELECT * FROM orders ORDER BY created_at LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [_row_to_order(r) for r in rows]

    def get_after_sale(self, after_sale_id: str) -> Optional[AfterSale]:
        row = self._conn().execute(
            "SELECT * FROM after_sales WHERE id=?", (after_sale_id,)
        ).fetchone()
        return _row_to_after_sale(row) if row else None

    def list_after_sales(
        self,
        user_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AfterSale]:
        # 无界加载大量数据：限制返回行数。按 user_id 过滤时通过 JOIN orders
        # 一次完成（避免「先取全部 after_sales 再逐个查 order」的 N+1）。
        limit = max(1, min(int(limit), 1000))
        offset = max(0, int(offset))
        if user_id is not None:
            rows = self._conn().execute(
                "SELECT after_sales.* FROM after_sales "
                "JOIN orders ON after_sales.order_id = orders.id "
                "WHERE orders.user_id=? ORDER BY after_sales.created_at LIMIT ? OFFSET ?",
                (user_id, limit, offset),
            ).fetchall()
        else:
            rows = self._conn().execute(
                "SELECT * FROM after_sales ORDER BY created_at LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [_row_to_after_sale(r) for r in rows]

    # ---- 幂等键（跨 Worker 共享） ----

    def get_idempotency(self, key: str) -> Optional[Tuple[int, dict]]:
        row = self._conn().execute(
            "SELECT status_code, body FROM idempotency WHERE key=?", (key,)
        ).fetchone()
        if row is None:
            return None
        return row["status_code"], json.loads(row["body"])

    # ---- 退款核心：数据库层原子 + 串行化，跨 Worker 安全 ----

    def _await_settlement(
        self,
        cur: sqlite3.Cursor,
        after_sale_id: str,
    ) -> Tuple[int, dict]:
        """另一个 Worker 已认领（status=REFUNDING）并正在调用外部渠道时，
        本事务外轮询其最终落库状态并返回，避免重复发起退款。"""
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            row = cur.execute(
                "SELECT * FROM after_sales WHERE id=?", (after_sale_id,)
            ).fetchone()
            if row is None:
                return 404, {"detail": "after-sale not found"}
            st = AfterSaleStatus(row["status"])
            if st == AfterSaleStatus.REFUNDED:
                return 200, _row_to_after_sale(row).model_dump(mode="json")
            if st == AfterSaleStatus.REFUND_FAILED:
                return 502, {
                    "detail": "third-party refund failed",
                    **_row_to_after_sale(row).model_dump(mode="json"),
                }
            # 仍在 REFUNDING：短暂等待后重试
            time.sleep(0.02)
        return 409, {"detail": "refund already in progress by another worker"}

    def refund_transaction(
        self,
        after_sale_id: str,
        requested: Optional[float],
        idempotency_key: Optional[str],
    ) -> Tuple[int, dict]:
        """执行退款（两阶段，缩短数据库写锁持有时间）。

        旧实现把「调用第三方渠道」放在 `BEGIN IMMEDIATE` 事务内部，意味着在等待
        外部网络（可能是数秒的 HTTP 调用）期间一直持有 SQLite 写锁，所有退款被
        串行化，且一旦渠道调用先于额度校验失败，还可能出现「已向渠道扣款但本地回滚」
        的重复扣款隐患。

        本版改为两阶段、把「慢」的渠道调用移到锁外：

          阶段 1（短事务 `BEGIN IMMEDIATE`）：
            幂等去重 -> 资源级去重 -> 「认领」售后（APPROVED/REFUND_FAILED 原子翻成
            REFUNDING）-> 校验并「预留」额度（条件 UPDATE orders）。
            认领 + 预留都在锁内、无网络等待，因此写锁仅在极短时间内持有。
            只有成功预留额度的工作者才会去调用外部渠道。

          阶段 2（无锁）：调用第三方支付渠道。此时不持有任何数据库锁，不会阻塞
            其它退款。

          阶段 3（短事务 `BEGIN IMMEDIATE`）：根据渠道结果写回——
            成功 -> AfterSale 置 REFUNDED（订单额度已在阶段 1 预留好）；
            失败 -> 释放阶段 1 预留的额度并把 AfterSale 置 REFUND_FAILED（可重试）。

        一致性约束（由 IMMEDIATE 事务 + 条件 UPDATE + 唯一幂等键保证，跨 Worker 安全）：
          * 同一 AfterSale 最多成功退款一次（认领保证仅有 1 个工作者驱动渠道）；
          * 累计退款不超过订单实付金额（额度在调用渠道前即预留，且仅成功结果缓存）；
          * 重复/重放请求不重复退款（幂等键 + 资源级去重）；
          * 渠道失败绝不污染订单累计金额（阶段 3 释放预留额度，且不缓存幂等键）。
        """
        conn = self._conn()
        cur = conn.cursor()

        # ---------------- 阶段 1：短事务——认领 + 预留额度 ----------------
        cur.execute("BEGIN IMMEDIATE")
        try:
            # 1) 跨 Worker 幂等去重：同一 Idempotency-Key 直接复用已存结果
            if idempotency_key is not None:
                row = cur.execute(
                    "SELECT status_code, body FROM idempotency WHERE key=?",
                    (idempotency_key,),
                ).fetchone()
                if row is not None:
                    conn.commit()
                    return row["status_code"], json.loads(row["body"])

            asale_row = cur.execute(
                "SELECT * FROM after_sales WHERE id=?", (after_sale_id,)
            ).fetchone()
            if asale_row is None:
                conn.rollback()
                return 404, {"detail": "after-sale not found"}

            asale = _row_to_after_sale(asale_row)

            # 2) 资源级幂等：已退款的售后重放，返回既有结果且不二次累加
            if asale.status == AfterSaleStatus.REFUNDED:
                conn.commit()
                return 200, asale.model_dump(mode="json")

            now = _now_iso()
            # 3) 认领：把 APPROVED/REFUND_FAILED 原子翻成 REFUNDING，保证同一售后
            #    只有 1 个工作者会去驱动（慢）的第三方渠道调用。
            rv = cur.execute(
                "UPDATE after_sales SET status='REFUNDING', "
                "reviewed_at=COALESCE(reviewed_at, ?) "
                "WHERE id=? AND status IN ('APPROVED', 'REFUND_FAILED')",
                (now, after_sale_id),
            )
            if rv.rowcount == 0:
                # 认领失败：读回当前状态判断原因
                conn.rollback()
                cur_status = cur.execute(
                    "SELECT * FROM after_sales WHERE id=?", (after_sale_id,)
                ).fetchone()
                if cur_status is None:
                    return 404, {"detail": "after-sale not found"}
                status = AfterSaleStatus(cur_status["status"])
                if status == AfterSaleStatus.REFUNDING:
                    # 其它工作者正在处理 -> 轮询其最终落库结果
                    return self._await_settlement(cur, after_sale_id)
                if status == AfterSaleStatus.REFUNDED:
                    return 200, _row_to_after_sale(cur_status).model_dump(mode="json")
                # PENDING / REJECTED 等不可退款状态
                return 409, {
                    "detail": f"cannot refund after-sale in status {status.value}"
                }

            # 4) 读取订单并校验金额（认领成功后，使用最新订单状态）
            orow = cur.execute(
                "SELECT id, amount, refunded_amount, status FROM orders WHERE id=?",
                (asale.order_id,),
            ).fetchone()
            if orow is None:
                conn.rollback()
                return 404, {"detail": "order not found"}

            # 规则：仅「已支付(PAID)」订单可退款。未支付(CREATED)或已全额退款闭单
            # (REFUNDED) 的订单不允许再发起退款——这把「unpaid order 不能退款」与
            # 「累计不超过 paid_amount」在存储层直接卡住，而非仅靠上游链路间接保证。
            if orow["status"] != OrderStatus.PAID.value:
                conn.rollback()
                return 409, {
                    "detail": f"cannot refund order in status {orow['status']}"
                }

            # 全部金额以「分」为整数运算，避免浮点累加误差（典型如 3 × 100/3 ≠ 100）。
            amount_c = int(round(orow["amount"] * 100))
            refunded_c = int(round(orow["refunded_amount"] * 100))
            remaining_c = amount_c - refunded_c

            # 订单累计已等于实付：无可退金额
            if remaining_c <= 0:
                conn.rollback()
                return 409, {
                    "detail": "order already fully refunded (no remaining payable)"
                }

            if requested is None:
                refund_c = remaining_c
            else:
                req_c = int(round(requested * 100))
                # 上限保护：单次退款不超过「剩余可退金额」。超过部分按剩余金额退款
                # （clamp 而非拒绝），保证「累计成功退款不超过 paid_amount」这一核心不变量，
                # 同时满足「申请超额时退剩余」的友好语义。
                refund_c = min(req_c, remaining_c)

            # 规则：退款金额必须 > 0
            if refund_c <= 0:
                conn.rollback()
                return 400, {"detail": "refund_amount must be greater than 0"}
            refund_amount = refund_c / 100.0

            # 5) 预留额度：条件 UPDATE 在调用渠道「之前」完成，仅成功预留者才去扣款，
            #    杜绝「渠道已扣款但本地额度校验失败而回滚」的重复扣款。
            #    注意：此处只累加 refunded_amount，暂不写订单状态/refunded_at；
            #    订单状态与 refunded_at 在阶段 3（渠道结果已知）才最终落定，
            #    这样渠道失败时可直接释放额度并把订单状态回退为 PAID，避免「假 REFUNDED」。
            #    WHERE 子句以「分」为单位做精确条件判定（CAST(...*100 AS INTEGER)），
            #    保证并发下累计退款金额永不突破订单实付金额（无浮点越界）。
            rv2 = cur.execute(
                "UPDATE orders SET refunded_amount = refunded_amount + ? "
                "WHERE id=? AND CAST((refunded_amount + ?) * 100 AS INTEGER) "
                "<= CAST(amount * 100 AS INTEGER)",
                (refund_amount, asale.order_id, refund_amount),
            )
            if rv2.rowcount == 0:
                # 额度已被并发的其它退款消耗：释放认领（ROLLBACK 一并撤销 REFUNDING），
                # 不调用渠道、不产生扣款。
                conn.rollback()
                return 409, {
                    "detail": (
                        f"refund amount {refund_amount} exceeds remaining "
                        f"payable {remaining_c / 100.0}"
                    )
                }

            # 记录本次尝试金额，并尽快提交以释放写锁
            cur.execute(
                "UPDATE after_sales SET refund_amount=? WHERE id=?",
                (round(refund_amount, 2), after_sale_id),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        # ---------------- 阶段 2：无锁——调用（慢）第三方渠道 ----------------
        result: RefundResult = self.gateway.refund(
            payment_ref=asale.order_id,
            after_sale_id=asale.id,
            amount=round(refund_amount, 2),
        )

        # ---------------- 阶段 3：短事务——写回渠道结果 ----------------
        cur.execute("BEGIN IMMEDIATE")
        try:
            if not result.success:
                # 释放阶段 1 预留的额度，并回退订单状态（绝不污染累计金额以外的状态），
                # 标记为可重试的 REFUND_FAILED；不缓存幂等键。
                cur.execute(
                    "UPDATE orders SET refunded_amount = refunded_amount - ? "
                    "WHERE id=? AND refunded_amount >= ?",
                    (refund_amount, asale.order_id, refund_amount),
                )
                # 依据剩余累计金额回退订单状态（全额才 REFUNDED，否则 PAID）
                cur.execute(
                    "UPDATE orders SET status = CASE "
                    "WHEN refunded_amount >= ? - 1e-9 THEN 'REFUNDED' ELSE 'PAID' END "
                    "WHERE id=?",
                    (orow["amount"], asale.order_id),
                )
                cur.execute(
                    "UPDATE after_sales SET status='REFUND_FAILED', refund_amount=? "
                    "WHERE id=? AND status='REFUNDING'",
                    (refund_amount, after_sale_id),
                )
                conn.commit()
                failed_body = AfterSale(
                    id=asale.id,
                    order_id=asale.order_id,
                    reason=asale.reason,
                    status=AfterSaleStatus.REFUND_FAILED,
                    created_at=asale.created_at,
                    reviewed_at=asale.reviewed_at,
                    refund_amount=refund_amount,
                    reviewer_note=asale.reviewer_note,
                ).model_dump(mode="json")
                return 502, {
                    "detail": f"third-party refund failed: {result.error}",
                    **failed_body,
                }

            # 渠道成功 -> 把认领状态落实为 REFUNDED（额度已在阶段 1 预留好）
            cur.execute(
                "UPDATE after_sales SET status='REFUNDED', refund_amount=?, "
                "reviewed_at=COALESCE(reviewed_at, ?) "
                "WHERE id=? AND status='REFUNDING'",
                (refund_amount, now, after_sale_id),
            )
            # 订单状态与 refunded_at 在渠道确认真实成功后落定
            cur.execute(
                "UPDATE orders SET status = CASE "
                "WHEN refunded_amount >= ? - 1e-9 THEN 'REFUNDED' ELSE 'PAID' END, "
                "refunded_at = ? WHERE id=?",
                (orow["amount"], now, asale.order_id),
            )
            body = AfterSale(
                id=asale.id,
                order_id=asale.order_id,
                reason=asale.reason,
                status=AfterSaleStatus.REFUNDED,
                created_at=asale.created_at,
                reviewed_at=asale.reviewed_at or _parse_dt(now),
                refund_amount=refund_amount,
                reviewer_note=asale.reviewer_note,
            ).model_dump(mode="json")

            # 仅缓存成功结果（失败不缓存，允许同键修正后重试）
            if idempotency_key is not None:
                cur.execute(
                    "INSERT OR IGNORE INTO idempotency(key, status_code, body) "
                    "VALUES(?, ?, ?)",
                    (idempotency_key, 200, json.dumps(body)),
                )
            conn.commit()
            return 200, body
        except Exception:
            conn.rollback()
            raise


# 全局单例：app 与测试（同进程内）共享同一数据库文件。
store = Store()
