// 账号数据导入解析器 · 逻辑测试（Node 环境）
// 运行：node tools/test_import.mjs
import { createRequire } from "module";
const require = createRequire(import.meta.url);

const Imp = require("../docs/demo/import.js");
const simOrders = require("../data/sim_orders.json");

let pass = 0, fail = 0;
function check(name, cond, extra = "") {
  if (cond) { pass++; console.log(`  ✅ ${name}${extra ? " — " + extra : ""}`); }
  else { fail++; console.log(`  ❌ ${name}${extra ? " — " + extra : ""}`); }
}

/* ---------- 1. 导出格式（mcpet-export v1） ---------- */
console.log("== 1. 导出格式 ==");
{
  const text = JSON.stringify({
    type: "mcpet-export", version: 1,
    orders: [
      { orderId: "T1", store: "麦当劳中山兴中广场餐厅", time: "2026-10-05 12:30",
        items: [{ name: "中薯条", qty: 2 }, { name: "高达吉士双牛堡", qty: 1 }] },
      { orderId: "T2", store: "麦当劳中山富华道餐厅", time: "2026-10-06 18:10",
        items: [{ name: "麦乐鸡", qty: 1 }] },
    ],
  });
  const r = Imp.normalize(text);
  check("解析出 2 单", r.orders.length === 2);
  check("门店正确", r.orders[0].store === "麦当劳中山兴中广场餐厅");
  check("时间正确", r.orders[1].time === "2026-10-06 18:10");
  check("物品与数量正确", r.orders[0].items[0].name === "中薯条" && r.orders[0].items[0].qty === 2);
}

/* ---------- 2. MCP 原始格式（模拟订单样本 = 真实接口同构） ---------- */
console.log("== 2. MCP 原始格式 ==");
{
  const r = Imp.normalize(simOrders);
  const total = simOrders.data.list.length;
  check(`解析出全部订单（${total} 单）`, r.orders.length === total - r.skipped, `skipped=${r.skipped}`);
  const combo = simOrders.data.list.find(o => o.orderProductList.some(p => p.comboItemList && p.comboItemList.length));
  const target = r.orders.find(o => o.orderId === combo.orderId);
  const expectFirst = combo.orderProductList[0].comboItemList[0].name;
  check("套餐被拆成子项", target && target.items.some(it => it.name === expectFirst), expectFirst);
  check("子项数量保留", target.items.every(it => it.qty >= 1));
  check("门店字段映射", r.orders.every(o => !combo.storeName || typeof o.store === "string"));
}

/* ---------- 3. 状态过滤：未完成订单被剔除 ---------- */
console.log("== 3. 状态过滤 ==");
{
  const raw = JSON.parse(JSON.stringify(simOrders));
  raw.data.list.push({
    orderId: "X-CANCELLED", createTime: "2026-10-07 10:00", storeName: "测试店",
    orderStatus: "订单已取消",
    orderProductList: [{ productName: "巨无霸", quantity: 1, comboItemList: [] }],
  });
  const r = Imp.normalize(raw);
  check("已取消订单被跳过", !r.orders.some(o => o.orderId === "X-CANCELLED"));
  check("skipped 计数 >= 1", r.skipped >= 1, `skipped=${r.skipped}`);
}

/* ---------- 4. 裸数组格式 ---------- */
console.log("== 4. 裸数组格式 ==");
{
  const r = Imp.normalize('[{"orderId":"A1","store":"店A","items":[{"name":"薯条","qty":1}]}]');
  check("数组输入可解析", r.orders.length === 1 && r.orders[0].orderId === "A1");
}

/* ---------- 5. 代码块包裹 / 容错 ---------- */
console.log("== 5. 容错 ==");
{
  const fenced = '```json\n{"orders":[{"orderId":"B1","store":"店B","items":[{"name":"可乐","qty":1}]}]}\n```';
  const r = Imp.normalize(fenced);
  check("```json 包裹可解析", r.orders.length === 1 && r.orders[0].orderId === "B1");

  let threw = false;
  try { Imp.normalize("这不是 JSON"); } catch (e) { threw = true; }
  check("非法内容抛错", threw);

  let threw2 = false;
  try { Imp.normalize('{"foo":123}'); } catch (e) { threw2 = true; }
  check("无法识别结构抛错", threw2);

  const r3 = Imp.normalize('{"orders":[{"orderId":"C1","store":"","items":[]}]}');
  check("空订单（无物品）被跳过", r3.orders.length === 0 && r3.skipped === 1);
}

console.log(`\n结果：${pass} 通过 / ${fail} 失败`);
process.exit(fail ? 1 : 0);
