# -*- coding: utf-8 -*-
"""食物库存（Pantry）测试"""
import os
import sys
import unittest

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "src")))

from pantry import Pantry  # noqa: E402


class TestPantry(unittest.TestCase):
    def test_import_and_dedup(self):
        p = Pantry()
        orders = [
            {"orderId": "A", "items": [{"name": "巨无霸", "quantity": 1, "parts": []}]},
            {"orderId": "B", "items": [{"name": "薯条", "quantity": 2, "parts": []}]},
        ]
        r = p.import_orders(orders)
        self.assertEqual(r["new_orders"], 2)
        self.assertEqual(p.count("巨无霸"), 1)
        self.assertEqual(p.count("薯条"), 2)

        r2 = p.import_orders(orders)                  # 重复同步
        self.assertEqual(r2["new_orders"], 0)
        self.assertEqual(r2["skipped"], 2)
        self.assertEqual(p.count("薯条"), 2)          # 没变

    def test_combo_decompose_on_import(self):
        p = Pantry()
        p.import_orders([{"orderId": "C", "items": [
            {"name": "随心配1+1套餐", "quantity": 1,
             "parts": [{"name": "高达吉士双牛堡", "quantity": 1},
                       {"name": "中杯怡泉+C", "quantity": 1}]}]}])
        self.assertEqual(p.count("高达吉士双牛堡"), 1)
        self.assertEqual(p.count("中杯怡泉+C"), 1)
        self.assertNotIn("随心配1+1套餐", p.items)     # 套餐本身不入库

    def test_take(self):
        p = Pantry(items={"薯条": 2})
        self.assertEqual(p.take("薯条"), "薯条")
        self.assertEqual(p.count("薯条"), 1)
        self.assertEqual(p.take("薯条"), "薯条")
        self.assertIsNone(p.take("薯条"))               # 取完了
        self.assertEqual(p.total, 0)
        self.assertIsNone(p.take("不存在"))              # 不存在的取不到

    def test_fuzzy_take(self):
        """模糊匹配：输入"薯条"能取到库存里的"中薯条" """
        p = Pantry(items={"中薯条": 1, "巨无霸": 1})
        self.assertEqual(p.take("薯条"), "中薯条")
        self.assertEqual(p.take("霸"), "巨无霸")          # 包含匹配
        self.assertIsNone(p.take("薯条"))                 # 已取完
        # 精确优先：两种薯条同时存在时，精确名优先
        p2 = Pantry(items={"薯条": 1, "中薯条": 1})
        self.assertEqual(p2.take("薯条"), "薯条")

    def test_serialization(self):
        p = Pantry(items={"薯条": 2}, imported=["A", "B"])
        p2 = Pantry.from_dict(p.to_dict())
        self.assertEqual(p2.items, p.items)
        self.assertEqual(p2.imported, {"A", "B"})

    def test_no_order_id(self):
        """无 orderId 的订单也能入库（不去重）"""
        p = Pantry()
        p.import_orders([{"orderId": "", "items": [
            {"name": "麦乐鸡", "quantity": 1, "parts": []}]}])
        self.assertEqual(p.count("麦乐鸡"), 1)

    def test_sorted_items(self):
        p = Pantry(items={"薯条": 1, "巨无霸": 3, "麦乐鸡": 2})
        names = [k for k, _ in p.sorted_items()]
        self.assertEqual(names, ["巨无霸", "麦乐鸡", "薯条"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
