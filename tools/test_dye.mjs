// 异色染色引擎 · 逻辑测试（Node 环境）
// 运行：node tools/test_dye.mjs
import { createRequire } from "module";
const require = createRequire(import.meta.url);

const Dye = require("../docs/demo/dye.js");
const lineageJson = require("../data/lineage.json");

const meta = {};
for (const [k, v] of Object.entries(lineageJson.lineages)) {
  meta[k] = { dye_color: v.dye_color, dye_name: v.dye_name };
}

let pass = 0, fail = 0;
function check(name, cond, extra = "") {
  if (cond) { pass++; console.log(`  ✅ ${name}${extra ? " — " + extra : ""}`); }
  else { fail++; console.log(`  ❌ ${name}${extra ? " — " + extra : ""}`); }
}
const L = rgb => Math.round(Dye.luminance(rgb));

console.log("== 用例 1：汉堡精灵吃咖啡 → 逐渐变深（灰→黑方向）==");
{
  const base = Dye.computeBlend("牛", { 牛: 3 }, meta);
  const c3 = Dye.computeBlend("牛", { 牛: 3, 咖: 3 }, meta);
  const c6 = Dye.computeBlend("牛", { 牛: 3, 咖: 6 }, meta);
  const c12 = Dye.computeBlend("牛", { 牛: 3, 咖: 12 }, meta);
  console.log(`   本色: ${base.name} ${base.hex} L=${L(base.rgb)} s=${base.s.toFixed(2)}`);
  console.log(`   +3咖: ${c3.name} ${c3.hex} L=${L(c3.rgb)} s=${c3.s.toFixed(2)}`);
  console.log(`   +6咖: ${c6.name} ${c6.hex} L=${L(c6.rgb)} s=${c6.s.toFixed(2)}`);
  console.log(`   +12咖: ${c12.name} ${c12.hex} L=${L(c12.rgb)} s=${c12.s.toFixed(2)}`);
  check("颜色逐级变深", L(base.rgb) > L(c3.rgb) && L(c3.rgb) > L(c6.rgb) && L(c6.rgb) > L(c12.rgb));
  check("染色强度逐级增加", c3.s < c6.s && c6.s < c12.s);
  check("最终接近深色系", ["深咖", "可可黑", "咖啡棕", "陨石灰"].includes(c12.name), c12.name);
}

console.log("\n== 用例 2：咖啡精灵吃浅色系（鸡/薯）→ 变淡、泛黄 ==");
{
  const base = Dye.computeBlend("咖", { 咖: 5 }, meta);
  const light = Dye.computeBlend("咖", { 咖: 5, 鸡: 4 }, meta);
  const warm = Dye.computeBlend("咖", { 咖: 5, 鸡: 4, 薯: 8 }, meta);
  console.log(`   本色: ${base.name} ${base.hex} L=${L(base.rgb)}`);
  console.log(`   +4鸡: ${light.name} ${light.hex} L=${L(light.rgb)}`);
  console.log(`   +8薯: ${warm.name} ${warm.hex} L=${L(warm.rgb)}`);
  check("颜色变淡（亮度上升）", L(light.rgb) > L(base.rgb) && L(warm.rgb) > L(base.rgb));
  check("朝暖黄方向偏移（R-B 差增大）", (warm.rgb[0] - warm.rgb[2]) > (base.rgb[0] - base.rgb[2]));
}

console.log("\n== 用例 3：本命系投喂会把颜色洗回来 ==");
{
  const stained = Dye.computeBlend("牛", { 牛: 3, 咖: 6 }, meta);
  const washed = Dye.computeBlend("牛", { 牛: 10, 咖: 6 }, meta);
  console.log(`   染黑后: ${stained.name} s=${stained.s.toFixed(2)}`);
  console.log(`   连喂本命: ${washed.name} s=${washed.s.toFixed(2)}`);
  check("染色强度回落", washed.s < stained.s);
  check("颜色向本色回归", L(washed.rgb) > L(stained.rgb));
}

console.log("\n== 用例 4：陌生拜访（无本命，仅显示混色）==");
{
  const mix = Dye.computeBlend(null, { 甜: 2, 鱼: 1 }, meta);
  console.log(`   甜×2+鱼×1: ${mix.name} ${mix.hex}（base=${mix.base}）`);
  check("无本命时取最多的系为锚", mix.base === "甜");
}

console.log("\n== 用例 5：颜色命名表覆盖检查 ==");
{
  check("雪碧色在色表中（用户举例）", Dye.PALETTE.some(p => p[0] === "雪碧色"));
  check("怡泉黄在色表中（用户举例）", Dye.PALETTE.some(p => p[0] === "怡泉黄"));
  check("深咖/可可黑在色表中", Dye.PALETTE.some(p => p[0] === "可可黑"));
}

console.log(`\n结果：通过 ${pass} 项，失败 ${fail} 项`);
if (fail > 0) process.exit(1);
