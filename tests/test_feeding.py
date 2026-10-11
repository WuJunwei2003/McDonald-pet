# -*- coding: utf-8 -*-
"""喂养引擎单元测试（stdlib unittest）"""
import os
import sys
import unittest

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "src")))

from feeding import Spirit, classify_meal, HETERO_LIMIT, THRESHOLDS  # noqa: E402


class TestClassify(unittest.TestCase):
    def test_six_lineages(self):
        cases = {
            "中薯条": "薯", "薯饼": "薯",
            "巨无霸": "牛", "双层吉士汉堡": "牛", "芝士安格斯厚牛堡": "牛",
            "麦辣鸡腿堡": "鸡", "麦乐鸡": "鸡", "那么大鸡排（椒盐风味）": "鸡",
            "麦香鱼": "鱼", "双层深海鳕鱼堡": "鱼",
            "麦咖啡™拿铁": "咖", "鲜萃咖啡": "咖",
            "蓝莓爆爆珠麦旋风": "甜", "圆筒冰淇淋": "甜", "香芋派": "甜",
        }
        for meal, expect in cases.items():
            self.assertEqual(classify_meal(meal), expect, f"{meal} 应归 {expect}")

    def test_unmatched(self):
        self.assertIsNone(classify_meal("可乐"))
        self.assertIsNone(classify_meal("雪碧"))
        self.assertIsNone(classify_meal(""))
        self.assertIsNone(classify_meal("纯牛奶(盒装)"))


class TestGrowth(unittest.TestCase):
    def test_undifferentiated_accumulates(self):
        sp = Spirit()
        e = sp.feed("薯条")
        self.assertEqual(e["exp_gained"], 10.0)
        self.assertEqual(sp.lineage_exp.get("薯"), 10.0)
        self.assertIsNone(sp.lineage)

    def test_stage2_lineage_is_top_fed(self):
        sp = Spirit()
        sp.feed("薯条")
        sp.feed("薯条")
        e = sp.feed("巨无霸")          # 总经验 30 -> 成形
        self.assertTrue(e["evolved"])
        self.assertEqual(e["lineage_assigned"], "薯")   # 薯 20 > 牛 10
        self.assertEqual(sp.stage, 2)

    def test_same_and_cross_affinity(self):
        sp = Spirit()
        sp.feed("薯条")
        sp.feed("薯条")
        sp.feed("薯条")                # 30 -> 成形为薯系
        self.assertEqual(sp.lineage, "薯")
        e1 = sp.feed("大薯条")          # 本命 x1.5
        self.assertEqual(e1["exp_gained"], 15.0)
        e2 = sp.feed("巨无霸")          # 异系 x0.5
        self.assertEqual(e2["exp_gained"], 5.0)
        self.assertEqual(sp.hetero.get("牛"), 5.0)

    def test_daily_source_multiplier(self):
        sp = Spirit()
        e = sp.feed("薯条", source="daily")
        self.assertEqual(e["exp_gained"], 3.0)

    def test_event_source_multiplier(self):
        sp = Spirit()
        e = sp.feed("薯条", source="event")
        self.assertEqual(e["exp_gained"], 12.0)

    def test_variant_on_hetero_limit(self):
        sp = Spirit()
        sp.feed("薯条"); sp.feed("薯条"); sp.feed("薯条")   # 成形为薯
        self.assertEqual(sp.lineage, "薯")
        triggered = False
        for _ in range(4):                                  # 4 x 5 = 20 异系值
            e = sp.feed("巨无霸")
            triggered = triggered or e["variant_triggered"]
        self.assertTrue(triggered)
        self.assertTrue(sp.variant)
        self.assertEqual(sp.stage, 4)
        self.assertGreaterEqual(sp.hetero["牛"], HETERO_LIMIT)

    def test_stage3_at_threshold(self):
        sp = Spirit()
        sp.feed("薯条"); sp.feed("薯条"); sp.feed("薯条")    # 30
        for _ in range(4):                                   # +15*4 = 90
            sp.feed("薯条")
        self.assertEqual(sp.stage, 3)

    def test_feed_log_and_count(self):
        sp = Spirit()
        sp.feed("薯条"); sp.feed("巨无霸")
        self.assertEqual(sp.feed_count, 2)
        self.assertEqual(sp.fed_meals[0], "巨无霸")          # 最近在前
        self.assertIn("薯条", sp.fed_meals)

    def test_message_non_empty(self):
        sp = Spirit()
        e = sp.feed("薯条")
        self.assertTrue(e["message"])


class TestSerialization(unittest.TestCase):
    def test_roundtrip(self):
        sp = Spirit(name="测试精灵")
        sp.feed("薯条"); sp.feed("薯条"); sp.feed("巨无霸"); sp.feed("麦旋风")
        d = sp.to_dict()
        sp2 = Spirit.from_dict(d)
        self.assertEqual(sp2.name, "测试精灵")
        self.assertEqual(sp2.lineage, sp.lineage)
        self.assertAlmostEqual(sp2.total_exp, sp.total_exp)
        self.assertEqual(sp2.hetero, sp.hetero)
        self.assertEqual(sp2.fed_meals, sp.fed_meals)

    def test_progress(self):
        sp = Spirit()
        sp.feed("薯条")
        p = sp.progress()
        self.assertEqual(p["stage"], 1)
        self.assertEqual(p["next"], THRESHOLDS["stage2"])
        self.assertGreater(p["pct"], 0)


class TestSpiritGen(unittest.TestCase):
    def test_svg_wellformed(self):
        sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "src")))
        from spirit_gen import render_spirit
        for lin in ("薯", "牛", "鸡", "鱼", "咖", "甜", None):
            for stage in (1, 2, 3, 4):
                svg = render_spirit(lin, stage)
                self.assertTrue(svg.startswith("<svg"))
                self.assertTrue(svg.endswith("</svg>"))
                self.assertIn("<title>", svg)
        egg = render_spirit(None, 0)
        self.assertIn("蛋", egg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
