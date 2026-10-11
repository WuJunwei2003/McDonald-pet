# -*- coding: utf-8 -*-
"""麦麦精灵 · GLB 压缩工具（构建期工具，需 Pillow）

把 3D 手办的贴图降采样 + 转 JPEG：
    4096² PNG ×3 ≈ 25MB → 1024² JPEG ≈ 1MB 级别

几何数据（accessor/bufferView）内容保持不变，只重排 offset，改动最小、可验证。

用法:
    python compress_glb.py --report <x.glb>              # 只看体积构成
    python compress_glb.py <x.glb> [--out y.glb]         # 压缩
    python compress_glb.py <x.glb> --tex 2048 --quality 90
"""
from __future__ import annotations

import argparse
import io
import json
import os
import struct
import sys

from PIL import Image

JSON_CHUNK = 0x4E4F534A   # 'JSON'
BIN_CHUNK = 0x004E4942    # 'BIN\0'


# ---------------------------------------------------------------- GLB 读写

def parse_glb(path: str):
    with open(path, "rb") as f:
        magic, version, length = struct.unpack("<III", f.read(12))
        if magic != 0x46546C67:
            raise ValueError("不是 GLB 文件")
        chunks = []
        while f.tell() < length:
            clen, ctype = struct.unpack("<II", f.read(8))
            chunks.append((ctype, f.read(clen)))
    js = json.loads(chunks[0][1])
    binc = b""
    for ctype, data in chunks[1:]:
        if ctype == BIN_CHUNK:
            binc = data
            break
    return js, binc


def build_glb(js: dict, bin_data: bytes) -> bytes:
    js_bytes = json.dumps(js, separators=(",", ":")).encode("utf-8")
    js_bytes += b" " * ((4 - len(js_bytes) % 4) % 4)
    bin_bytes = bin_data + b"\x00" * ((4 - len(bin_data) % 4) % 4)
    total = 12 + 8 + len(js_bytes) + 8 + len(bin_bytes)
    out = struct.pack("<III", 0x46546C67, 2, total)
    out += struct.pack("<II", len(js_bytes), JSON_CHUNK) + js_bytes
    out += struct.pack("<II", len(bin_bytes), BIN_CHUNK) + bin_bytes
    return out


# ---------------------------------------------------------------- 贴图语义

def _slot_of(js: dict) -> dict:
    """bufferView 索引 -> 语义槽（baseColor / metallicRoughness / normal / other）"""
    tex_slot = {}
    for mat in js.get("materials", []):
        pbr = mat.get("pbrMetallicRoughness", {})
        for key, tex in (("baseColor", pbr.get("baseColorTexture")),
                         ("metallicRoughness", pbr.get("metallicRoughnessTexture"))):
            if tex:
                tex_slot[tex["index"]] = key
        nt = mat.get("normalTexture")
        if nt:
            tex_slot[nt["index"]] = "normal"
    img_slot = {}
    for ti, t in enumerate(js.get("textures", [])):
        if "source" in t and ti in tex_slot:
            img_slot[t["source"]] = tex_slot[ti]
    out = {}
    for i, im in enumerate(js.get("images", [])):
        bv = im.get("bufferView")
        if bv is None:
            continue
        out[bv] = img_slot.get(i, "other")
    return out


# 各语义槽的压缩策略： (最长边, JPEG 质量)
POLICY = {
    "baseColor": (1024, 90),
    "metallicRoughness": (1024, 85),
    "normal": (1024, 92),
    "other": (1024, 88),
}


def _transcode(raw: bytes, tex_max: int, quality: int) -> tuple[bytes, str]:
    """PNG/JPEG -> 降采样 JPEG。返回 (data, mime)。未变小时返回原图。"""
    is_png = raw[:4] == b"\x89PNG"
    is_jpg = raw[:2] == b"\xff\xd8"
    if not (is_png or is_jpg):
        return raw, ""
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception:  # noqa: BLE001
        return raw, ""
    if img.mode in ("P", "RGBA", "LA"):
        img = img.convert("RGBA")
        bgc = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(bgc, img).convert("RGB")
    else:
        img = img.convert("RGB")
    if max(img.size) > tex_max:
        r = tex_max / max(img.size)
        img = img.resize((max(1, round(img.width * r)), max(1, round(img.height * r))),
                         Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
    out = buf.getvalue()
    if len(out) < len(raw):
        return out, "image/jpeg"
    return raw, "image/png" if is_png else "image/jpeg"


# ---------------------------------------------------------------- 主流程

def report(path: str) -> None:
    js, binc = parse_glb(path)
    bvs = js["bufferViews"]
    slot = _slot_of(js)
    total_img = 0
    print(f"文件: {path}（{os.path.getsize(path)/1e6:.1f} MB，bin {len(binc)/1e6:.1f} MB）")
    for i, im in enumerate(js.get("images", [])):
        bv = bvs[im["bufferView"]]
        raw = binc[bv.get("byteOffset", 0): bv.get("byteOffset", 0) + bv["byteLength"]]
        kind = "PNG" if raw[:4] == b"\x89PNG" else "JPEG"
        try:
            dims = Image.open(io.BytesIO(raw)).size
        except Exception:  # noqa: BLE001
            dims = "?"
        total_img += len(raw)
        print(f"  image[{i}] slot={slot.get(im['bufferView'],'?'):18s} {kind} {dims} "
              f"{len(raw)/1e6:.2f} MB")
    print(f"  贴图合计 {total_img/1e6:.1f} MB | 几何 {len(binc)/1e6 - total_img/1e6:.1f} MB")


def compress(in_path: str, out_path: str, tex_max: int, quality: int, dry: bool) -> None:
    js, binc = parse_glb(in_path)
    bvs = js["bufferViews"]
    slot = _slot_of(js)
    img_bv = {im["bufferView"] for im in js.get("images", []) if "bufferView" in im}

    new_bin = bytearray()
    before_img = after_img = 0
    for i, bv in enumerate(bvs):
        off, ln = bv.get("byteOffset", 0), bv["byteLength"]
        data = binc[off: off + ln]
        if i in img_bv:
            before_img += len(data)
            tm, q = POLICY.get(slot.get(i, "other"), POLICY["other"])
            if tex_max:
                tm = min(tm, tex_max)
            if quality:
                q = min(q, quality) if quality < q else q
            data, mime = _transcode(data, tm, q)
            if mime:
                for im in js["images"]:
                    if im.get("bufferView") == i:
                        im["mimeType"] = mime
            after_img += len(data)
        pad = (4 - len(new_bin) % 4) % 4
        new_bin.extend(b"\x00" * pad)
        bv["byteOffset"] = len(new_bin)
        bv["byteLength"] = len(data)
        new_bin.extend(data)

    js["buffers"][0]["byteLength"] = len(new_bin)
    blob = build_glb(js, bytes(new_bin))

    src = os.path.getsize(in_path)
    print(f"{os.path.basename(in_path)}: {src/1e6:.1f} MB -> {len(blob)/1e6:.1f} MB"
          f"（贴图 {before_img/1e6:.1f} -> {after_img/1e6:.1f} MB）")
    if dry:
        return
    with open(out_path, "wb") as f:
        f.write(blob)
    print(f"  已写出 {out_path}")


def main() -> int:
    ap = argparse.ArgumentParser(description="GLB 压缩")
    ap.add_argument("glb")
    ap.add_argument("--out", default=None, help="输出路径（默认原地加后缀 _min）")
    ap.add_argument("--tex", type=int, default=1024, help="贴图最长边（0=不缩放）")
    ap.add_argument("--quality", type=int, default=95, help="JPEG 质量上限")
    ap.add_argument("--report", action="store_true", help="只报告体积构成")
    ap.add_argument("--dry", action="store_true", help="只计算不写文件")
    args = ap.parse_args()

    if args.report:
        report(args.glb)
        return 0
    out = args.out
    if not out:
        base, ext = os.path.splitext(args.glb)
        out = base + "_min" + ext
    compress(args.glb, out, args.tex, args.quality, args.dry)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
