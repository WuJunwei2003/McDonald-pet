# -*- coding: utf-8 -*-
"""麦麦精灵 · 喂养引擎（纯逻辑，零依赖，可单元测试）

规则摘要：
- 未分化期（幼体）：所有喂养按基础经验积累到各系，喂得最多的系别决定成形方向
- 成形后：喂本命系 x1.5；喂异系 x0.5 且累积「异系值」，异系值满触发变异体
- 三种喂养来源：真食（真实订单）x1.0 / 每日投喂 x0.3 / 活动 x1.2
"""
from __future__ import annotations

import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA = os.path.normpath(os.path.join(_HERE, "..", "data", "lineage.json"))

with open(_DATA, encoding="utf-8") as _f:
    CFG = json.load(_f)

KEYWORDS: dict = CFG["keywords"]
RULES: dict = CFG["rules"]
LINEAGES: dict = CFG["lineages"]

BASE_EXP = 10.0

SOURCE_MULT = RULES["feed_multiplier"]          # real / daily / event
AFFINITY = RULES["affinity"]                    # same / cross / neutral
THRESHOLDS = RULES["stage_thresholds"]          # hatch / stage2 / stage3 / variant_extra
HETERO_LIMIT = RULES["hetero_variant_threshold"]


def classify_meal(meal_name: str) -> str | None:
    """餐品名 -> 系别（薯/牛/鸡/鱼/咖/甜）或 None（不属于任何系）"""
    if not meal_name:
        return None
    for lineage, kws in KEYWORDS.items():
        for kw in kws:
            if kw in meal_name:
                return lineage
    return None


class Spirit:
    """一只麦麦精灵的全部状态与成长逻辑。"""

    def __init__(self, name: str = "麦麦", lineage: str | None = None,
                 total_exp: float = 0.0, lineage_exp: dict | None = None,
                 hetero: dict | None = None, variant: bool = False,
                 feed_count: int = 0, fed_meals: list | None = None):
        self.name = name
        self.lineage = lineage                      # 成形后的系别
        self.total_exp = total_exp
        self.lineage_exp = lineage_exp or {}        # {系别: 累积经验}
        self.hetero = hetero or {}                  # {系别: 异系值}
        self.variant = variant                      # 是否已变异
        self.feed_count = feed_count                # 被喂食次数
        self.fed_meals = fed_meals or []            # 喂过的餐品名（最近的在前）

    # ------------------------------------------------------------ 状态

    @property
    def stage(self) -> int:
        """0=蛋（不会出现，蛋在孵化前）1=幼体 2=成形 3=完全体 4=变异"""
        if self.variant:
            return 4
        if self.total_exp >= THRESHOLDS["stage3"]:
            return 3
        if self.total_exp >= THRESHOLDS["stage2"]:
            return 2
        return 1

    @property
    def mood(self) -> str:
        """由最近喂养状态推断表情"""
        if self.feed_count == 0:
            return "hungry"
        # 饥饿：连续 3 次没喂（用简单计数模拟：总次数 < 5 时更饿）
        if self.feed_count < 3:
            return "hungry"
        if self.feed_count >= 20 and self.total_exp > THRESHOLDS["stage3"]:
            return "sleepy"
        return "happy"

    def progress(self) -> dict:
        """当前阶段的成长进度（给 UI 用的进度条）"""
        s = self.stage
        if s == 1:
            cur, nxt = self.total_exp, THRESHOLDS["stage2"]
        elif s in (2, 4):
            cur, nxt = self.total_exp, THRESHOLDS["stage3"]
        else:
            cur, nxt = self.total_exp, self.total_exp
        pct = 100.0 if nxt <= 0 else min(100.0, round(cur / nxt * 100, 1))
        return {"stage": s, "exp": round(self.total_exp, 1), "next": nxt, "pct": pct}

    def top_lineage(self) -> str | None:
        """未分化时：当前喂得最多的系别"""
        if not self.lineage_exp:
            return None
        return max(self.lineage_exp, key=lambda k: self.lineage_exp[k])

    # ------------------------------------------------------------ 喂养

    def feed(self, meal_name: str, source: str = "real") -> dict:
        """喂一次。返回本次事件（供 UI/文案层使用）。"""
        assert source in SOURCE_MULT, f"未知喂养来源: {source}"
        meal_lin = classify_meal(meal_name)
        src_mult = SOURCE_MULT[source]

        event = {
            "meal": meal_name,
            "meal_lineage": meal_lin,
            "source": source,
            "lineage_before": self.lineage,
            "stage_before": self.stage,
            "exp_gained": 0.0,
            "evolved": False,
            "lineage_assigned": None,
            "variant_triggered": False,
            "message": "",
        }

        # 1) 计算本次经验
        if self.lineage is None:
            # 未分化：按来源计算，记入对应系的积累（中性食物只给少量经验）
            if meal_lin is None:
                gained = BASE_EXP * src_mult * AFFINITY["neutral"]
            else:
                gained = BASE_EXP * src_mult
                self.lineage_exp[meal_lin] = self.lineage_exp.get(meal_lin, 0.0) + gained
        else:
            same = meal_lin == self.lineage
            if same:
                gained = BASE_EXP * src_mult * AFFINITY["same"]
            else:
                gained = BASE_EXP * src_mult * AFFINITY["cross"]
                if meal_lin is not None:
                    self.hetero[meal_lin] = self.hetero.get(meal_lin, 0.0) + gained

        if meal_lin is None and self.lineage is None:
            pass  # gained 已在上面算好
        event["exp_gained"] = round(gained, 1)
        self.total_exp += gained
        self.feed_count += 1
        self.fed_meals.insert(0, meal_name)
        self.fed_meals = self.fed_meals[:20]

        # 2) 阶段晋升 / 首次定系
        stage_now = self.stage
        if self.lineage is None and stage_now >= 2:
            self.lineage = self.top_lineage() or None
            event["lineage_assigned"] = self.lineage
            event["evolved"] = True
        elif stage_now != event["stage_before"]:
            event["evolved"] = True

        # 3) 变异检查（成形后，异系值满）
        if self.lineage is not None and not self.variant:
            if self.hetero and max(self.hetero.values()) >= HETERO_LIMIT:
                self.variant = True
                event["variant_triggered"] = True
                event["evolved"] = True

        event["stage_after"] = self.stage
        event["message"] = _message_for(event, self)
        return event

    # ------------------------------------------------------------ 订单喂养（套餐感知）

    MAX_QTY_PER_ITEM = 5   # 单个品项单次最多按 5 份计（防异常数据刷经验）

    def feed_item(self, name: str, quantity: int = 1, source: str = "real") -> list[dict]:
        """喂一个品项（按份数逐份喂养），返回事件列表"""
        qty = max(1, min(int(quantity or 1), self.MAX_QTY_PER_ITEM))
        return [self.feed(name, source=source) for _ in range(qty)]

    def feed_order(self, order, source: str = "real") -> dict:
        """喂一整单 —— 套餐自动拆解成子项逐个喂养。

        items 结构（来自 order_parser）::

            [{"name": "随心配1+1套餐", "quantity": 1,
              "parts": [{"name": "高达吉士双牛堡", "quantity": 1},
                        {"name": "中杯怡泉+C", "quantity": 1}]}]

        有 parts 的品项（套餐）→ 逐个子项喂养；无 parts → 喂本品项。
        """
        items = order.get("items", []) if isinstance(order, dict) else list(order or [])
        events: list[dict] = []
        for it in items:
            parts = it.get("parts") or []
            if parts:
                for part in parts:
                    events.extend(self.feed_item(part.get("name", ""),
                                                 part.get("quantity", 1), source))
            else:
                events.extend(self.feed_item(it.get("name", ""),
                                             it.get("quantity", 1), source))

        fed: dict = {}
        for ev in events:
            key = ev["meal_lineage"] or "无"
            fed[key] = fed.get(key, 0) + 1
        return {
            "feed_count": len(events),
            "exp_gained": round(sum(e["exp_gained"] for e in events), 1),
            "lineages_fed": fed,
            "evolved": any(e["evolved"] for e in events),
            "variant": any(e["variant_triggered"] for e in events),
            "events": events,
        }

    # ------------------------------------------------------------ 序列化

    def to_dict(self) -> dict:
        return {
            "name": self.name, "lineage": self.lineage,
            "total_exp": round(self.total_exp, 1),
            "lineage_exp": {k: round(v, 1) for k, v in self.lineage_exp.items()},
            "hetero": {k: round(v, 1) for k, v in self.hetero.items()},
            "variant": self.variant, "feed_count": self.feed_count,
            "fed_meals": self.fed_meals,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Spirit":
        return cls(
            name=d.get("name", "麦麦"), lineage=d.get("lineage"),
            total_exp=d.get("total_exp", 0.0),
            lineage_exp=d.get("lineage_exp", {}), hetero=d.get("hetero", {}),
            variant=d.get("variant", False), feed_count=d.get("feed_count", 0),
            fed_meals=d.get("fed_meals", []),
        )


# ---------------------------------------------------------------- 文案

_EVOLVE_LINES = {
    "薯": "🍟 一份薯条的灵魂注入了它的身体——金薯灵诞生！",
    "牛": "🐂 双层牛肉的力量崛起了——小牛堡诞生！",
    "鸡": "🐔 它长出了第一撮鸡冠——咕咕鸡诞生！",
    "鱼": "🐟 稀有！深海的气息……鱼板仔诞生（菜单里的鱼类最少，这个系很稀有）！",
    "咖": "☕ 香气混合着它的呼吸——咖啡豆豆诞生！",
    "甜": "🍦 甜甜的奶油在头顶融化——奶油团诞生！",
}


def _message_for(event: dict, sp: Spirit) -> str:
    if event["variant_triggered"]:
        return f"⚡ 异系能量满溢……它突破了形态，变成了变异体！"
    if event["lineage_assigned"]:
        return _EVOLVE_LINES.get(event["lineage_assigned"], "它长大了一点点。")
    if event["stage_before"] < 2 and event["stage_after"] >= 2 and not event["lineage_assigned"]:
        return "它成形了！"
    if event["stage_after"] == 3 and event["stage_before"] < 3:
        return "🎉 它长成了完全体！已经是一只成熟的麦麦精灵了。"
    ml = event["meal_lineage"]
    if ml and sp.lineage and ml == sp.lineage:
        return f"（本命系加成 x1.5）它吃得特别香。"
    if ml and sp.lineage and ml != sp.lineage:
        return f"（异系 x0.5，异系值 +{event['exp_gained']}）它有点疑惑，但还是吃下去了……"
    return "它吃下去了，似乎没什么特别的感觉。"
