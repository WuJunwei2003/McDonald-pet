# -*- coding: utf-8 -*-
"""形态表一致性测试：forms.json ↔ 素材文件 ↔ 系别配置 三方对齐

防护目标：改了素材/映射后不会出现"界面上引用不存在的图"或"某系缺形态"。
"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from feeding import LINEAGES          # noqa: E402  六系配置（单一事实来源）

with open(os.path.join(ROOT, "data", "forms.json"), encoding="utf-8") as _f:
    FORMS = json.load(_f)

SPIRITS_DIR = os.path.join(ROOT, "assets", "spirits")


def _all_form_slugs() -> set:
    out = set()
    for tiers in FORMS["lineages"].values():
        for e in tiers.values():
            out.add(e["slug"])
    return out


class TestForms(unittest.TestCase):

    def test_every_lineage_has_all_tiers(self):
        """六系（与 lineage.json 对齐）都要有 T2/T3/T4 形态"""
        for lin in LINEAGES:
            tiers = FORMS["lineages"].get(lin, {})
            for t in ("2", "3", "4"):
                self.assertIn(t, tiers, f"{lin}系缺 tier {t}")
                self.assertTrue(tiers[t].get("slug"), f"{lin}系 T{t} 缺 slug")
                self.assertTrue(tiers[t].get("name"), f"{lin}系 T{t} 缺 name")

    def test_all_form_slugs_have_image(self):
        """形态引用的每个 slug 都有对应素材文件"""
        for slug in sorted(_all_form_slugs()):
            self.assertTrue(os.path.exists(os.path.join(SPIRITS_DIR, slug + ".png")),
                            f"缺素材文件：{slug}.png")

    def test_food_icons_slugs_known(self):
        """食物图标映射使用的 slug 必须全部在素材清单里"""
        known = set(_all_form_slugs())
        mpath = os.path.join(SPIRITS_DIR, "manifest.json")
        with open(mpath, encoding="utf-8") as f:
            known |= {it["slug"] for it in json.load(f)["items"]}
        for kw, slug in FORMS.get("food_icons", []):
            self.assertIn(slug, known, f"food_icons「{kw}」指向未收录素材 {slug}")

    def test_fish_is_unique_form(self):
        """鱼系三个 tier 同图（'菜单里鱼类最少'的稀有唯一形态设计）"""
        fish = FORMS["lineages"]["鱼"]
        self.assertEqual(fish["2"]["slug"], fish["3"]["slug"])
        self.assertEqual(fish["3"]["slug"], fish["4"]["slug"])

    def test_tier_slugs_unique_except_fish(self):
        """除鱼系外，同系内形态不应重复（进化要有区别）"""
        for lin, tiers in FORMS["lineages"].items():
            if lin == "鱼":
                continue
            slugs = [tiers[t]["slug"] for t in ("2", "3", "4")]
            self.assertEqual(len(set(slugs)), 3, f"{lin}系形态有重复：{slugs}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
