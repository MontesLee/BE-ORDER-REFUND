"""第三方支付渠道退款网关抽象（可替换）。

根因：原 `store.refund_transaction` 在校验完金额/额度后，直接把本地 AfterSale/Order
置为 REFUNDED，从未真正调用第三方支付渠道。因此一旦真实渠道因网络/服务问题失败，
本地却显示「退款成功」——这正是本轮要修复的线上问题。

本模块把「调用第三方渠道」抽成可替换的 `RefundGateway`：

  * RefundResult        —— 渠道退款结果（成功/失败 + 渠道流水号 + 错误信息）；
  * RefundGateway       —— 网关协议（结构化类型，便于依赖注入与测试替身）；
  * RealRefundGateway   —— 生产用，基于 httpx 调用真实渠道（由 REFUND_CHANNEL_URL 启用）；
  * FakeRefundGateway   —— 测试用，确定性模拟「成功/失败」，使失败场景可稳定复现；
  * SuccessRefundGateway—— 未接入真实渠道时的「成功」占位，保持既有 happy-path 行为，
                            并作为默认网关，使已有一致性测试在无渠道环境下依旧通过；
  * build_refund_gateway() —— 根据环境变量选择默认网关的工厂。

设计要点：
  * 网关方法签名 `refund(*, payment_ref, after_sale_id, amount) -> RefundResult`；
    其中 payment_ref 取订单 id（代表原始支付单据），便于渠道侧按单据退款并对账。
  * 网关自身捕获网络/协议异常并转成 `RefundResult(success=False)`，不让异常穿透到
    退款事务之外（失败时由 store 记入 REFUND_FAILED，保证事务可正常提交）。
"""
from dataclasses import dataclass
from typing import Callable, Optional, Protocol


@dataclass
class RefundResult:
    """第三方渠道退款结果。"""

    success: bool
    channel_refund_id: Optional[str] = None
    error: Optional[str] = None


class RefundGateway(Protocol):
    """第三方退款渠道协议（可替换抽象）。"""

    def refund(
        self, *, payment_ref: str, after_sale_id: str, amount: float
    ) -> RefundResult:
        """对 payment_ref 对应的原始支付发起 amount 金额的退款。

        返回 RefundResult：success=True 表示渠道已确认退款成功；
        success=False 表示渠道失败（网络/服务/拒绝），error 记录原因。
        """
        ...


class SuccessRefundGateway:
    """本地/未接入真实渠道时的占位实现：模拟渠道成功。

    用于默认网关（REFUND_CHANNEL_URL 未配置），保证既有 happy-path 行为不退化，
    也使已有一致性测试无需改造即可通过。
    """

    def refund(
        self, *, payment_ref: str, after_sale_id: str, amount: float
    ) -> RefundResult:
        return RefundResult(
            success=True, channel_refund_id=f"stub-{after_sale_id}-{amount}"
        )


class FakeRefundGateway:
    """测试用确定性网关。

    可在构造时指定：
      * fail=True            —— 所有退款一律失败（稳定复现第三方失败）；
      * fail_predicate       —— 按 (after_sale_id, amount) 规则决定失败，用于模拟
                                间歇性/选择性失败；
      * error                —— 失败原因文案。
    并暴露 `calls` 列表，便于测试断言「渠道确实被（且仅被）调用了一次」。
    """

    def __init__(
        self,
        fail: bool = False,
        fail_predicate: Optional[Callable[[str, float], bool]] = None,
        error: str = "channel declined",
    ) -> None:
        self.fail = fail
        self.fail_predicate = fail_predicate
        self.error = error
        self.calls: list[tuple[str, str, float]] = []

    def refund(
        self, *, payment_ref: str, after_sale_id: str, amount: float
    ) -> RefundResult:
        self.calls.append((payment_ref, after_sale_id, amount))
        if self.fail or (
            self.fail_predicate is not None
            and self.fail_predicate(after_sale_id, amount)
        ):
            return RefundResult(success=False, error=self.error)
        return RefundResult(
            success=True, channel_refund_id=f"fake-{after_sale_id}-{amount}"
        )


class RealRefundGateway:
    """真实渠道网关（基于 httpx 的占位实现，演示如何接入生产渠道）。

    由环境变量 REFUND_CHANNEL_URL 启用；未配置时返回失败（而非静默成功），
    迫使生产环境显式接入，避免「假成功」。
    """

    def __init__(
        self, channel_url: Optional[str] = None, timeout: float = 5.0
    ) -> None:
        import os

        self.channel_url = channel_url or os.environ.get("REFUND_CHANNEL_URL")
        self.timeout = timeout

    def refund(
        self, *, payment_ref: str, after_sale_id: str, amount: float
    ) -> RefundResult:
        if not self.channel_url:
            return RefundResult(
                success=False, error="REFUND_CHANNEL_URL not configured"
            )
        import httpx

        try:
            resp = httpx.post(
                self.channel_url,
                json={
                    "payment_ref": payment_ref,
                    "after_sale_id": after_sale_id,
                    "amount": amount,
                },
                timeout=self.timeout,
            )
            if 200 <= resp.status_code < 300:
                cid = None
                try:
                    cid = resp.json().get("refund_id")
                except Exception:
                    cid = None
                return RefundResult(success=True, channel_refund_id=cid)
            return RefundResult(
                success=False, error=f"channel returned HTTP {resp.status_code}"
            )
        except Exception as exc:  # 网络/超时/协议异常均视为失败
            return RefundResult(success=False, error=f"channel error: {exc}")


def build_refund_gateway() -> RefundGateway:
    """默认网关工厂：配置了真实渠道则使用 RealRefundGateway，否则使用占位成功网关。"""
    import os

    if os.environ.get("REFUND_CHANNEL_URL"):
        return RealRefundGateway()
    return SuccessRefundGateway()
