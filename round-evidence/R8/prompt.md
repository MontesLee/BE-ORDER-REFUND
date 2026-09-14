# R8 — 测试要求：补齐并稳定自动化测试

> 本文件是被测模型在该轮收到的 **Prompt 原文**。评测时逐轮原文发送，
> 不补充解读、不预告后续轮次。

```text
请为当前系统补齐完整自动化测试，并确保测试可以稳定、重复运行。

至少覆盖：

Business：

* normal refund；
* unpaid refund；
* invalid amount；
* multiple partial refunds；
* over-refund。

State：

* not approved cannot refund；
* REFUND_FAILED can retry；
* REFUNDED cannot retry；
* illegal transition。

Idempotency：

* duplicate submit；
* duplicate execute。

Concurrency：

* same AfterSale concurrent；
* multiple AfterSale concurrent over-refund。

Third-party：

* failure；
* retry；
* execute after success。

Security：

* unauthorized order；
* unauthorized AfterSale；
* normal user protected execution。

不要使用随机 sleep 作为核心正确性证明。

最后运行完整测试集并修复失败。
```
