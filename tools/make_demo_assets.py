# -*- coding: utf-8 -*-
"""试玩页专用素材优化：把 assets/spirits 的 PNG 转成 WebP（512 全尺寸 + 128 缩略图）

背景：试玩页原本加载 21 张 PNG（合计 ~5MB），是首屏慢的主因。
WebP 在同等画质下体积约为 PNG 的 1/5，且全平台浏览器已支持。

构建期工具（需要 Pillow），产物提交到仓库（docs/demo/assets/spirits/）：
    python tools/make_demo_assets.py            # 增量：已存在的跳过
    python tools/make_demo_assets.py --force    # 全量重转
"""
from __future__ import annotations

import argparse
import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.normpath(os.path.join(HERE, "..", "assets", "spirits"))
DST = os.path.normpath(os.path.join(HERE, "..", "docs", "demo", "assets", "spirits"))

BIG = (512, 512)
SMALL = (128, 128)


def convert(png_path: str, force: bool = False) -> str:
    slug = os.path.splitext(os.path.basename(png_path))[0]
    big = os.path.join(DST, slug + ".webp")
    small = os.path.join(DST, slug + ".sm.webp")
    if not force and os.path.exists(big) and os.path.exists(small):
        return "skip"
    im = Image.open(png_path).convert("RGBA")
    im.resize(BIG, Image.LANCZOS).save(big, "WEBP", quality=85, method=4)
    im.resize(SMALL, Image.LANCZOS).save(small, "WEBP", quality=82, method=4)
    return "ok"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="全量重转（默认增量）")
    args = ap.parse_args()

    os.makedirs(DST, exist_ok=True)
    pngs = sorted(f for f in os.listdir(SRC) if f.lower().endswith(".png"))
    if not pngs:
        print(f"没有找到 PNG：{SRC}")
        return 1

    total_in = total_out = 0
    for f in pngs:
        src = os.path.join(SRC, f)
        result = convert(src, args.force)
        slug = os.path.splitext(f)[0]
        big = os.path.join(DST, slug + ".webp")
        small = os.path.join(DST, slug + ".sm.webp")
        sz_in = os.path.getsize(src)
        sz_out = (os.path.getsize(big) if os.path.exists(big) else 0) + \
                 (os.path.getsize(small) if os.path.exists(small) else 0)
        total_in += sz_in
        total_out += sz_out
        print(f"{result:4} {f:34} {sz_in // 1024:4}KB -> {sz_out // 1024:3}KB (webp+thumb)")
    print(f"\n合计: {total_in // 1024}KB -> {total_out // 1024}KB "
          f"（压缩率 {100 - total_out * 100 // max(total_in, 1)}%）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
