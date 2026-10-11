# -*- coding: utf-8 -*-
"""麦麦精灵 · 本地网页版（stdlib-only）

数据流：同步订单 → 食物入库 → 从库存喂养

用法::

    python app.py                 # 启动后自动打开浏览器
    python app.py --port 8765     # 指定端口
    python app.py --no-open       # 不自动打开浏览器

浏览器 → 本机服务（此文件）→ 麦当劳 MCP（服务端转发，规避 CORS）
状态文件与 CLI 共用（默认 ~/.mcpet/spirit.json），两边数据互通。
"""
from __future__ import annotations

import argparse
import http.server
import json
import os
import socketserver
import sys
import urllib.parse
import webbrowser

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "src"))

from feeding import Spirit, classify_meal            # noqa: E402
from spirit_gen import render_spirit, LINEAGES       # noqa: E402
from pantry import Pantry                            # noqa: E402
from state import StateStore                         # noqa: E402
import order_parser                                   # noqa: E402

WEB_DIR = os.path.join(_HERE, "web")
ASSETS_DIR = os.path.join(_HERE, "assets")

STAGE_LABEL = {1: "幼体", 2: "成形", 3: "完全体", 4: "变异体"}

with open(os.path.join(_HERE, "data", "forms.json"), encoding="utf-8") as _f:
    FORMS = json.load(_f)

_GLOBAL = {"state_path": None, "token": None}


def _store() -> StateStore:
    return StateStore(_GLOBAL["state_path"])


# ---------------------------------------------------------------- 形态 / 图标

def _form_slug(sp: Spirit | None) -> str | None:
    """当前应显示的形态 slug。

    - 未分化（幼体）：按"倾向系别"显示基础形态（小号）——喂什么，先露什么苗头
    - 已分化：按阶段取 tier 2/3/4
    - 完全没喂过：None（前端回落 SVG 蛋）
    """
    if sp is None:
        return None
    lin = sp.lineage or sp.top_lineage()
    if not lin:
        return None
    tier = "2" if not sp.lineage else str(sp.stage)
    entry = FORMS["lineages"].get(lin, {}).get(tier)
    return entry["slug"] if entry else None


def _form_meta(sp: Spirit | None) -> dict:
    """形态的附加信息（名称 / 说明）"""
    if sp is None:
        return {}
    lin = sp.lineage or sp.top_lineage()
    if not lin:
        return {}
    tier = "2" if not sp.lineage else str(sp.stage)
    return FORMS["lineages"].get(lin, {}).get(tier, {})


def _food_icon(name: str) -> str | None:
    """食物名 -> 图标 slug（按关键词顺序匹配）"""
    if not name:
        return None
    for kw, slug in FORMS.get("food_icons", []):
        if kw in name:
            return slug
    return None


def _load_all() -> tuple[Spirit | None, Pantry]:
    d = _store().load()
    if not d:
        return None, Pantry()
    sp = Spirit.from_dict(d["spirit"]) if d.get("spirit") else None
    return sp, Pantry.from_dict(d.get("pantry"))


def _save_all(sp: Spirit, pantry: Pantry) -> None:
    _store().save(sp.to_dict(), pantry.to_dict())


def _pantry_payload(pantry: Pantry) -> dict:
    return {
        "total": pantry.total,
        "items": [{"name": k, "qty": v, "lineage": classify_meal(k),
                   "icon": (f"/assets/spirits/{s}.png" if (s := _food_icon(k)) else None)}
                  for k, v in pantry.sorted_items()],
    }


def _spirit_payload(sp: Spirit | None, pantry: Pantry) -> dict:
    base = {"pantry": _pantry_payload(pantry)}
    if sp is None:
        return {"hatched": False, **base}
    p = sp.progress()
    slug = _form_slug(sp)
    meta = _form_meta(sp)
    return {
        "hatched": True,
        "name": sp.name,
        "stage": sp.stage,
        "stage_label": STAGE_LABEL.get(sp.stage, str(sp.stage)),
        "lineage": sp.lineage,
        "lineage_name": LINEAGES[sp.lineage]["name"] if sp.lineage else None,
        "title": LINEAGES[sp.lineage]["title"] if sp.lineage else None,
        "mood": sp.mood,
        "exp": p["exp"], "next": p["next"], "pct": p["pct"],
        "feed_count": sp.feed_count,
        "hetero": sp.hetero,
        "top_lineage": sp.top_lineage(),
        "lineage_exp": sp.lineage_exp,
        "fed_meals": sp.fed_meals[:8],
        "svg": render_spirit(sp.lineage, sp.stage, sp.mood, size=260),
        "form_img": f"/assets/spirits/{slug}.png" if slug else None,
        "form_name": meta.get("name"),
        "form_desc": meta.get("desc"),
        **base,
    }


def _mcp_orders() -> list[dict]:
    from mcp_client import McdClient, McdError
    client = McdClient(token=_GLOBAL["token"])
    raw = client.order_list()
    text = client.extract_text(raw) or ""
    data = order_parser.extract_json(text)
    if not data:
        raise McdError("未能解析订单返回")
    return order_parser.parse_order_list(data)


def _sim_orders() -> list[dict]:
    with open(os.path.join(_HERE, "data", "sim_orders.json"), encoding="utf-8") as f:
        raw = json.load(f)
    return order_parser.parse_order_list(raw)


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    # -------------------------------------------------- 静态资源

    def translate_path(self, path):
        """/assets/* 从项目根 assets/ 目录提供（防目录穿越）"""
        p = urllib.parse.urlparse(path).path
        if p.startswith("/assets/"):
            rel = p[len("/assets/"):]
            fp = os.path.normpath(os.path.join(ASSETS_DIR, *rel.split("/")))
            root = os.path.normpath(ASSETS_DIR) + os.sep
            if not fp.startswith(root):
                return os.path.join(ASSETS_DIR, "_denied_")
            return fp
        return super().translate_path(path)

    # -------------------------------------------------- 工具

    def _send_json(self, obj, code: int = 200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def log_message(self, fmt, *args):
        if "/api/" in (self.path or ""):
            sys.stderr.write("[api] %s\n" % (fmt % args))

    # -------------------------------------------------- GET

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/state":
            sp, pantry = _load_all()
            return self._send_json(_spirit_payload(sp, pantry))
        if path == "/api/lineages":
            data = {}
            for k, v in LINEAGES.items():
                tiers, seen = [], set()
                for t in ("2", "3", "4"):
                    e = FORMS["lineages"].get(k, {}).get(t)
                    if not e or e["slug"] in seen:
                        continue
                    seen.add(e["slug"])
                    tiers.append({"tier": t, "slug": e["slug"], "name": e.get("name", ""),
                                  "desc": e.get("desc", ""),
                                  "img": f"/assets/spirits/{e['slug']}.png"})
                data[k] = {"name": v["name"], "title": v["title"], "rarity": v["rarity"],
                           "svg": render_spirit(k, 2, size=96), "forms": tiers}
            return self._send_json(data)
        if path == "/":
            self.path = "/index.html"
        return super().do_GET()

    # -------------------------------------------------- POST

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        body = self._read_body()
        sp, pantry = _load_all()

        if path == "/api/hatch":
            if sp is not None:
                return self._send_json(
                    {"ok": False, "error": f"已有精灵「{sp.name}」，需重置请点「重新开始」"})
            sp = Spirit(name=(body.get("name") or "麦麦").strip()[:12] or "麦麦")
            _save_all(sp, pantry)
            return self._send_json({"ok": True, "state": _spirit_payload(sp, pantry)})

        if path == "/api/feed":
            if sp is None:
                return self._send_json({"ok": False, "error": "还没有精灵，先孵化"}, 400)
            meal = (body.get("meal") or "").strip()
            if not meal:
                return self._send_json({"ok": False, "error": "食物名不能为空"}, 400)
            taken = pantry.take(meal)                # 支持模糊名（"薯条"→"中薯条"）
            if taken is None:
                return self._send_json(
                    {"ok": False, "error": f"库存里没有「{meal}」了，先同步订单补充食物"}, 400)
            ev = sp.feed(taken, source="real")
            _save_all(sp, pantry)
            return self._send_json({"ok": True, "event": {
                "meal": taken, "exp_gained": ev["exp_gained"],
                "message": ev["message"], "evolved": ev["evolved"],
                "variant": ev["variant_triggered"],
            }, "state": _spirit_payload(sp, pantry)})

        if path == "/api/sync":
            if sp is None:
                return self._send_json({"ok": False, "error": "还没有精灵，先孵化"}, 400)
            try:
                orders = _mcp_orders()
            except Exception as e:                       # noqa: BLE001
                return self._send_json({"ok": False, "error": f"订单获取失败：{e}"}, 502)
            if not orders:
                return self._send_json({"ok": True, "new_orders": 0, "added": {},
                                        "skipped": 0, "message": "没有找到已完成的订单",
                                        "state": _spirit_payload(sp, pantry)})
            result = pantry.import_orders(orders)
            _save_all(sp, pantry)
            return self._send_json({"ok": True, **result,
                                    "state": _spirit_payload(sp, pantry)})

        if path == "/api/simulate":
            if sp is None:
                return self._send_json({"ok": False, "error": "还没有精灵，先孵化"}, 400)
            orders = _sim_orders()
            result = pantry.import_orders(orders)
            _save_all(sp, pantry)
            return self._send_json({"ok": True, **result,
                                    "state": _spirit_payload(sp, pantry)})

        if path == "/api/reset":
            if sp is None:
                return self._send_json({"ok": False, "error": "没有精灵"}, 400)
            name = (body.get("name") or sp.name).strip()[:12]
            new_sp = Spirit(name=name)
            _save_all(new_sp, pantry)                    # 食物库存保留
            return self._send_json({"ok": True, "state": _spirit_payload(new_sp, pantry)})

        return self._send_json({"ok": False, "error": "未知接口"}, 404)


def main() -> int:
    ap = argparse.ArgumentParser(description="麦麦精灵 · 网页版")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--state", default=None, help="状态文件路径（与 CLI 共用）")
    ap.add_argument("--token", default=None, help="MCP Token（默认读环境变量/文件）")
    ap.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    args = ap.parse_args()

    _GLOBAL["state_path"] = args.state
    _GLOBAL["token"] = args.token

    with socketserver.ThreadingTCPServer(("127.0.0.1", args.port), Handler) as httpd:
        httpd.daemon_threads = True
        url = f"http://127.0.0.1:{args.port}/"
        print(f"🍔 麦麦精灵网页版已启动：{url}")
        print("   数据流：同步订单 → 食物入库 → 从库存喂养。Ctrl+C 退出。")
        if not args.no_open:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n再见～")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
