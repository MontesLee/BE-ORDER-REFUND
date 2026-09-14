"""内存存储层。

为保持最小可运行，订单与售后数据存放在进程内存的字典中，
重启服务后数据丢失。使用线程锁保证基本的并发安全。
测试可通过 Store.reset() 清空数据。
"""
import threading
from typing import Dict, Optional

from models import Order, AfterSale


class Store:
    def __init__(self) -> None:
        self.orders: Dict[str, Order] = {}
        self.after_sales: Dict[str, AfterSale] = {}
        self.lock = threading.Lock()

    def reset(self) -> None:
        with self.lock:
            self.orders.clear()
            self.after_sales.clear()


# 全局单例，app 与测试共享同一实例。
store = Store()
