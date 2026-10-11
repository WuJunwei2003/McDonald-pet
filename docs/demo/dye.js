/* 麦麦精灵 · 异色染色引擎（McPet Dye Engine）
 * 规则：喂异系食物会让精灵体色逐渐向该系的「食物色」混合；
 *       喂本命系会把颜色洗回来（本命 = 锚点）。
 * 渲染：对精灵图做「保亮度染色」（保留明暗结构），纯白描边不染。
 * 本文件同时可在浏览器（window.McPetDye）与 Node（module.exports）使用，便于逻辑测试。
 */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.McPetDye = api;
})(typeof window !== "undefined" ? window : globalThis, function () {

  /* 颜色命名表（混色结果取最近邻命名；颜色名会直接显示给玩家） */
  const PALETTE = [
    ["奶白", 250, 246, 238],
    ["雪碧色", 214, 236, 206],
    ["鱼肚蓝", 159, 196, 232],
    ["奶油粉", 242, 168, 192],
    ["草莓红", 214, 90, 86],
    ["怡泉黄", 232, 179, 58],
    ["黄金薯", 245, 167, 66],
    ["脆皮金", 232, 201, 138],
    ["焦糖", 176, 112, 54],
    ["咖啡棕", 107, 74, 50],
    ["深咖", 55, 43, 34],
    ["可可黑", 46, 36, 30],
    ["牛肉红", 181, 80, 47],
    ["灰褐", 140, 126, 114],
    ["陨石灰", 96, 92, 88],
  ];

  function hexToRgb(hex) {
    const h = String(hex || "").replace("#", "");
    if (h.length !== 6) return [191, 184, 172];
    return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
  }
  function rgbToHex(rgb) {
    return "#" + rgb.map(v => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, "0")).join("");
  }
  function luminance(rgb) { return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]; }
  function desaturate(rgb, amt) {
    const g = luminance(rgb);
    return rgb.map(v => v + (g - v) * amt);
  }

  /** 计算混色与染色强度
   * @param baseLin  本命系（null 时取喂养次数最多的系）
   * @param counts   {系别: 累计喂养次数}（含本命系）
   * @param dyeMeta  {系别: {dye_color, dye_name}}（来自 lineage.json）
   * @returns {hex, rgb, s(0~0.8), name, base, off}
   */
  function computeBlend(baseLin, counts, dyeMeta) {
    const lins = Object.keys(dyeMeta || {});
    let base = baseLin;
    if (!base) {
      let best = null, bv = 0;
      for (const l of lins) { const c = (counts && counts[l]) || 0; if (c > bv) { bv = c; best = l; } }
      base = best;
    }
    if (!base) {
      return { hex: "#BFB8AC", rgb: [191, 184, 172], s: 0, name: "素灰色", base: null, off: 0 };
    }
    const baseCount = (counts && counts[base]) || 0;
    const baseW = 3 + baseCount;          // 本命锚点权重（吃得再多，基本色也保留一部分）
    let offW = 0, totalW = 0;
    const acc = [0, 0, 0];
    let baseColor = [191, 184, 172];
    for (const l of lins) {
      const c = (counts && counts[l]) || 0;
      const w = (l === base) ? baseW : c;
      if (l !== base && c > 0) offW += c;
      if (w <= 0) continue;
      if (l === base) baseColor = hexToRgb(dyeMeta[l].dye_color);
      const col = hexToRgb(dyeMeta[l].dye_color);
      acc[0] += col[0] * w; acc[1] += col[1] * w; acc[2] += col[2] * w;
      totalW += w;
    }
    if (totalW === 0) {
      return { hex: rgbToHex(baseColor), rgb: baseColor, s: 0, name: nameOf(baseColor) + "（本色）", base, off: 0 };
    }
    let rgb = acc.map(v => v / totalW);
    const s = Math.min(0.85, offW / (offW + baseW + 3));
    rgb = desaturate(rgb, 0.5 * s);        // 染得越深越"发灰"（污浊感）
    return { hex: rgbToHex(rgb), rgb, s, name: nameOf(rgb), base, off: offW };
  }

  function nameOf(rgb) {
    let best = PALETTE[0][0], bd = Infinity;
    for (const [n, r, g, b] of PALETTE) {
      const d = (rgb[0] - r) ** 2 + (rgb[1] - g) ** 2 + (rgb[2] - b) ** 2;
      if (d < bd) { bd = d; best = n; }
    }
    return best;
  }

  /** 对 canvas 像素做保亮度染色（就地修改）
   * @param ctx      canvas 2d context（内容已绘制好）
   * @param w,h      尺寸
   * @param hex      目标颜色
   * @param strength 0~1
   * 规则：≥235 的纯白像素跳过（保护白描边）；其余像素按亮度映射目标色再与原色混合。
   */
  function tintCanvas(ctx, w, h, hex, strength) {
    if (strength <= 0.02) return;
    const [tr, tg, tb] = hexToRgb(hex);
    const id = ctx.getImageData(0, 0, w, h);
    const d = id.data;
    for (let i = 0; i < d.length; i += 4) {
      if (!d[i + 3]) continue;
      const r = d[i], g = d[i + 1], b = d[i + 2];
      if (r >= 235 && g >= 235 && b >= 235) continue; // 白描边保护
      const L = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
      const k = 0.35 + 0.65 * L;                      // 保留明暗结构
      const nr = tr * k, ng = tg * k, nb = tb * k;
      d[i] = r + (nr - r) * strength;
      d[i + 1] = g + (ng - g) * strength;
      d[i + 2] = b + (nb - b) * strength;
    }
    ctx.putImageData(id, 0, 0);
  }

  return { hexToRgb, rgbToHex, luminance, computeBlend, nameOf, tintCanvas, PALETTE };
});
