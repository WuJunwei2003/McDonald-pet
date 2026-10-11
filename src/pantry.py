# -*- coding: utf-8 -*-
"""食物库存（Pantry）—— 同步订单获得食物，喂养时消耗

设计：
- 同步订单 → 把订单里的品项（套餐拆成子项）存入库存
- 已入库的订单按 orderId 去重，重复同步不会重复获得食物
- 喂养时从库存取一份（take），取完了就"没得吃"，需要再去吃麦当劳
"""
from __future__ import annotations


class Pantry:
    """食物库存 + 订单入库去重"""

    def __init__(self, items: dict | None = None, imported: list | None = None):
        self.items: dict[str, int] = dict(items or {})     # {食物名: 份数}
        self.imported: set[str] = set(imported or [])     # 已入库 orderId

    # ---------------------------------------------------------- 入库

    def import_orders(self, orders: list[dict]) -> dict:
        """把订单入库（自动拆解套餐、按 orderId 去重）。

        返回::

            {"new_orders": 2,
             "added": {"薯条": 2, "巨无霸": 1},   # 本次新增（份数）
             "skipped": 8}                        # 已入过库的订单数
        """
        added: dict[str, int] = {}
        new_orders = 0
        skipped = 0
        for o in orders:
            oid = o.get("orderId", "")
            if oid and oid in self.imported:
                skipped += 1
                continue
            new_orders += 1
            if oid:
                self.imported.add(oid)
            for it in o.get("items", []):
                parts = it.get("parts") or [it]
                for p in parts:
                    name = (p.get("name") or "").strip()
                    if not name:
                        continue
                    qty = max(1, int(p.get("quantity") or 1))
                    self.items[name] = self.items.get(name, 0) + qty
                    added[name] = added.get(name, 0) + qty
        return {"new_orders": new_orders, "added": added, "skipped": skipped}

    def add(self, name: str, quantity: int = 1) -> None:
        """直接添加食物（模拟订单 / 活动投喂用）"""
        name = (name or "").strip()
        if name and quantity > 0:
            self.items[name] = self.items.get(name, 0) + quantity

    # ---------------------------------------------------------- 取出

    def find(self, keyword: str) -> str | None:
        """模糊查找库存中的食物名（精确优先 → 包含匹配）。

        例：找 "薯条" 可以匹配到库存里的 "中薯条"。
        """
        keyword = (keyword or "").strip()
        if not keyword:
            return None
        if self.items.get(keyword, 0) > 0:
            return keyword
        for name in self.items:
            if keyword in name:
                return name
        return None

    def take(self, keyword: str) -> str | None:
        """取一份食物用于喂养（支持模糊名）。

        返回：实际取到的食物名（如输入"薯条"取到"中薯条"）；库存没有则 None。
        """
        name = self.find(keyword)
        if not name:
            return None
        self.items[name] -= 1
        if self.items[name] <= 0:
            del self.items[name]
        return name

    def count(self, name: str) -> int:
        return self.items.get(name, 0)

    @property
    def total(self) -> int:
        return sum(self.items.values())

    def sorted_items(self) -> list[tuple[str, int]]:
        """按份数降序（供 UI 展示）"""
        return sorted(self.items.items(), key=lambda kv: (-kv[1], kv[0]))

    # ---------------------------------------------------------- 序列化

    def to_dict(self) -> dict:
        return {"items": self.items, "imported": sorted(self.imported)}

    @classmethod
    def from_dict(cls, d: dict | None) -> "Pantry":
        d = d or {}
        return cls(items=d.get("items"), imported=d.get("imported"))
