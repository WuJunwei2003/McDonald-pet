# -*- coding: utf-8 -*-
"""麦麦精灵 CLI —— 孵化 / 同步订单 / 喂养（库存制）/ 状态 / 形象

数据流：同步订单 → 食物入库（薯条×3、巨无霸×1）→ 从库存喂给精灵

用法：
    python mcpet.py hatch                      # 孵化一颗蛋
    python mcpet.py sync                       # 同步真实订单 → 食物入库（需 MCP Token）
    python mcpet.py simulate                   # 用模拟订单入库（无需 Token，体验用）
    python mcpet.py pantry                     # 查看食物库存
    python mcpet.py feed "薯条"                 # 从库存喂一份
    python mcpet.py status                     # 查看精灵状态
    python mcpet.py show --out spirit.png      # 导出精灵形象（形态素材图）
    python mcpet.py show --out spirit.svg      # 导出精灵形象（SVG 兜底形态）
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "src"))

from feeding import Spirit, classify_meal          # noqa: E402
from order_parser import parse_order_list, extract_json  # noqa: E402
from pantry import Pantry                          # noqa: E402
from spirit_gen import render_spirit, LINEAGES     # noqa: E402
from state import StateStore                       # noqa: E402

STAGE_LABEL = {1: "幼体", 2: "成形", 3: "完全体", 4: "变异体"}


def _load_all(state_path=None) -> tuple[Spirit | None, Pantry]:
    d = StateStore(state_path).load()
    if not d:
        return None, Pantry()
    sp = Spirit.from_dict(d["spirit"]) if d.get("spirit") else None
    return sp, Pantry.from_dict(d.get("pantry"))


def _save_all(sp: Spirit, pantry: Pantry, state_path=None) -> None:
    StateStore(state_path).save(sp.to_dict(), pantry.to_dict())


def _lin_tag(name: str) -> str:
    lin = classify_meal(name)
    return f"({lin})" if lin else "(—)"


def _fmt_added(added: dict) -> str:
    if not added:
        return "（无新食物）"
    return "、".join(f"{k}×{v}" for k, v in sorted(added.items(), key=lambda kv: -kv[1]))


# ---------------------------------------------------------------- 命令

def cmd_hatch(args) -> int:
    store = StateStore(args.state)
    sp, pantry = _load_all(args.state)
    if sp is not None and not args.force:
        print(f"你已经有一只精灵了：「{sp.name}」。加 --force 可以重开一颗蛋（食物库存保留）。")
        return 1
    sp = Spirit(name=args.name or "麦麦")
    _save_all(sp, pantry, args.state)
    print(f"🥚 一颗麦麦精灵的蛋出现了！名字：{sp.name}")
    print("   下一步：python mcpet.py sync（同步订单获得食物）或 simulate（模拟体验）")
    return 0


def _import_orders(args, orders: list[dict], source_label: str) -> int:
    sp, pantry = _load_all(args.state)
    if sp is None:
        print("还没有精灵，先执行：python mcpet.py hatch")
        return 1
    result = pantry.import_orders(orders)
    _save_all(sp, pantry, args.state)
    print(f"{source_label}：新增 {result['new_orders']} 单"
          f"（跳过已入库 {result['skipped']} 单）")
    print(f"🍱 本次入库：{_fmt_added(result['added'])}")
    print(f"   当前库存共 {pantry.total} 份食物："
          + "、".join(f"{k}×{v}" for k, v in pantry.sorted_items()[:10]))
    print("   下一步：python mcpet.py feed \"食物名\"  喂给精灵")
    return 0


def cmd_sync(args) -> int:
    sp, _ = _load_all(args.state)
    if sp is None:
        print("还没有精灵，先执行：python mcpet.py hatch")
        return 1
    try:
        from mcp_client import McdClient, McdError
    except ImportError as e:
        print(f"加载 MCP 客户端失败：{e}")
        return 1
    try:
        client = McdClient()
    except McdError as e:
        print(f"⚠️  {e}")
        print("   设置环境变量 MCD_MCP_TOKEN（或在 mcpet 目录放 .mcpet.token）后重试。")
        return 1

    print("🔄 正在拉取真实订单…")
    try:
        raw = client.order_list()
    except McdError as e:
        print(f"⚠️  订单查询失败：{e}")
        return 1
    text = client.extract_text(raw) or ""
    data = extract_json(text)
    if not data:
        print("⚠️  未能从返回中解析出订单 JSON（接口格式可能变化）")
        return 1
    orders = parse_order_list(data)[: args.limit]
    if not orders:
        print("📭 没有找到已完成的订单。先去吃一顿麦当劳吧～")
        return 1
    return _import_orders(args, orders, "📦 真实订单同步")


def cmd_simulate(args) -> int:
    sp, _ = _load_all(args.state)
    if sp is None:
        print("还没有精灵，先执行：python mcpet.py hatch")
        return 1
    sim_path = os.path.join(_HERE, "data", "sim_orders.json")
    with open(sim_path, encoding="utf-8") as f:
        raw = json.load(f)
    orders = parse_order_list(raw)
    return _import_orders(args, orders, "🎲 模拟订单入库")


def cmd_pantry(args) -> int:
    _, pantry = _load_all(args.state)
    if pantry.total == 0:
        print("🍱 食物库存为空。先同步订单：python mcpet.py sync（或 simulate 模拟体验）")
        return 0
    print(f"🍱 食物库存（共 {pantry.total} 份）：")
    for name, qty in pantry.sorted_items():
        print(f"   {name}×{qty}  {_lin_tag(name)}")
    if pantry.imported:
        print(f"   已入库订单 {len(pantry.imported)} 单（重复同步会自动去重）")
    return 0


def cmd_feed(args) -> int:
    sp, pantry = _load_all(args.state)
    if sp is None:
        print("还没有精灵，先执行：python mcpet.py hatch")
        return 1
    meal = args.meal
    taken = pantry.take(meal)                    # 支持模糊名（"薯条"→"中薯条"）
    if taken is None and not args.force:
        print(f"⚠️ 库存里没有「{meal}」了。")
        print("   补充食物：python mcpet.py sync（真实订单）或 simulate（模拟）")
        if pantry.total:
            print("   当前库存：" + "、".join(f"{k}×{v}" for k, v in pantry.sorted_items()))
        else:
            print("   当前库存为空。")
        return 1
    meal_name = taken or meal                    # --force 时直接用输入名
    ev = sp.feed(meal_name, source=args.source)
    _save_all(sp, pantry, args.state)
    left = pantry.count(meal_name)
    hint = f"（匹配到「{meal_name}」）" if taken and taken != meal else ""
    print(f"🍽️  喂了一个「{meal_name}」{hint}（{_lin_tag(meal_name)}，库存剩余 {left} 份）")
    print(f"    {ev['message']}")
    print(f"    经验 +{ev['exp_gained']} → 总 {sp.total_exp:.1f} ｜ 阶段：{STAGE_LABEL.get(sp.stage, sp.stage)}")
    if sp.lineage:
        print(f"    当前系别：{LINEAGES[sp.lineage]['name']} ｜ 异系值：{sp.hetero or '无'}")
    return 0


def cmd_status(args) -> int:
    sp, pantry = _load_all(args.state)
    if sp is None:
        print("还没有精灵，先执行：python mcpet.py hatch")
        return 1
    p = sp.progress()
    print(f"📛 {sp.name}")
    print(f"   阶段：{STAGE_LABEL.get(sp.stage, sp.stage)} ｜ 心情：{sp.mood}")
    print(f"   经验：{p['exp']} / {p['next']}（{p['pct']}%）")
    if sp.lineage:
        print(f"   系别：{LINEAGES[sp.lineage]['name']}（{LINEAGES[sp.lineage]['title']}）")
    else:
        print(f"   系别：未分化（喂得最多的是：{sp.top_lineage() or '暂无'}）")
        print(f"   系别积累：{ {k: round(v, 1) for k, v in sp.lineage_exp.items()} }")
    if sp.hetero:
        print(f"   异系值：{ {k: round(v, 1) for k, v in sp.hetero.items()} }（满 20 触发变异）")
    print(f"   累计喂养：{sp.feed_count} 次")
    print(f"   🍱 食物库存：{pantry.total} 份"
          + ("（" + "、".join(f"{k}×{v}" for k, v in pantry.sorted_items()[:6]) + "）" if pantry.total else ""))
    return 0


def _form_image(sp) -> str | None:
    """当前形态对应的素材图路径（不存在返回 None）"""
    lin = sp.lineage or sp.top_lineage()
    if not lin:
        return None
    tier = "2" if not sp.lineage else str(sp.stage)
    try:
        with open(os.path.join(_HERE, "data", "forms.json"), encoding="utf-8") as f:
            forms = json.load(f)
    except OSError:
        return None
    e = forms["lineages"].get(lin, {}).get(tier)
    if not e:
        return None
    p = os.path.join(_HERE, "assets", "spirits", e["slug"] + ".png")
    return p if os.path.exists(p) else None


def cmd_show(args) -> int:
    sp, _ = _load_all(args.state)
    if sp is None:
        print("还没有精灵，先执行：python mcpet.py hatch")
        return 1
    out = args.out
    want_png = bool(out) and out.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
    img = None if args.svg else _form_image(sp)

    if want_png:
        if not img:
            print("⚠️ 当前形态没有对应素材图（未喂过 / 素材缺失），可改用：--out spirit.svg")
            return 1
        import shutil
        shutil.copyfile(img, out)
        print(f"✅ 精灵形态素材已导出：{out}")
        return 0

    svg = render_spirit(sp.lineage, sp.stage, sp.mood)
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(svg)
        print(f"✅ 精灵形象已导出（SVG 兜底形态）：{out}")
    else:
        sys.stdout.write(svg + "\n")
        if img:
            sys.stderr.write(f"（当前形态素材图：{img}；用 --out xxx.png 可直接导出）\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="mcpet", description="麦麦精灵 · 命令行")
    ap.add_argument("--state", default=None, help="状态文件路径（默认 ~/.mcpet/spirit.json）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("hatch", help="孵化一颗蛋")
    p.add_argument("--name", default=None)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_hatch)

    p = sub.add_parser("sync", help="同步真实订单 → 食物入库（需 MCP Token）")
    p.add_argument("--limit", type=int, default=30, help="最多取前 N 单")
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("simulate", help="模拟订单入库（无需 Token）")
    p.set_defaults(func=cmd_simulate)

    p = sub.add_parser("pantry", help="查看食物库存")
    p.set_defaults(func=cmd_pantry)

    p = sub.add_parser("feed", help="从库存喂一份食物")
    p.add_argument("meal", help="食物名（需在库存中），如：薯条 / 巨无霸")
    p.add_argument("--source", default="real", choices=["real", "daily", "event"])
    p.add_argument("--force", action="store_true", help="跳过库存检查（调试用）")
    p.set_defaults(func=cmd_feed)

    p = sub.add_parser("status", help="查看精灵状态")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("show", help="导出精灵形象（默认 SVG，--out xxx.png 导出形态素材）")
    p.add_argument("--out", default=None, help="输出文件：x.svg（兜底形态）/ x.png（形态素材）；缺省打印到终端")
    p.add_argument("--svg", action="store_true", help="强制输出 SVG（忽略形态素材）")
    p.set_defaults(func=cmd_show)
    return ap


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
