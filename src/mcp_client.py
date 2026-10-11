# -*- coding: utf-8 -*-
"""麦当劳 MCP 最小客户端（stdlib-only，无第三方依赖）

- 传输：Streamable HTTP + JSON-RPC 2.0
- 认证：Authorization: Bearer <token>
- Token 读取优先级：构造参数 > 环境变量 MCD_MCP_TOKEN > 同级 .mcpet.token 文件

用法::

    from mcp_client import McdClient
    client = McdClient()
    raw = client.call_tool("order-list", {})
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Optional

DEFAULT_URL = "https://mcp.mcd.cn"


class McdError(Exception):
    """MCP 调用失败"""


class McdClient:
    def __init__(self, token: Optional[str] = None, url: str = DEFAULT_URL,
                 timeout: int = 30):
        self.token = (token
                      or os.environ.get("MCD_MCP_TOKEN")
                      or self._read_token_file() or "")
        if not self.token:
            raise McdError("缺少 MCP Token：请传入 token、设置环境变量 MCD_MCP_TOKEN "
                           "或创建 .mcpet.token 文件（内容为纯 token）")
        self.url = url
        self.timeout = timeout
        self._seq = 0

    @staticmethod
    def _read_token_file() -> Optional[str]:
        here = os.path.dirname(os.path.abspath(__file__))
        for candidate in (
            os.path.join(os.getcwd(), ".mcpet.token"),
            os.path.normpath(os.path.join(here, "..", ".mcpet.token")),
        ):
            if os.path.exists(candidate):
                with open(candidate, encoding="utf-8") as f:
                    return f.read().strip()
        return None

    # ------------------------------------------------------------ 传输

    def _post(self, payload: dict) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {self.token}",
        }
        req = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            raise McdError(f"HTTP {e.code}: {detail[:300]}") from e
        except OSError as e:
            raise McdError(f"网络错误: {e}") from e
        return self._parse(body)

    @staticmethod
    def _parse(body: str) -> dict:
        """兼容 JSON 与 SSE（data: 行）两种响应格式"""
        text = body.strip()
        if not text:
            raise McdError("空响应")
        if text.startswith("{"):
            return json.loads(text)
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
        raise McdError(f"无法解析响应: {text[:200]}")

    # ------------------------------------------------------------ 协议

    def call_tool(self, name: str, arguments: Optional[dict] = None) -> dict:
        """调用任意 MCP 工具，返回 result 原始结构"""
        self._seq += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._seq,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        }
        result = self._post(payload)
        if "error" in result:
            raise McdError(f"工具调用失败: {result['error']}")
        return result.get("result", {})

    @staticmethod
    def extract_text(result: dict) -> str:
        """从 tools/call 结果里抽取文本内容（content[].text 拼接）"""
        parts = []
        for item in (result or {}).get("content", []) or []:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        return "\n".join(parts)

    # ------------------------------------------------------------ 便捷方法

    def order_list(self) -> dict:
        """查询历史订单"""
        return self.call_tool("order-list", {})

    def query_my_account(self) -> dict:
        """积分账户"""
        return self.call_tool("query-my-account", {})

    def query_meals(self, store_code: str, order_type: int = 1, be_type: int = 1,
                    be_code: Optional[str] = None) -> dict:
        """门店菜单（用于拿真实餐品名与图片）"""
        args = {"storeCode": store_code, "orderType": order_type, "beType": be_type}
        if be_code:
            args["beCode"] = be_code
        return self.call_tool("query-meals", args)

    def available_coupons(self) -> dict:
        return self.call_tool("available-coupons", {})
