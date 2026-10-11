/* 麦麦精灵 · 账号数据导入解析器（McPet Import Parser）
 * 把「导出的订单数据」统一成试玩页可消费的结构：
 *   { orders: [{orderId, store, time, items:[{name, qty}]}], skipped }
 *
 * 支持三种输入格式：
 *   1. 麦麦精灵导出文件（完整版 `python mcpet.py export` / 独立脚本生成）：
 *      { type:"mcpet-export", orders:[{orderId, store, time, items:[{name,qty}]}] }
 *   2. MCP order-list 原始响应（可直接粘贴）：
 *      { data:{ list:[ {orderId, storeName, createTime, orderStatus, orderProductList:[{productName, quantity, comboItemList:[...]}]} ] } }
 *   3. 订单数组：[ {...同上任一结构} ]
 *
 * 本文件同时可在浏览器（window.McPetImport）与 Node（module.exports）使用，便于逻辑测试。
 */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.McPetImport = api;
})(typeof window !== "undefined" ? window : globalThis, function () {

  const FINISHED = ["订单已完成", "已完成", "已完成订单"];

  /* 订单状态判定：导入格式没有该字段时视为已完成（用户主动导出即视为有效） */
  function isFinished(status) {
    if (status === undefined || status === null || status === "") return true;
    return FINISHED.indexOf(String(status)) !== -1;
  }

  /* 单条订单 -> 统一结构；无法识别返回 null */
  function normalizeOne(o) {
    if (!o || typeof o !== "object") return null;
    const orderId = String(o.orderId || o.id || o.order_id || "");
    const store = String(o.storeName || o.store || "");
    const time = String(o.createTime || o.time || "");
    let items = [];

    if (Array.isArray(o.items)) {
      // 导出格式（已是扁平 items）
      items = o.items.map(function (it) {
        return {
          name: String(it.name || it.productName || ""),
          qty: Number(it.qty || it.quantity || 1) || 1,
        };
      });
    } else if (Array.isArray(o.orderProductList)) {
      // MCP 原始格式：套餐拆子项（comboItemList），单点取本身
      for (const p of o.orderProductList) {
        const parts = p.comboItemList || [];
        if (parts.length) {
          for (const c of parts) {
            items.push({
              name: String(c.name || c.productName || ""),
              qty: Number(c.quantity || 1) || 1,
            });
          }
        } else {
          items.push({
            name: String(p.productName || p.name || ""),
            qty: Number(p.quantity || 1) || 1,
          });
        }
      }
    }
    items = items.filter(function (it) { return it.name; });
    if (!items.length) return null;
    return { orderId: orderId, store: store, time: time, items: items };
  }

  /* 主入口：文本或对象 -> {orders, skipped}；无法识别时抛错 */
  function normalize(input) {
    let d = input;
    if (typeof input === "string") {
      let t = input.trim();
      if (!t) throw new Error("内容为空");
      // 容忍 ```json 代码块包裹（从聊天/文档复制时常见）
      t = t.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
      try {
        d = JSON.parse(t);
      } catch (e) {
        throw new Error("不是合法的 JSON 内容");
      }
    }
    let list = null;
    if (Array.isArray(d)) list = d;
    else if (d && Array.isArray(d.orders)) list = d.orders;
    else if (d && d.data && Array.isArray(d.data.list)) list = d.data.list;
    else if (d && d.data && Array.isArray(d.data)) list = d.data;
    if (!list) throw new Error("无法识别的数据格式（支持：麦麦精灵导出文件 / order-list 原始 JSON）");

    const orders = [];
    let skipped = 0;
    for (const o of list) {
      if (!isFinished(o && o.orderStatus)) { skipped++; continue; }
      const n = normalizeOne(o);
      if (n) orders.push(n); else skipped++;
    }
    return { orders: orders, skipped: skipped };
  }

  return { normalize: normalize, isFinished: isFinished };
});
