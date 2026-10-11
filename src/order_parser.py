# -*- coding: utf-8 -*-
"""订单解析器：把 order-list 的原始返回解析成可喂养的订单结构（零依赖）

真实数据样例（实测）：
{
  "orderProductList": [{
      "productCode": "9900016048",
      "productName": "随心配1+1套餐",
      "quantity": 1,
      "comboItemList": [                      ← 套餐子项是现成的！
          {"productCode": "521316", "name": "高达吉士双牛堡", "quantity": 1},
          {"productCode": "515520", "name": "中杯怡泉+C", "quantity": 1}
      ]
  }]
}
"""
from __future__ import annotations

import json
from typing import Optional

FINISHED_STATUS = ("订单已完成", "已完成", "已完成订单")


def extract_json(text: str) -> Optional[dict]:
    """从工具返回文本中提取第一个完整的 JSON 对象（平衡括号扫描）"""
    if not text:
        return None
    # 优先找 success 结构
    start = text.find('{"success"')
    if start == -1:
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


def parse_order_list(raw: dict) -> list[dict]:
    """order-list 原始 JSON -> 订单列表

    返回::
        [{
          "orderId": str,
          "createTime": str,
          "storeName": str,
          "items": [
             {"name": "随心配1+1套餐", "quantity": 1,
              "parts": [{"name": "高达吉士双牛堡", "quantity": 1}, ...]}
          ]
        }]
    """
    out = []
    for o in ((raw.get("data") or {}).get("list") or []):
        if o.get("orderStatus") not in FINISHED_STATUS:
            continue
        items = []
        for p in (o.get("orderProductList") or []):
            parts = []
            for c in (p.get("comboItemList") or []):
                name = c.get("name") or c.get("productName") or ""
                if name:
                    parts.append({"name": name, "quantity": int(c.get("quantity") or 1)})
            items.append({
                "name": p.get("productName") or "",
                "quantity": int(p.get("quantity") or 1),
                "parts": parts,
            })
        if items:
            out.append({
                "orderId": o.get("orderId", ""),
                "createTime": o.get("createTime", ""),
                "storeName": o.get("storeName", ""),
                "items": items,
            })
    return out
