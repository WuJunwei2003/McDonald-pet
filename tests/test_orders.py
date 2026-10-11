# -*- coding: utf-8 -*-
"""订单解析与套餐拆解测试"""
import os
import sys
import unittest

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "src")))

from feeding import Spirit  # noqa: E402
from order_parser import parse_order_list, extract_json  # noqa: E402

RAW = {
    "success": True,
    "data": {
        "list": [
            {
                "orderId": "T1", "createTime": "2026-10-07 13:52:16",
                "storeName": "测试店", "orderStatus": "订单已完成",
                "orderProductList": [
                    {"productName": "随心配1+1套餐", "quantity": 1, "comboItemList": [
                        {"name": "高达吉士双牛堡", "quantity": 1},
                        {"name": "中杯怡泉+C", "quantity": 1},
                    ]},
                ],
            },
            {
                "orderId": "T2", "createTime": "2026-10-06 12:00:00",
                "storeName": "测试店", "orderStatus": "订单已取消",
                "orderProductList": [{"productName": "巨无霸", "quantity": 1,
                                      "comboItemList": []}],
            },
            {
                "orderId": "T3", "createTime": "2026-10-05 12:00:00",
                "storeName": "测试店", "orderStatus": "订单已完成",
                "orderProductList": [
                    {"productName": "2份风味派", "quantity": 1, "comboItemList": [
                        {"name": "姜汁撞奶风味派", "quantity": 2}]},
                    {"productName": "麦乐鸡", "quantity": 1, "comboItemList": []},
                ],
            },
        ]
    },
}


class TestParser(unittest.TestCase):
    def test_filters_unfinished(self):
        orders = parse_order_list(RAW)
        self.assertEqual(len(orders), 2)                     # 取消的单被过滤
        self.assertEqual(orders[0]["orderId"], "T1")

    def test_combo_parts_parsed(self):
        orders = parse_order_list(RAW)
        parts = orders[0]["items"][0]["parts"]
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0]["name"], "高达吉士双牛堡")

    def test_extract_json_from_text(self):
        text = 'Response info...\n{"success":true,"data":{"list":[]}}\ntail'
        d = extract_json(text)
        self.assertTrue(d["success"])
        self.assertEqual(d["data"]["list"], [])

    def test_extract_json_none_on_bad_text(self):
        self.assertIsNone(extract_json("no json here"))
        self.assertIsNone(extract_json(""))


class TestComboFeeding(unittest.TestCase):
    def test_combo_decomposed_to_parts(self):
        sp = Spirit()
        orders = parse_order_list(RAW)
        r = sp.feed_order(orders[0])                          # 随心配：牛堡 + 汽水
        self.assertEqual(r["feed_count"], 2)
        self.assertEqual(r["lineages_fed"].get("牛"), 1)
        self.assertEqual(r["lineages_fed"].get("无"), 1)      # 汽水=中性
        self.assertEqual(sp.lineage_exp.get("牛"), 10.0)

    def test_quantity_makes_multiple_feeds(self):
        sp = Spirit()
        r = sp.feed_order({"items": [
            {"name": "2份风味派", "quantity": 1,
             "parts": [{"name": "姜汁撞奶风味派", "quantity": 2}]}]})
        self.assertEqual(r["feed_count"], 2)                  # 2 份派喂 2 次
        self.assertEqual(sp.lineage_exp.get("甜"), 20.0)

    def test_mixed_order_distribution(self):
        sp = Spirit()
        orders = parse_order_list(RAW)
        r = sp.feed_order(orders[1])                          # 派×2 + 麦乐鸡
        self.assertEqual(r["feed_count"], 3)
        self.assertEqual(r["lineages_fed"], {"甜": 2, "鸡": 1})

    def test_quantity_cap(self):
        sp = Spirit()
        r = sp.feed_item("薯条", quantity=99)
        self.assertEqual(len(r), Spirit.MAX_QTY_PER_ITEM)     # 单次封顶 5 份

    def test_full_order_lineage_result(self):
        """两个订单喂完 -> 成形为甜系（2份派共 20 exp，多于双牛堡的 10 exp）"""
        sp = Spirit()
        orders = parse_order_list(RAW)
        for o in orders:
            sp.feed_order(o)
        self.assertEqual(sp.lineage, "甜")
        self.assertGreaterEqual(sp.total_exp, 30)


if __name__ == "__main__":
    unittest.main(verbosity=2)
