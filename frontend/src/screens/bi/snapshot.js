// snapshot.js — v0.8.15 分享：DOM 节点 → PNG blob（手写 foreignObject 序列化，零 npm 依赖）。
//
// 为何手写 foreignObject 而非 html2canvas（v0.8.15 grounding 纠偏）：
//   BI 渲染面纯 SVG+HTML 零 canvas + 样式全内联 → foreignObject 由浏览器**原生**渲染，
//   支持 oklch()/color-mix()（html2canvas 自实现 CSS 解析、不支持 oklch → 每色糊）。
//   R-BI-11.1：本文件零 eval / new Function。R-186：零新依赖。
//
// 用法：captureNodeToPng(offscreenNode, {scale, background}) → Promise<Blob 'image/png'>。
// 前提（调用方保证）：node 为「从数据重建的离屏节点」，样式全内联（0 className 依赖可见样式），
//   无外部图片（否则 canvas taint → toBlob 抛）。SnapshotDashboard/SnapshotTable 满足。

export async function captureNodeToPng(node, { scale = 2, background = '#ffffff' } = {}) {
  const rect = node.getBoundingClientRect();
  const width = Math.max(1, Math.ceil(rect.width));
  const height = Math.max(1, Math.ceil(rect.height));

  // 序列化节点为 XHTML（内联样式随节点走；外部样式表不入 — BI 全内联故无损）
  const clone = node.cloneNode(true);
  // 对抗复核 v0.8.15 #HIGH：调用方离屏壳常带 position:fixed;left:-99999px（脱流不占位）。
  // 该定位随 cloneNode 进 foreignObject → 在 SVG 视口里 fixed 定位 → 整树移出画布 → PNG 全白。
  // 截图前把根节点定位归零，令内容自 (0,0) 铺开（尺寸已由 getBoundingClientRect 量定）。
  if (clone.style) { clone.style.position = 'static'; clone.style.left = '0'; clone.style.top = '0'; clone.style.margin = '0'; }
  clone.querySelectorAll('[data-snapshot-exclude]').forEach((el) => el.remove());
  // 对抗复核 v0.8.15 #HIGH（kk 报「宽屏折线消失」）：内联 <svg> 用 width/height:100%（sparkline + ECharts 皆然）。
  // foreignObject→img 栅格化时百分比尺寸不解析 → svg 塌到内在尺寸 → 折线只占局部宽（letterbox/压缩）。
  // 序列化前把每个 svg 的尺寸冻结成实测 px（读原节点 rect，按文档序映射到 clone；已排除 data-snapshot-exclude 子树对齐）。
  const keptOrigSvgs = [...node.querySelectorAll('svg')].filter((s) => !s.closest('[data-snapshot-exclude]'));
  const cloneSvgs = clone.querySelectorAll('svg');
  keptOrigSvgs.forEach((os, i) => {
    const cs = cloneSvgs[i];
    if (!cs) return;
    const r = os.getBoundingClientRect();
    if (r.width > 0 && r.height > 0) {
      cs.setAttribute('width', String(Math.round(r.width)));
      cs.setAttribute('height', String(Math.round(r.height)));
      cs.style.width = Math.round(r.width) + 'px';
      cs.style.height = Math.round(r.height) + 'px';
    }
  });
  const xhtml = new XMLSerializer().serializeToString(clone);

  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}">` +
    `<foreignObject x="0" y="0" width="${width}" height="${height}">` +
    `<div xmlns="http://www.w3.org/1999/xhtml" ` +
    `style="width:${width}px;height:${height}px;background:${background};box-sizing:border-box">` +
    xhtml +
    `</div></foreignObject></svg>`;

  const img = new Image();
  img.decoding = 'sync';
  await new Promise((resolve, reject) => {
    img.onload = () => resolve();
    img.onerror = () => reject(new Error('快照渲染失败（foreignObject → img）'));
    img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
  });

  const canvas = document.createElement('canvas');
  canvas.width = width * scale;
  canvas.height = height * scale;
  const ctx = canvas.getContext('2d');
  ctx.setTransform(scale, 0, 0, scale, 0, 0);
  ctx.fillStyle = background;
  ctx.fillRect(0, 0, width, height);
  ctx.drawImage(img, 0, 0);

  return await new Promise((resolve, reject) => {
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('PNG 编码失败'))), 'image/png');
  });
}

// 离屏挂载 helper：把 React 渲染的节点放到脱离文档流 + 0 尺寸壳的屏外容器，
// 供 captureNodeToPng 截取「全宽全内容」（不裁剪、不闪、不占位）。调用方截完须 remove()。
export function mountOffscreen() {
  const host = document.createElement('div');
  host.setAttribute('aria-hidden', 'true');
  host.style.cssText =
    'position:fixed;left:-99999px;top:0;width:0;height:0;overflow:hidden;pointer-events:none;';
  document.body.appendChild(host);
  return host;
}
