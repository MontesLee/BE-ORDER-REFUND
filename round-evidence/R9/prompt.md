# R9 — 最终收敛：全量历史回归

> 本文件是被测模型在该轮收到的 **Prompt 原文**。评测时逐轮原文发送，
> 不补充解读、不预告后续轮次。

```text
请完成最终交付。

最终系统必须满足：

1. paid order 可以退款；
2. unpaid order 不能退款；
3. 一个订单支持多个 AfterSale；
4. 累计成功退款不超过 paid_amount；
5. 一个 AfterSale 最多一个成功退款；
6. duplicate request 不产生重复有效退款；
7. 非法状态转换被拒绝；
8. REFUND_FAILED 可以 retry；
9. REFUNDED 不能 retry；
10. 第三方失败不能导致本地退款成功；
11. multi-worker 场景保持核心 invariant；
12. 用户不能访问其他用户订单；
13. 用户不能访问其他用户 AfterSale；
14. 普通用户不能绕过审核执行退款。

请：

* 完成代码；
* 完善测试；
* 梳理并完善 README；
* 运行完整测试；
* 修复所有失败；
* 确保 clean environment 可以运行；
* 简要说明最终架构和核心保证。
```
