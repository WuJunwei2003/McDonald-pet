# -*- coding: utf-8 -*-
"""麦麦精灵 · 素材预处理（构建期工具，仅此工具需要 Pillow）

把 ../picture/ 里的原始图抠成透明 PNG，裁剪归一化到 512x512，
输出到 ../assets/spirits/，并生成 QA 对照图到 tools/_qa/。

算法（无外部依赖）：
    1) 采样边缘环带中位数作为背景色
    2) 逐像素最大通道差 < 阈值 → 候选背景
    3) 白色描边保护（min(r,g,b) 高且饱和度低 → 不侵蚀）
    4) 从四边 BFS 漫水，只吃掉与边缘连通的背景
    5) 只保留与画面中心连通的最大组件（去掉散落的星星/爱心/地面阴影）
    6) alpha 羽化 → 裁剪 → 方形留边 → 512x512

用法:
    python prepare_spirits.py                 # 处理全部
    python prepare_spirits.py --only fries_m  # 只处理指定条目
    python prepare_spirits.py --qa            # 只重新生成 QA 对照图
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import deque

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))                    # mcpet/
PICTURE_DIR = os.path.normpath(os.path.join(ROOT, "..", "picture"))  # 工作区/picture
OUT_DIR = os.path.normpath(os.path.join(ROOT, "assets", "spirits"))
QA_DIR = os.path.normpath(os.path.join(HERE, "_qa"))

# (slug, 源文件名, 中文名, 系别, 层级)  层级：2 成形 / 3 完全体 / 4 变异 / 9 备用池
ITEMS = [
    # 薯系
    ("fries_m",                  "中薯条.png",                          "中薯条",        "薯", 2),
    ("fries_wave",               "波纹薯条.png",                        "波纹薯条",      "薯", 3),
    ("fries_ring",               "环形薯条.png",                        "环形薯条",      "薯", 4),
    # 牛系
    ("beef_single",              "牛肉堡（一层牛肉一层芝士一层番茄）.png", "芝士牛堡",      "牛", 2),
    ("beef_double",              "牛肉堡（两层牛肉）.png",               "双层牛堡",      "牛", 3),
    ("beef_double_cheese",       "牛肉堡（两层牛肉两层芝士）.png",        "芝士双层牛堡",  "牛", 4),
    # 鸡系
    ("chicken_burger",           "麦香鸡.png",                          "麦香鸡",        "鸡", 2),
    ("chicken_thigh",            "炸鸡大腿.png",                        "脆鸡大腿",      "鸡", 3),
    ("chicken_drum",             "炸鸡小腿.png",                        "脆鸡小腿",      "鸡", 4),
    # 鱼系（菜单里鱼类最少 → 只有一种形态，正好点题「稀有」）
    ("fish_burger",              "麦香鱼.png",                          "麦香鱼",        "鱼", 2),
    # 咖系
    ("coffee_bean",              "咖啡豆.png",                          "咖啡豆",        "咖", 2),
    ("coffee_cup_beans",         "一杯咖啡豆.png",                      "一杯咖啡豆",    "咖", 3),
    ("coffee_cup_drink",         "一杯咖啡液.png",                      "一杯咖啡",      "咖", 4),
    ("coffee_cup_beans2",        "一杯咖啡豆2.png",                     "咖啡豆杯·外带", "咖", 9),
    ("coffee_cup_drink2",        "一杯咖啡液2.png",                     "咖啡·外带",     "咖", 9),
    # 甜系
    ("sundae",                   "圣代.png",                            "圣代",          "甜", 2),
    ("sundae_cherry",            "圣代+车厘子.png",                     "车厘子圣代",    "甜", 3),
    ("sundae_strawberry_heavy",  "圣代+大量草莓酱.png",                  "草莓圣代",      "甜", 4),
    ("sundae_strawberry_light",  "圣代+少量草莓酱.png",                  "轻草莓圣代",    "甜", 9),
    ("sundae_oreo",              "圣代+少量奥利奥碎.png",                "奥利奥圣代",    "甜", 9),
    ("sundae_choco",             "圣代+少量巧克力酱.png",                "巧克力圣代",    "甜", 9),
]

# 个别图片阈值覆盖（默认 80；背景越花/对比越低越需要调大，但别大到吃穿白描边）
THRESH_OVERRIDE = {
    "beef_double_cheese": 120,   # 背景是闪光砂砾质感，颜色不匀
    "sundae_strawberry_heavy": 95,
    "fries_ring": 95,
}

CANVAS = 512
MARGIN = 0.06          # 方形画布四周留边比例
WHITE_MIN = 232        # min(r,g,b) ≥ 此值 且 spread < WHITE_SPREAD → 视为白描边，不侵蚀
WHITE_SPREAD = 22
ALPHA_FEATHER = 0.6
CLEAN_BELOW = 16       # alpha 低于此值的像素，RGB 清零（防缩放黑边）


# ---------------------------------------------------------------- 工具

def _solid(size, v):
    return Image.new("L", size, v)


def _dist_img(img: Image.Image, bg: tuple[int, int, int]) -> Image.Image:
    """每像素与背景色的最大通道差（L 模式，0~255）"""
    r, g, b = img.split()
    d = ImageChops.lighter(
        ImageChops.lighter(
            ImageChops.difference(r, _solid(img.size, bg[0])),
            ImageChops.difference(g, _solid(img.size, bg[1])),
        ),
        ImageChops.difference(b, _solid(img.size, bg[2])),
    )
    return d


def _whiteish_mask(img: Image.Image) -> Image.Image:
    """白描边保护掩码：255 = 疑似白描边（不侵蚀）"""
    r, g, b = img.split()
    mn = ImageChops.darker(ImageChops.darker(r, g), b)
    mx = ImageChops.lighter(ImageChops.lighter(r, g), b)
    spread = ImageChops.subtract(mx, mn)
    mn_ok = mn.point(lambda v: 255 if v >= WHITE_MIN else 0)
    sp_ok = spread.point(lambda v: 255 if v < WHITE_SPREAD else 0)
    return ImageChops.multiply(mn_ok, sp_ok)


def _bfs(mask: bytes, w: int, h: int, seeds) -> bytearray:
    """4 邻域 BFS。mask：每像素 0/非0；返回 visited(bytearray)"""
    visited = bytearray(w * h)
    dq = deque()
    for i in seeds:
        if not visited[i] and mask[i]:
            visited[i] = 1
            dq.append(i)
    last_row = w * (h - 1)
    while dq:
        i = dq.popleft()
        x = i % w
        if x > 0:
            n = i - 1
            if not visited[n] and mask[n]:
                visited[n] = 1
                dq.append(n)
        if x < w - 1:
            n = i + 1
            if not visited[n] and mask[n]:
                visited[n] = 1
                dq.append(n)
        if i >= w:
            n = i - w
            if not visited[n] and mask[n]:
                visited[n] = 1
                dq.append(n)
        if i < last_row:
            n = i + w
            if not visited[n] and mask[n]:
                visited[n] = 1
                dq.append(n)
    return visited


def _border_bg(img: Image.Image) -> tuple[int, int, int]:
    """边缘环带取中位数颜色作为背景色"""
    w, h = img.size
    px = img.load()
    samples = []
    step = max(1, min(w, h) // 80)
    for x in range(0, w, step):
        samples.append(px[x, 0])
        samples.append(px[x, h - 1])
    for y in range(0, h, step):
        samples.append(px[0, y])
        samples.append(px[w - 1, y])
    rs = sorted(s[0] for s in samples)
    gs = sorted(s[1] for s in samples)
    bs = sorted(s[2] for s in samples)
    mid = len(samples) // 2
    return (rs[mid], gs[mid], bs[mid])


# ---------------------------------------------------------------- 单张处理

def process_one(slug: str, fname: str, cn: str, thr: int) -> dict:
    path = os.path.join(PICTURE_DIR, fname)
    img = Image.open(path).convert("RGB")
    w, h = img.size

    bg = _border_bg(img)
    dist = _dist_img(img, bg)
    white = _whiteish_mask(img)

    cand = ImageChops.multiply(
        dist.point(lambda v: 255 if v < thr else 0),
        white.point(lambda v: 255 - v),
    )
    mask = cand.tobytes()

    # 从四边 BFS 吃背景（只吃与边缘连通的候选像素）
    seeds = []
    seeds.extend(range(0, w))
    seeds.extend(range(w * (h - 1), w * h))
    seeds.extend(range(0, w * h, w))
    seeds.extend(range(w - 1, w * h, w))
    eaten = _bfs(mask, w, h, seeds)

    alpha = bytearray(b"\xff" * (w * h))
    for i in range(w * h):
        if eaten[i]:
            alpha[i] = 0

    # 只保留与画面中心连通的主组件（去掉散落的星星 / 爱心 / 地面阴影）
    fg = bytes(a for a in alpha)
    cx, cy = w // 2, h // 2
    best_i, best_d = -1, 1 << 62
    for i in range(w * h):
        if fg[i]:
            x = i % w
            y = i // w
            d = (x - cx) ** 2 + (y - cy) ** 2
            if d < best_d:
                best_d, best_i = d, i
    if best_i < 0:
        raise RuntimeError("抠图失败：没有剩下任何前景像素（阈值过高？）")
    keep = _bfs(fg, w, h, [best_i])

    alpha = bytearray(w * h)
    for i in range(w * h):
        if keep[i]:
            alpha[i] = 255

    a_img = Image.frombytes("L", (w, h), bytes(alpha))
    a_img = a_img.filter(ImageFilter.GaussianBlur(ALPHA_FEATHER))
    a_img = a_img.point(lambda v: v if v >= CLEAN_BELOW else 0)

    out = img.convert("RGBA")
    out.putalpha(a_img)
    # RGB 清零在透明区（防缩放黑边）
    zero = Image.new("RGBA", out.size, (0, 0, 0, 0))
    out = Image.composite(out, zero, a_img)

    bbox = a_img.getbbox()
    if bbox is None:
        raise RuntimeError("抠图失败：alpha 全空")
    out = out.crop(bbox)

    ow, oh = out.size
    side = int(max(ow, oh) * (1 + MARGIN * 2))
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(out, ((side - ow) // 2, (side - oh) // 2), out)
    canvas = canvas.resize((CANVAS, CANVAS), Image.LANCZOS)

    os.makedirs(OUT_DIR, exist_ok=True)
    dst = os.path.join(OUT_DIR, slug + ".png")
    canvas.save(dst)

    kept = sum(1 for a in alpha if a)
    return {
        "slug": slug, "cn": cn, "src": fname,
        "src_size": [w, h], "bg": list(bg), "thr": thr,
        "bbox": list(bbox), "kept_ratio": round(kept / (w * h), 3),
        "out": dst,
    }


# ---------------------------------------------------------------- QA 对照图

def build_qa(slugs: list[str] | None = None) -> str:
    os.makedirs(QA_DIR, exist_ok=True)
    rows, cols = 7, 3
    cell_w, cell_h = 300, 330
    pad = 8
    sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), (38, 38, 38))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 16)
        font_small = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 13)
    except Exception:
        font = ImageFont.load_default()
        font_small = font

    items = [it for it in ITEMS if (slugs is None or it[0] in slugs)]
    for n, (slug, _f, cn, lin, tier) in enumerate(items):
        r, c = divmod(n, cols)
        x0, y0 = c * cell_w, r * cell_h
        bg_col = (232, 232, 232) if (r + c) % 2 == 0 else (24, 24, 24)
        draw.rectangle([x0 + 3, y0 + 3, x0 + cell_w - 4, y0 + cell_h - 4], fill=bg_col)
        p = os.path.join(OUT_DIR, slug + ".png")
        if os.path.exists(p):
            im = Image.open(p).convert("RGBA")
            im.thumbnail((cell_w - 2 * pad - 20, cell_h - 2 * pad - 44), Image.LANCZOS)
            px = x0 + (cell_w - im.width) // 2
            py = y0 + 10
            sheet.paste(im, (px, py), im)
        tc = (20, 20, 20) if bg_col[0] > 128 else (235, 235, 235)
        draw.text((x0 + 16, y0 + cell_h - 48), f"{slug} · {cn}", fill=tc, font=font)
        draw.text((x0 + 16, y0 + cell_h - 26), f"{lin}系 · {'备用' if tier == 9 else 'T' + str(tier)}", fill=tc, font=font_small)

    dst = os.path.join(QA_DIR, "qa_sheet.png")
    sheet.save(dst)
    return dst


# ---------------------------------------------------------------- 主流程

def main() -> int:
    ap = argparse.ArgumentParser(description="麦麦精灵素材预处理")
    ap.add_argument("--only", nargs="*", help="只处理指定 slug")
    ap.add_argument("--qa", action="store_true", help="只重新生成 QA 对照图")
    args = ap.parse_args()

    if args.qa:
        print("QA ->", build_qa())
        return 0

    results = []
    ok, fail = 0, 0
    for slug, fname, cn, lin, tier in ITEMS:
        if args.only and slug not in args.only:
            continue
        thr = THRESH_OVERRIDE.get(slug, 80)
        try:
            info = process_one(slug, fname, cn, thr)
            results.append(info)
            ok += 1
            warn = " ⚠️" if info["kept_ratio"] < 0.08 else ""
            print(f"  ✅ {slug:24s} bg={info['bg']} thr={thr:3d} "
                  f"kept={info['kept_ratio']:.0%}{warn}")
        except Exception as e:  # noqa: BLE001
            fail += 1
            print(f"  ❌ {slug:24s} {e}")

    # 写 manifest
    manifest = {
        "canvas": CANVAS,
        "items": [
            {"slug": s, "file": f"assets/spirits/{s}.png", "src": f, "cn": cn,
             "lineage": lin, "tier": tier}
            for s, f, cn, lin, tier in ITEMS
        ],
    }
    mpath = os.path.join(ROOT, "assets", "spirits", "manifest.json")
    with open(mpath, "w", encoding="utf-8") as fp:
        json.dump(manifest, fp, ensure_ascii=False, indent=2)
    print(f"\n完成：{ok} 成功 / {fail} 失败，manifest -> {mpath}")
    print("QA ->", build_qa())
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
