# -*- coding: utf-8 -*-
"""麦麦精灵 · 独立导出脚本（单文件 / 零依赖）

把麦当劳 MCP 的历史订单导出为 mcpet-orders.json，用于在线试玩页「📥 导入账号数据」，
用你自己的真实订单喂养精灵。

用法：
    1) 需要 Python 3.8+（命令行执行：python export_orders.py）
    2) 运行后按提示粘贴 Token；或直接：python export_orders.py --token 你的Token
    3) 得到 mcpet-orders.json → 打开在线试玩页 → 「📥 导入账号数据」→ 上传该文件

Token 从哪来：麦当劳 MCP 开发者平台（比赛报名后会发放）。
本脚本只做一件事：调用官方 order-list 接口把订单下载到本地文件，不会上传到任何其他地方。
"""
from __future__ import annotations

import argparse
import datetime
import getpass
import json
import urllib.error
import urllib.request

DEFAULT_URL = "https://mcp.mcd.cn"
FINISHED = ("订单已完成", "已完成", "已完成订单")


def call_order_list(token: str) -> str:
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "order-list", "arguments": {}},
    }
    req = urllib.request.Request(
        DEFAULT_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": "Bearer " + token,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        raise SystemExit("❌ 请求失败 HTTP %s：%s\n（请检查 Token 是否正确）" % (e.code, detail[:200]))
    except OSError as e:
        raise SystemExit("❌ 网络错误：%s" % e)


def parse_body(body: str) -> dict:
    text = body.strip()
    if text.startswith("{"):
        return json.loads(text)
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            return json.loads(line[5:].strip())
    raise SystemExit("❌ 无法解析响应：%s" % text[:200])


def extract_json_object(text: str):
    """从工具返回文本中提取第一个完整 JSON 对象（平衡括号扫描）"""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def flatten_orders(raw: dict) -> list:
    """order-list 原始 JSON -> [{orderId, store, time, items:[{name,qty}]}]（套餐自动拆分）"""
    out = []
    for o in ((raw.get("data") or {}).get("list") or []):
        if o.get("orderStatus") not in FINISHED:
            continue
        items = []
        for p in (o.get("orderProductList") or []):
            parts = p.get("comboItemList") or []
            if parts:
                for c in parts:
                    name = c.get("name") or c.get("productName") or ""
                    if name:
                        items.append({"name": name, "qty": int(c.get("quantity") or 1)})
            else:
                name = p.get("productName") or ""
                if name:
                    items.append({"name": name, "qty": int(p.get("quantity") or 1)})
        if items:
            out.append({
                "orderId": o.get("orderId", ""),
                "store": o.get("storeName", ""),
                "time": o.get("createTime", ""),
                "items": items,
            })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="导出麦当劳 MCP 订单为 mcpet-orders.json（供在线试玩页导入）")
    ap.add_argument("--token", default="", help="MCP Token（缺省则交互输入）")
    ap.add_argument("--out", default="mcpet-orders.json", help="输出文件名")
    args = ap.parse_args()

    token = args.token.strip()
    if not token:
        try:
            token = getpass.getpass("请粘贴你的麦当劳 MCP Token（输入时不显示，回车确认）：").strip()
        except Exception:
            token = input("请粘贴你的麦当劳 MCP Token：").strip()
    if not token:
        print("❌ 缺少 Token。用法：python export_orders.py --token 你的Token")
        return 1

    print("🔄 正在拉取订单…")
    body = call_order_list(token)
    result = parse_body(body)
    if "error" in result:
        print("❌ 工具调用失败：%s" % result["error"])
        return 1
    content = (result.get("result") or {}).get("content") or []
    text = "\n".join(it.get("text", "") for it in content if isinstance(it, dict))
    data = extract_json_object(text)
    if not data:
        print("❌ 未能解析订单 JSON（接口格式可能变化）")
        return 1
    orders = flatten_orders(data)
    if not orders:
        print("📭 没有找到已完成订单。先去吃一顿麦当劳吧～")
        return 1

    payload = {
        "type": "mcpet-export",
        "version": 1,
        "exportedAt": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "orders": orders,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    stores = sorted({o["store"] for o in orders if o["store"]})
    print("✅ 已导出 %d 单（%d 家门店）→ %s" % (len(orders), len(stores), args.out))
    for s in stores[:5]:
        print("   ·", s)
    print("   下一步：打开在线试玩页 →「📥 导入账号数据」→ 上传这个文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
