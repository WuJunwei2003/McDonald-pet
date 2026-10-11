# MCP Integration · 麦当劳 MCP 使用说明

本文档说明「麦麦精灵 McPet」实际使用的麦当劳 MCP Server、Tool、调用流程与业务价值，供参赛资格核验。

## 1. 接入的 MCP Server

| 项 | 值 |
|----|-----|
| Server | 麦当劳中国官方 MCP（`https://mcp.mcd.cn`） |
| 传输协议 | Streamable HTTP + JSON-RPC 2.0 |
| 认证方式 | HTTP Header：`Authorization: Bearer <MCP Token>` |
| Token 获取 | 麦当劳 MCP 开放平台（open.mcd.cn/mcp）申请 |
| 客户端实现 | `src/mcp_client.py`（纯 Python 标准库，无第三方依赖；兼容 JSON 与 SSE 两种响应格式） |

> 配置示例见 [`mcp-config.example.json`](./mcp-config.example.json)（脱敏版，仅含环境变量占位符）。

## 2. 使用的 MCP Tool 与调用位置

### 2.1 已集成（运行时代码直接调用）

| Tool | 用途 | 业务映射 | 调用位置 |
|------|------|---------|---------|
| `order-list` | 拉取用户历史订单（含套餐子项 `comboItemList`） | **核心**：真实订单 → 自动拆解为食物 → 精灵的食物库存 | `src/mcp_client.py#order_list`、`mcpet.py#cmd_sync`、`app.py#/api/sync` |
| `query-meals` | 门店菜单（餐品名、价格、官方图片） | 每日免费投喂取材；餐品图片与元数据 | `src/mcp_client.py#query_meals` |
| `query-my-account` | 会员积分账户 | 账户状态展示；积分玩法（规划中） | `src/mcp_client.py#query_my_account` |
| `available-coupons` | 可用优惠券列表 | 优惠券玩法（规划中）；孵化资格参考 | `src/mcp_client.py#available_coupons` |

### 2.2 开发期验证（探索/规划）

| Tool | 用途 | 状态 |
|------|------|------|
| `campaign-calendar` | 官方活动日历 → 活动限定投喂 | 已验证可用，玩法规划中 |
| `list-nutrition-foods` | 餐品营养数据 → 精灵体质面板 | 已验证可用，玩法规划中 |

## 3. 核心调用流程

```
┌──────────────┐   自然语言/点击     ┌───────────────────────────┐
│  用户         │ ─────────────────→ │  麦麦精灵                   │
│ （网页 / CLI /│                    │  网页服务 or CLI or Skill   │
│  WorkBuddy）  │ ←───────────────── │                            │
└──────────────┘   转述/界面呈现      └──────────────┬────────────┘
                                                    │ JSON-RPC over
                                                    │ Streamable HTTP
                                                    ▼
                                        ┌───────────────────────┐
                                        │ mcp.mcd.cn（麦当劳MCP） │
                                        │  Bearer <token> 认证    │
                                        └───────────┬───────────┘
                                                    │
              ┌─────────────────────────────────────┤
              ▼                                     ▼
     order-list（历史订单）                 query-meals（门店菜单）
              │                                     │
              ▼                                     ▼
   套餐自动拆解（comboItemList）            餐品名/图片/价格
              │                                     │
              └──────────────┬──────────────────────┘
                             ▼
                  食物库存（按订单号去重）
                             │
                             ▼
                  喂养引擎（倍率/晋升/变异）
                             │
                             ▼
              精灵形态（六系 × 蛋→幼体→成形→完全体→变异体）
```

**同步订单链路（核心玩法）**：
1. 用户触发同步（网页按钮 / `python mcpet.py sync` / Skill 对话）
2. 调用 `order-list` 拉取历史订单
3. `src/order_parser.py` 逐单解析：订单 → 餐品条目 → **套餐自动拆解**（如"随心配（双层吉士汉堡＋汽水）"拆为「双层吉士汉堡」+「汽水」，饮品等无系别项标为"无感"）
4. 拆解结果按订单号**去重**后入食物库存（同一订单重复同步不会重复获得食物）
5. 用户从库存中点选喂养 → 喂养引擎按系别倍率计算成长 → 精灵进化

## 4. 业务价值

1. **真实消费行为成为游戏输入**：精灵的成长完全由用户真实的麦当劳消费数据驱动——吃什么、吃多少次，直接决定精灵的系别和形态。"你的点单习惯，就是它的基因。"
2. **个人数据 API 的玩法化**：麦当劳 MCP 提供的是"个人订单/积分/券"这类账户级数据接口。本项目把这类数据从"查询工具"变成"养成系统的输入源"，示范了个人数据接口在游戏化场景的用法。
3. **数据真实性带动分享欲**："我的精灵长成变异体了"背后是一份真实的消费记录，天然具备社交传播属性。
4. **零门槛**：无 Token 用户可用内置模拟订单完整体验全部玩法；有 Token 用户获得"真实订单驱动"的完整体验。

## 5. 技术要点

- **stdlib-only 客户端**：不依赖任何 MCP SDK，用 `urllib` 直接走 JSON-RPC，保证评委/用户 clone 后零安装即可运行
- **SSE 兼容解析**：`mcp.mcd.cn` 在 `Accept: application/json, text/event-stream` 下可能返回 SSE（`data:` 行）格式，客户端做了双格式兼容
- **Token 安全**：Token 读取优先级为「构造参数 > 环境变量 `MCD_MCP_TOKEN` > 本地 `.mcpet.token` 文件」；`.mcpet.token` 已加入 `.gitignore`，仓库中**不含任何真实凭证**（见 `mcp-config.example.json` 的占位符写法）
- **CORS 规避**：实测麦当劳 MCP 服务端未开放 CORS，浏览器无法直连；网页版通过本机微型服务（`app.py`，零依赖）转发，用户体验为"打开网页即用"
