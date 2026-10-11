# -*- coding: utf-8 -*-
"""麦麦精灵 · 程序化 SVG 生成器（零依赖）

每种形态（系别 x 阶段 x 表情）都由参数化 SVG 实时生成，
不需要任何图片素材，天然规避版权风险。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA = os.path.normpath(os.path.join(_HERE, "..", "data", "lineage.json"))

with open(_DATA, encoding="utf-8") as _f:
    CFG = json.load(_f)

LINEAGES: dict = CFG["lineages"]
NEUTER: dict = CFG["neuter"]
RULES: dict = CFG["rules"]

# 五官与线条的墨色
INK = "#33261A"

# 阶段缩放（以脚底为锚点）
STAGE_SCALE = {0: 1.0, 1: 0.62, 2: 0.84, 3: 1.0, 4: 1.0}
STAGE_ACC_SCALE = {0: 1.0, 1: 1.0, 2: 0.74, 3: 1.0, 4: 1.0}
STAGE_NAME = {0: "蛋", 1: RULES["names"]["stage1"], 2: RULES["names"]["stage2"],
              3: RULES["names"]["stage3"], 4: RULES["names"]["variant"]}


# ---------------------------------------------------------------- 组件

def _shadow() -> str:
    return '<ellipse cx="100" cy="172" rx="46" ry="9" fill="#000000" opacity="0.16"/>'


def _body(body: str, light: str, dark: str) -> str:
    return (
        # 主体
        f'<ellipse cx="100" cy="112" rx="48" ry="56" fill="{body}"/>'
        # 顶部亮部（月牙）
        f'<path d="M60 96 A44 50 0 0 1 140 96 A60 34 0 0 0 60 96 Z" fill="{light}" opacity="0.85"/>'
        # 底部暗部
        f'<path d="M58 140 A48 56 0 0 0 142 140 A62 30 0 0 1 58 140 Z" fill="{dark}" opacity="0.45"/>'
    )


def _limbs(body: str, dark: str, mood: str) -> str:
    """小短手小短脚"""
    if mood == "sleepy":
        arms = (
            f'<ellipse cx="52" cy="136" rx="9" ry="12" fill="{body}" transform="rotate(28 52 136)"/>'
            f'<ellipse cx="148" cy="136" rx="9" ry="12" fill="{body}" transform="rotate(-28 148 136)"/>'
        )
    else:
        arms = (
            f'<ellipse cx="50" cy="126" rx="9" ry="13" fill="{body}" transform="rotate(-18 50 126)"/>'
            f'<ellipse cx="150" cy="126" rx="9" ry="13" fill="{body}" transform="rotate(18 150 126)"/>'
        )
    feet = (
        f'<ellipse cx="80" cy="164" rx="13" ry="8" fill="{dark}"/>'
        f'<ellipse cx="120" cy="164" rx="13" ry="8" fill="{dark}"/>'
    )
    return arms + feet


def _face(mood: str, stage: int) -> str:
    if mood == "sleepy":
        eyes = (
            f'<path d="M70 100 Q82 109 94 100" stroke="{INK}" stroke-width="3" '
            'fill="none" stroke-linecap="round"/>'
            f'<path d="M106 100 Q118 109 130 100" stroke="{INK}" stroke-width="3" '
            'fill="none" stroke-linecap="round"/>'
        )
        mouth = f'<path d="M95 128 Q100 131 105 128" stroke="{INK}" stroke-width="2.4" fill="none" stroke-linecap="round"/>'
    elif mood == "hungry":
        eyes = (
            f'<ellipse cx="82" cy="99" rx="13" ry="14.5" fill="#FFFFFF" stroke="{INK}" stroke-width="2"/>'
            f'<ellipse cx="118" cy="99" rx="13" ry="14.5" fill="#FFFFFF" stroke="{INK}" stroke-width="2"/>'
            f'<circle cx="84" cy="103" r="7" fill="{INK}"/><circle cx="120" cy="103" r="7" fill="{INK}"/>'
            f'<circle cx="81" cy="98" r="2.6" fill="#FFFFFF"/><circle cx="117" cy="98" r="2.6" fill="#FFFFFF"/>'
        )
        mouth = f'<ellipse cx="100" cy="130" rx="10" ry="8" fill="{INK}"/>' \
                f'<ellipse cx="100" cy="133" rx="5" ry="3.4" fill="#E8756A"/>'
    else:  # happy
        eyes = (
            f'<ellipse cx="82" cy="100" rx="12.5" ry="13.5" fill="#FFFFFF" stroke="{INK}" stroke-width="2"/>'
            f'<ellipse cx="118" cy="100" rx="12.5" ry="13.5" fill="#FFFFFF" stroke="{INK}" stroke-width="2"/>'
            f'<circle cx="83.5" cy="103" r="6.6" fill="{INK}"/><circle cx="119.5" cy="103" r="6.6" fill="{INK}"/>'
            f'<circle cx="80.8" cy="99" r="2.5" fill="#FFFFFF"/><circle cx="116.8" cy="99" r="2.5" fill="#FFFFFF"/>'
        )
        mouth = f'<path d="M88 125 Q100 135 112 125" stroke="{INK}" stroke-width="2.6" fill="none" stroke-linecap="round"/>'

    blush = (
        '<ellipse cx="63" cy="117" rx="9" ry="5" fill="#E8756A" opacity="0.42"/>'
        '<ellipse cx="137" cy="117" rx="9" ry="5" fill="#E8756A" opacity="0.42"/>'
    )
    return eyes + blush + mouth


def _acc_fries(light: str, dark: str) -> str:
    return (
        f'<rect x="83" y="34" width="9" height="30" rx="3.5" fill="{light}" transform="rotate(-10 87 49)"/>'
        f'<rect x="95.5" y="26" width="9" height="38" rx="3.5" fill="{dark}" opacity="0.85"/>'
        f'<rect x="108" y="32" width="9" height="32" rx="3.5" fill="{light}" transform="rotate(10 112 48)"/>'
    )


def _acc_horns(light: str, dark: str) -> str:
    return (
        f'<polygon points="68,70 78,40 94,64" fill="{light}" stroke="{dark}" stroke-width="2" stroke-linejoin="round"/>'
        f'<polygon points="106,64 122,40 132,70" fill="{light}" stroke="{dark}" stroke-width="2" stroke-linejoin="round"/>'
    )


def _acc_comb(light: str, dark: str) -> str:
    c = "#E24B4A"
    return (
        f'<circle cx="82" cy="54" r="9" fill="{c}" stroke="{dark}" stroke-width="1.5"/>'
        f'<circle cx="100" cy="46" r="11" fill="{c}" stroke="{dark}" stroke-width="1.5"/>'
        f'<circle cx="118" cy="54" r="9" fill="{c}" stroke="{dark}" stroke-width="1.5"/>'
    )


def _acc_fin(light: str, dark: str) -> str:
    return (
        f'<polygon points="74,66 100,28 126,66" fill="{light}" stroke="{dark}" '
        'stroke-width="2" stroke-linejoin="round"/>'
    )


def _acc_cup(light: str, dark: str) -> str:
    return (
        f'<rect x="80" y="40" width="40" height="28" rx="6" fill="{light}" stroke="{dark}" stroke-width="2"/>'
        f'<rect x="76" y="36" width="48" height="10" rx="5" fill="{dark}"/>'
        f'<path d="M92 28 Q95 22 92 16" stroke="#FFFFFF" stroke-width="3" fill="none" '
        'stroke-linecap="round" opacity="0.75"/>'
        f'<path d="M108 28 Q111 22 108 16" stroke="#FFFFFF" stroke-width="3" fill="none" '
        'stroke-linecap="round" opacity="0.75"/>'
    )


def _acc_cream(light: str, dark: str) -> str:
    return (
        f'<polygon points="82,64 100,34 118,64" fill="{light}" stroke="{dark}" stroke-width="2" stroke-linejoin="round"/>'
        f'<circle cx="100" cy="36" r="12" fill="{light}" stroke="{dark}" stroke-width="2"/>'
        f'<circle cx="100" cy="36" r="5.5" fill="{dark}" opacity="0.55"/>'
    )


_ACC = {
    "fries": _acc_fries,
    "horns": _acc_horns,
    "comb": _acc_comb,
    "fin": _acc_fin,
    "cup": _acc_cup,
    "cream": _acc_cream,
}


def _variant_mark(light: str) -> str:
    """变异体专属：星标"""
    return (
        '<g transform="translate(146 52)">'
        f'<polygon points="10,0 12.6,6.2 19.4,6.8 14.2,11.2 15.8,17.8 10,14.2 4.2,17.8 5.8,11.2 0.6,6.8 7.4,6.2" '
        f'fill="{light}" stroke="#7A5A12" stroke-width="1"/>'
        '</g>'
    )


def _egg_svg() -> str:
    spots = "".join(
        f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="#DCD2BA" opacity="0.9"/>'
        for cx, cy, rx, ry in ((80, 100, 9, 6), (118, 132, 11, 7), (94, 152, 8, 5),
                               (122, 88, 7, 5), (74, 136, 6, 4))
    )
    crack = f'<path d="M72 118 L84 112 L90 122 L100 114 L110 123 L118 116 L128 122" ' \
            f'stroke="#C9BFA6" stroke-width="3" fill="none" stroke-linecap="round"/>'
    return (
        '<ellipse cx="100" cy="120" rx="42" ry="54" fill="#F4EFE0"/>'
        f'<ellipse cx="100" cy="120" rx="42" ry="54" fill="none" stroke="#E0D6BE" stroke-width="2"/>'
        + spots + crack +
        '<ellipse cx="84" cy="88" rx="10" ry="7" fill="#FFFFFF" opacity="0.65"/>'
    )


# ---------------------------------------------------------------- 主入口

def render_spirit(lineage: str | None, stage: int, mood: str = "happy",
                  size: int = 220) -> str:
    """生成一只麦麦精灵的 SVG。

    Args:
        lineage: 六系之一（薯/牛/鸡/鱼/咖/甜），None 表示未分化
        stage:   0=蛋 1=幼体 2=成形 3=完全体 4=变异
        mood:    happy / hungry / sleepy
        size:    输出像素尺寸
    """
    title = "麦麦精灵"
    if stage == 0:
        inner = _egg_svg()
        title = "麦麦精灵的蛋"
    else:
        pal = LINEAGES.get(lineage or "", NEUTER)
        body_c, light_c, dark_c = pal["body"], pal["light"], pal["dark"]
        parts = [_shadow(), _body(body_c, light_c, dark_c)]
        if mood != "sleepy":
            parts.append(_limbs(body_c, dark_c, mood))
        else:
            parts.append(_limbs(body_c, dark_c, mood))
        # 配件
        if lineage and stage >= 2:
            acc_fn = _ACC.get(LINEAGES[lineage]["accessory"])
            if acc_fn:
                parts.append(
                    f'<g transform="translate(100 100) scale({STAGE_ACC_SCALE[stage]}) translate(-100 -100)">'
                    + acc_fn(light_c, dark_c) + '</g>'
                )
        if stage == 4:
            parts.append(_variant_mark(light_c))
        parts.append(_face(mood, stage))
        scale = STAGE_SCALE[stage]
        inner = f'<g transform="translate(100 168) scale({scale}) translate(-100 -168)">' + "".join(parts) + '</g>'
        if lineage:
            title = f"{pal['name']}{LINEAGES[lineage]['title']}（{STAGE_NAME[stage]}）"
        else:
            title = f"麦麦精灵（{STAGE_NAME[stage]}）"

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" '
        f'width="{size}" height="{size}" role="img">'
        f'<title>{title}</title>{inner}</svg>'
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="麦麦精灵 SVG 生成器")
    ap.add_argument("--lineage", default="薯", help="薯/牛/鸡/鱼/咖/甜 或 none")
    ap.add_argument("--stage", type=int, default=3, help="0蛋 1幼体 2成形 3完全体 4变异")
    ap.add_argument("--mood", default="happy", help="happy/hungry/sleepy")
    ap.add_argument("--out", default="-", help="输出文件，默认打印到 stdout")
    args = ap.parse_args()

    lin = None if args.lineage in ("none", "null", "") else args.lineage
    svg = render_spirit(lin, args.stage, args.mood)

    if args.out == "-":
        sys.stdout.write(svg)
        sys.stdout.write("\n")
    else:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(svg)
        print(f"已写入 {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
