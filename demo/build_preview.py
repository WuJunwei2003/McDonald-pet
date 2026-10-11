# -*- coding: utf-8 -*-
"""生成麦麦精灵形态谱预览页（真实素材图 · 六系进化线）

读取 data/forms.json 与 assets/spirits/ 的实际素材，生成静态展示页。
"""
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.normpath(os.path.join(_HERE, ".."))
OUT = os.path.join(_HERE, "preview.html")

with open(os.path.join(_ROOT, "data", "forms.json"), encoding="utf-8") as f:
    FORMS = json.load(f)

LINEAGE_ORDER = ["薯", "牛", "鸡", "鱼", "咖", "甜"]
LIN_COLOR = {"薯": "#F5A742", "牛": "#D85A30", "鸡": "#F0E3C8",
             "鱼": "#85B7EB", "咖": "#9A6B44", "甜": "#ED93B1"}
TIER_LABEL = {"2": "成形", "3": "完全体", "4": "变异体"}


def cell(slug: str, tier: str, name: str, desc: str) -> str:
    return f'''<div class="cell" title="{desc}">
      <img src="../assets/spirits/{slug}.png" alt="{name}">
      <div class="t">{TIER_LABEL.get(tier, "")}</div>
      <div class="n">{name}</div>
    </div>'''


def lineage_row(lin: str) -> str:
    tiers = FORMS["lineages"][lin]
    cells = []
    seen = set()
    for t in ("2", "3", "4"):
        e = tiers[t]
        if e["slug"] in seen:
            continue
        seen.add(e["slug"])
        if cells:
            cells.append('<span class="arrow">→</span>')
        cells.append(cell(e["slug"], t, e["name"], e.get("desc", "")))
    only = '<span class="only">唯一形态（菜单里鱼类最少）</span>' if len(seen) == 1 else ""
    return f'''<div class="line">
      <div class="head"><span class="dot" style="background:{LIN_COLOR[lin]}"></span>
        六系 · {lin}系{only}</div>
      <div class="cells">{"".join(cells)}</div>
    </div>'''


def build() -> str:
    lines = "".join(lineage_row(lin) for lin in LINEAGE_ORDER)
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>麦麦精灵 · 六系进化谱</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:#141414; color:#e8e8e8;
         font-family:"Microsoft YaHei","PingFang SC",system-ui,sans-serif;
         padding:40px 32px 64px; }}
  h1 {{ font-size:22px; font-weight:600; margin-bottom:8px; }}
  .desc {{ color:#9a9a9a; font-size:13px; line-height:1.9; margin-bottom:30px; }}
  .lines {{ display:grid; grid-template-columns:repeat(2,1fr); gap:14px; max-width:1060px; }}
  .line {{ background:#1d1d1d; border:1px solid #2c2c2c; border-radius:16px; padding:14px 16px; }}
  .head {{ display:flex; align-items:center; gap:8px; font-size:13.5px; color:#cfcfcf; margin-bottom:12px; }}
  .dot {{ width:10px; height:10px; border-radius:50%; }}
  .only {{ font-size:11px; color:#9a9a9a; border:1px solid #2c2c2c; border-radius:99px; padding:1px 8px; }}
  .cells {{ display:flex; align-items:flex-start; gap:4px; }}
  .cell {{ flex:1; text-align:center; }}
  .cell img {{ height:96px; width:auto; filter:drop-shadow(0 8px 14px rgba(0,0,0,.45));
              transition:transform .18s ease; }}
  .cell:hover img {{ transform:translateY(-4px) scale(1.1); }}
  .cell .t {{ font-size:11px; color:#7a7a7a; margin-top:6px; }}
  .cell .n {{ font-size:12px; color:#b8b8b8; margin-top:2px; }}
  .arrow {{ color:#4a4a4a; font-size:13px; padding-top:36px; }}
  .foot {{ margin-top:30px; color:#8a8a8a; font-size:13px; line-height:2; max-width:860px; }}
  code {{ background:#242424; padding:1px 6px; border-radius:4px; color:#7fe0c3; font-size:12px; }}
</style>
</head>
<body>
  <h1>麦麦精灵 · 六系进化谱</h1>
  <p class="desc">
    形态素材由 <code>picture/</code> 原创形象经 <code>tools/prepare_spirits.py</code> 抠图归一化（512² 透明 PNG），
    按 <code>data/forms.json</code> 绑定到「系别 × 阶段」。<br>
    规则：喂什么变什么 —— 幼体期喂得最多的系别决定成形方向；本命系 ×1.5，异系 ×0.5 并累积变异能量。
  </p>
  <div class="lines">{lines}</div>
  <p class="foot">
    网页版里这些形态会随你的真实订单成长实时切换，并配有立体舞台与 3D 手办柜：
    运行 <code>python app.py</code> 体验。本页为实际素材渲染效果，非示意图。
  </p>
</body>
</html>'''


def main() -> int:
    html = build()
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"预览已生成: {OUT} ({(os.path.getsize(OUT) / 1024):.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
