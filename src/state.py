# -*- coding: utf-8 -*-
"""麦麦精灵 · 状态持久化（本地 JSON，零依赖）

数据结构::

    {
      "version": 2,
      "updated_at": "...",
      "spirit": { ...精灵状态... },
      "pantry": { "items": {"薯条": 3}, "imported": ["orderId", ...] }
    }
"""
from __future__ import annotations

import json
import os
import time
from typing import Optional


def default_state_path() -> str:
    return os.path.join(os.path.expanduser("~"), ".mcpet", "spirit.json")


class StateStore:
    """精灵 + 食物库存的本地存储（单精灵模式，预留多精灵扩展位）"""

    def __init__(self, path: Optional[str] = None):
        self.path = path or default_state_path()

    def exists(self) -> bool:
        return os.path.exists(self.path)

    def load(self) -> Optional[dict]:
        """读取完整状态。返回 {"spirit": dict|None, "pantry": dict}；无文件时返回 None"""
        if not self.exists():
            return None
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
        if not isinstance(data, dict):
            return None
        return {
            "spirit": data.get("spirit"),
            "pantry": data.get("pantry") or {"items": {}, "imported": []},
        }

    def save(self, spirit: dict, pantry: dict | None = None) -> str:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        payload = {
            "version": 2,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "spirit": spirit,
            "pantry": pantry or {"items": {}, "imported": []},
        }
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return self.path
