# -*- coding: utf-8 -*-
"""麦麦精灵 · 图生 3D 封装（直调官方 buddy-cloud.py）

为什么需要它：
    buddy-cloud.py 的 --image-base64 是命令行参数，Windows 命令行有约 32K 字符
    上限，512px 图片的 base64 放不进去。本封装在进程内直接构造 argv 并调用其
    main()，图片不经过命令行，也不上传任何第三方图床。

用法:
    echo -n "<token>" | python gen3d.py <图片> [选项]

选项:
    --pbr               开启 PBR 材质
    --no-pbr            关闭 PBR（默认关）
    --face-count N      面数（默认 300000）
    --prompt "..."      可选文本提示
    --model X           模型版本（3.0/3.1，默认 3.1）
    --no-poll           只提交不等待（返回 job_id）
    --out-dir DIR       产物下载目录（默认 tools/_3d）
    --no-download       不自动下载产物
"""
from __future__ import annotations

import argparse
import base64
import importlib.util
import io
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.join(HERE, "_3d")
SCRIPT = ("D:/Workbuddy/resources/app.asar.unpacked/resources/plugins/"
          "workbuddy-builtin/skills/buddy-multimodal-generation/scripts/buddy-cloud.py")


def _flatten_white(path: str, out_path: str) -> str:
    """RGBA → 白底 RGB（3D 生成输入更稳），返回新文件路径"""
    from PIL import Image
    im = Image.open(path)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        im = Image.alpha_composite(bg, im).convert("RGB")
    else:
        im = im.convert("RGB")
    im.save(out_path)
    return out_path


def _download(url: str, dst: str) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "mcpet/1.0"})
        with urllib.request.urlopen(req, timeout=300) as r, open(dst, "wb") as f:
            f.write(r.read())
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[warn] 下载失败 {url} -> {e}", file=sys.stderr)
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="麦麦精灵图生3D")
    ap.add_argument("image", help="输入图片路径")
    ap.add_argument("--pbr", dest="pbr", action="store_true", help="开启 PBR")
    ap.add_argument("--no-pbr", dest="pbr", action="store_false")
    ap.set_defaults(pbr=False)
    ap.add_argument("--face-count", type=int, default=300000)
    ap.add_argument("--prompt", default="")
    ap.add_argument("--model", default="3.1")
    ap.add_argument("--no-poll", action="store_true")
    ap.add_argument("--out-dir", default=DEFAULT_OUT)
    ap.add_argument("--no-download", action="store_true")
    ap.add_argument("--skip-existing", action="store_true",
                    help="产物已存在则跳过（批次重跑用）")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(args.image))[0]

    if args.skip_existing and os.path.exists(os.path.join(args.out_dir, stem + ".glb")):
        print(f"[skip] {stem}.glb 已存在", file=sys.stderr)
        return 0

    # 1) 白底归一化 + base64
    flat = os.path.join(args.out_dir, stem + "_input.png")
    flat = _flatten_white(args.image, flat)
    with open(flat, "rb") as f:
        raw = f.read()
    b64 = base64.b64encode(raw).decode("ascii")
    print(f"[info] 输入 {flat}（{len(raw)//1024} KB, base64 {len(b64)//1024} KB）",
          file=sys.stderr)

    # 2) 载入官方脚本（进程内调用，argv 无长度限制）
    spec = importlib.util.spec_from_file_location("buddy_cloud", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    argv = ["buddy-cloud.py", "3d"]
    if args.prompt:
        argv.append(args.prompt)
    argv += ["--image-base64", b64, "--model", args.model, "--token-stdin"]
    if args.pbr:
        argv.append("--enable-pbr")
    if args.face_count:
        argv += ["--face-count", str(args.face_count)]
    if args.no_poll:
        argv.append("--no-poll")

    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    code = 0
    try:
        sys.argv = argv
        mod.main()
    except SystemExit as e:
        code = int(e.code or 0)
    finally:
        sys.stdout = old_stdout
    text = buf.getvalue()
    sys.stdout.write(text)
    sys.stdout.flush()

    # 3) 解析输出并下载产物
    if args.no_download or args.no_poll:
        return code
    text_stripped = text.strip()
    start, end = text_stripped.find("{"), text_stripped.rfind("}")
    if start < 0 or end <= start:
        print("[warn] 输出中未找到 JSON，跳过自动下载", file=sys.stderr)
        return code
    try:
        data = json.loads(text_stripped[start:end + 1])
    except Exception:  # noqa: BLE001
        print("[warn] JSON 解析失败，跳过自动下载", file=sys.stderr)
        return code

    if data.get("error"):
        print(f"[error] {data.get('error')}: {data.get('message')}", file=sys.stderr)
        return 1

    files = data.get("result_files") or []
    if not files and data.get("result_url"):
        urls = data["result_url"]
        urls = urls if isinstance(urls, list) else [urls]
        files = [{"type": "bin", "url": u} for u in urls]
    # 官方输出里 3D 结果在 raw_result.ResultFile3Ds（Type/Url/PreviewImageUrl）
    if not files and isinstance(data.get("raw_result"), dict):
        for it in data["raw_result"].get("ResultFile3Ds", []) or []:
            files.append({
                "type": (it.get("Type") or "").lower(),
                "url": it.get("Url"),
                "preview_image_url": it.get("PreviewImageUrl"),
            })

    saved = []
    for item in files:
        t = (item.get("type") or "bin").lower()
        url = item.get("url")
        if not url or t not in ("glb",):          # 只取 GLB（OBJ 是 zip，体积大且用不到）
            continue
        dst = os.path.join(args.out_dir, f"{stem}.{t}")
        if _download(url, dst):
            saved.append(dst)
            print(f"[ok] 已下载 {dst}", file=sys.stderr)
        pv = item.get("preview_image_url")
        if pv:
            dst_pv = os.path.join(args.out_dir, f"{stem}_preview.png")
            if _download(pv, dst_pv):
                saved.append(dst_pv)
                print(f"[ok] 已下载 {dst_pv}", file=sys.stderr)

    if saved:
        print("[done] 本地产物：")
        for p in saved:
            print("  " + p)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
