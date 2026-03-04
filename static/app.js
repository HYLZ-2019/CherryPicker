/* =========================================================
   CherryPicker – Frontend Application Logic
   ========================================================= */
"use strict";

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let CFG         = {};          // config from server
let frameIdx    = 0;
let frameCount  = 0;
let methodCount = 0;
let displayMethods = [];       // list of method indices currently shown
let maxDisplay  = 100;         // no hard upper limit; show all active methods
let drawMethodIdx = 0;
let uiMode = "pick";
let pickModeRightPanelWidth = "";
let stitchRenderToken = 0;
const imageSizeCache = new Map();

// crop region (in original image pixels)
let cropX = 0, cropY = 0, cropW = 100, cropH = 100;
let lockRatio = false;
let lockSize  = false;
let cropRatio = 1.0;

// canvas state
let canvasImg = null;          // Image object loaded for draw-box
let imgNatW = 1, imgNatH = 1; // natural image dimensions
let canvasScale = 1;           // display scale factor
let isDragging = false;
let dragStartX = 0, dragStartY = 0;

// crop list
let cropPatches = [];

// stitch settings
const stitchState = {
  methodLayoutText: "",
  methodAliasText: "",
  patchCount: 3,
  exampleLimit: 0,
  exampleGap: 16,
  patchPosition: "bottom",
  borderColors: "red, green, blue",
  patchBorderWidth: 2,
  fullBoxBorderWidth: 2,
  patchGap: 8,
  imageGap: 16,
  fontFamily: "Arial, sans-serif",
  fontSize: 16,
  bigWidth: 220,
};

// ---------------------------------------------------------------------------
// DOM references
// ---------------------------------------------------------------------------
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

const elFrameInput     = $("#frame-idx-input");
const elFrameTotal     = $("#frame-total");
const elBtnToggleMode  = $("#btn-toggle-mode");
const elMethodButtons  = $("#method-buttons");
const elDrawSelect     = $("#draw-method-select");
const elCanvas         = $("#draw-canvas");
const ctx              = elCanvas.getContext("2d");
const elCropX          = $("#crop-x");
const elCropY          = $("#crop-y");
const elCropW          = $("#crop-w");
const elCropH          = $("#crop-h");
const elCropRatio      = $("#crop-ratio");
const elLockRatio      = $("#lock-ratio");
const elLockSize       = $("#lock-size");
const elDisplayGrid    = $("#display-grid");
const elCropList       = $("#crop-list");
const elCropCount      = $("#crop-count");
const elRightPanel     = $("#right-panel");
const elStitchPreview  = $("#stitch-preview-canvas");
const elStitchMethodLayout = $("#stitch-method-layout");
const elStitchPatchCount   = $("#stitch-patch-count");
const elStitchExampleLimit = $("#stitch-example-limit");
const elStitchExampleGap = $("#stitch-example-gap");
const elStitchPatchPosition = $("#stitch-patch-position");
const elStitchBorderColors = $("#stitch-border-colors");
const elStitchBorderWidth = $("#stitch-border-width");
const elStitchFullBoxBorderWidth = $("#stitch-full-box-border-width");
const elStitchPatchGap = $("#stitch-patch-gap");
const elStitchImageGap = $("#stitch-image-gap");
const elStitchFontFamily = $("#stitch-font-family");
const elStitchFontSize = $("#stitch-font-size");
const elStitchBigWidth = $("#stitch-big-width");
const elStitchMethodAlias = $("#stitch-method-alias");
const elBtnSaveStitchConfig = $("#btn-save-stitch-config");
const elBtnLoadStitchConfig = $("#btn-load-stitch-config");
const elBtnExportPdfLossless = $("#btn-export-pdf-lossless");
const elStitchConfigFile = $("#stitch-config-file");
const elStitchConfigAlert = $("#stitch-config-alert");

// ---------------------------------------------------------------------------
// Toast helper
// ---------------------------------------------------------------------------
function toast(msg, type = "info", duration = 2500) {
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = msg;
  const container = $("#toast-container");
  container.appendChild(el);
  setTimeout(() => { el.remove(); }, duration);
}

// ---------------------------------------------------------------------------
// Loading overlay
// ---------------------------------------------------------------------------
function showLoading() {
  if (document.querySelector(".loading-overlay")) return;
  const ov = document.createElement("div");
  ov.className = "loading-overlay";
  ov.innerHTML = '<div class="spinner"></div>';
  document.body.appendChild(ov);
}
function hideLoading() {
  const ov = document.querySelector(".loading-overlay");
  if (ov) ov.remove();
}

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------
async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(txt);
  }
  return res.json();
}

function parseMethodLayout(text) {
  const nameToIdx = new Map(CFG.methods.map((m, i) => [m.name.toLowerCase(), i]));
  const rows = [];
  const lines = text.split(/\r?\n/).map((x) => x.trim()).filter(Boolean);

  const parseLineTokens = (line) => {
    const normalized = line.replace(/，/g, ",");
    const tokens = [];
    const regex = /"([^"]+)"|'([^']+)'|([^,]+)/g;
    let match;
    while ((match = regex.exec(normalized)) !== null) {
      const raw = (match[1] ?? match[2] ?? match[3] ?? "").trim();
      if (raw) tokens.push(raw);
    }
    return tokens;
  };

  for (const line of lines) {
    const tokens = parseLineTokens(line);
    const row = [];
    for (const token of tokens) {
      const idx = nameToIdx.get(token.toLowerCase());
      if (idx !== undefined) row.push(idx);
    }
    if (row.length > 0) rows.push(row);
  }
  if (rows.length === 0) {
    const fallback = buildDefaultMethodLayout(CFG.methods.map((m) => m.name));
    const fallbackLines = fallback.split(/\r?\n/).map((x) => x.trim()).filter(Boolean);
    for (const line of fallbackLines) {
      const row = [];
      const tokens = parseLineTokens(line);
      for (const token of tokens) {
        const idx = nameToIdx.get(token.toLowerCase());
        if (idx !== undefined) row.push(idx);
      }
      if (row.length > 0) rows.push(row);
    }
  }
  return rows;
}

function parseMethodLayoutWithUnknown(text) {
  const nameToIdx = new Map(CFG.methods.map((m, i) => [m.name.toLowerCase(), i]));
  const lines = text.split(/\r?\n/).map((x) => x.trim()).filter(Boolean);
  const unknown = [];
  const rows = [];
  const regex = /"([^"]+)"|'([^']+)'|([^,，]+)/g;
  for (const lineRaw of lines) {
    const line = lineRaw.replace(/，/g, ",");
    const row = [];
    let match;
    while ((match = regex.exec(line)) !== null) {
      const token = (match[1] ?? match[2] ?? match[3] ?? "").trim();
      if (!token) continue;
      const idx = nameToIdx.get(token.toLowerCase());
      if (idx === undefined) unknown.push(token);
      else row.push(idx);
    }
    if (row.length > 0) rows.push(row);
  }
  return { rows, unknown };
}

function setStitchAlert(message = "") {
  if (!elStitchConfigAlert) return;
  if (!message) {
    elStitchConfigAlert.style.display = "none";
    elStitchConfigAlert.textContent = "";
    return;
  }
  elStitchConfigAlert.style.display = "block";
  elStitchConfigAlert.textContent = message;
}

function validateCurrentStitchFormat() {
  if (uiMode !== "stitch") return true;
  const errors = [];
  const detail = parseMethodLayoutWithUnknown(elStitchMethodLayout.value || "");
  if (detail.rows.length === 0) {
    errors.push("Methods Layout 无法解析出有效方法。请检查格式和方法名。");
  }
  if (detail.unknown.length > 0) {
    errors.push(`Methods Layout 包含不存在的方法名: ${[...new Set(detail.unknown)].join(", ")}`);
  }
  try {
    const data = JSON.parse(elStitchMethodAlias.value || "{}");
    if (typeof data !== "object" || Array.isArray(data) || data === null) {
      errors.push("Method Aliases 必须是 JSON 对象。\n例如: {\"Input\":\"Input\"}");
    } else {
      const names = new Set(CFG.methods.map((m) => m.name));
      const bad = Object.keys(data).filter((k) => !names.has(k));
      if (bad.length > 0) {
        errors.push(`Method Aliases 包含不存在的方法键: ${bad.join(", ")}`);
      }
    }
  } catch {
    errors.push("Method Aliases JSON 解析失败。请检查逗号、引号和括号。");
  }
  setStitchAlert(errors.join("\n"));
  return errors.length === 0;
}

function buildDefaultMethodLayout(methodNames) {
  if (!methodNames || methodNames.length === 0) return "";
  if (methodNames.length <= 5) {
    return methodNames.map((name) => `"${name}"`).join(",");
  }
  const lines = [];
  for (let i = 0; i < methodNames.length; i += 5) {
    const row = methodNames.slice(i, i + 5);
    lines.push(row.map((name) => `"${name}"`).join(","));
  }
  return lines.join("\n");
}

function buildDefaultAliasMap(methodNames) {
  const obj = {};
  methodNames.forEach((name) => {
    obj[name] = name;
  });
  return obj;
}

function parseMethodAliasMap(text) {
  const fallback = buildDefaultAliasMap(CFG.methods.map((m) => m.name));
  if (!text || !text.trim()) return fallback;
  try {
    const data = JSON.parse(text);
    if (!data || typeof data !== "object" || Array.isArray(data)) {
      return fallback;
    }
    return { ...fallback, ...data };
  } catch {
    return fallback;
  }
}

function indexToAlphaTag(idx) {
  let n = idx;
  let out = "";
  while (n >= 0) {
    out = String.fromCharCode(97 + (n % 26)) + out;
    n = Math.floor(n / 26) - 1;
  }
  return out;
}

function getGroupedCrops() {
  const groups = new Map();
  cropPatches.forEach((item) => {
    if (!groups.has(item.img_idx)) groups.set(item.img_idx, []);
    groups.get(item.img_idx).push(item.crop_box);
  });
  const out = [...groups.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([imgIdx, boxes]) => ({ imgIdx, boxes }));
  return out;
}

function collectStitchSettings() {
  stitchState.methodLayoutText = elStitchMethodLayout.value;
  stitchState.patchCount = Math.max(1, parseInt(elStitchPatchCount.value) || 1);
  stitchState.exampleLimit = Math.max(0, parseInt(elStitchExampleLimit.value) || 0);
  stitchState.exampleGap = Math.max(0, parseInt(elStitchExampleGap.value) || 0);
  stitchState.patchPosition = elStitchPatchPosition.value === "right" ? "right" : "bottom";
  stitchState.borderColors = elStitchBorderColors.value;
  stitchState.patchBorderWidth = Math.max(0, parseInt(elStitchBorderWidth.value) || 0);
  stitchState.fullBoxBorderWidth = Math.max(0, parseInt(elStitchFullBoxBorderWidth.value) || 0);
  stitchState.patchGap = Math.max(0, parseInt(elStitchPatchGap.value) || 0);
  stitchState.imageGap = Math.max(0, parseInt(elStitchImageGap.value) || 0);
  stitchState.fontFamily = (elStitchFontFamily.value || "Arial, sans-serif").trim();
  stitchState.fontSize = Math.max(8, parseInt(elStitchFontSize.value) || 16);
  stitchState.bigWidth = Math.max(60, parseInt(elStitchBigWidth.value) || 220);
  stitchState.methodAliasText = elStitchMethodAlias.value;
}

function getStitchPayload() {
  collectStitchSettings();
  const detail = parseMethodLayoutWithUnknown(stitchState.methodLayoutText);
  return {
    method_grid: detail.rows,
    patches_per_example: stitchState.patchCount,
    example_limit: stitchState.exampleLimit,
    example_gap: stitchState.exampleGap,
    patch_position: stitchState.patchPosition,
    patch_border_colors: stitchState.borderColors
      .split(",")
      .map((x) => x.trim())
      .filter(Boolean),
    patch_border_width: stitchState.patchBorderWidth,
    full_box_border_width: stitchState.fullBoxBorderWidth,
    patch_big_gap: stitchState.patchGap,
    image_gap: stitchState.imageGap,
    font_family: stitchState.fontFamily,
    font_size: stitchState.fontSize,
    big_image_width: stitchState.bigWidth,
    method_aliases: parseMethodAliasMap(stitchState.methodAliasText),
  };
}

async function getImageSizeCached(methodIdx, frameIdx) {
  const key = `${methodIdx}-${frameIdx}`;
  if (imageSizeCache.has(key)) return imageSizeCache.get(key);
  const size = await api(`/api/image-size/${methodIdx}/${frameIdx}`);
  imageSizeCache.set(key, size);
  return size;
}

async function refreshStitchPreview() {
  if (uiMode !== "stitch") return;
  const myToken = ++stitchRenderToken;
  const payload = getStitchPayload();
  const groups = getGroupedCrops();
  if (payload.method_grid.length === 0) {
    elStitchPreview.innerHTML = '<p class="stitch-empty">方法排布为空，请输入如 "A","B","C" 的行文本。</p>';
    return;
  }
  if (groups.length === 0) {
    elStitchPreview.innerHTML = '<p class="stitch-empty">还没有保存 crop。请先在挑图模式点击 Save Current Crop。</p>';
    return;
  }

  const borderColors = payload.patch_border_colors.length > 0 ? payload.patch_border_colors : ["red"];
  const aliasMap = payload.method_aliases || {};
  const limit = payload.example_limit > 0 ? Math.min(payload.example_limit, groups.length) : groups.length;
  const patchInnerGap = Math.max(0, Math.floor(payload.patch_big_gap / 2));
  const flatMethodOrder = payload.method_grid.flat();
  const slotTargetContentWidth = new Map();

  const estimateBottomContentWidth = (bigW, patchCnt, borderW, innerGap) => {
    if (patchCnt <= 0) return Math.max(1, bigW);
    const gapTotal = innerGap * Math.max(0, patchCnt - 1);
    const patchAxisTotal = Math.max(patchCnt, bigW - gapTotal);
    const patchStripW = patchAxisTotal + gapTotal + (2 * borderW * patchCnt);
    return Math.max(bigW, patchStripW);
  };

  const estimateRightContentWidth = (bigW, bigH, boxes, patchCnt, borderW, innerGap, outerGap) => {
    if (patchCnt <= 0) return Math.max(1, bigW);
    const gapTotal = innerGap * Math.max(0, patchCnt - 1);
    const patchAxisTotal = Math.max(patchCnt, bigH - gapTotal);
    const axisBase = Math.floor(patchAxisTotal / patchCnt);
    let axisRemain = patchAxisTotal;
    let stripW = 1;
    for (let i = 0; i < patchCnt; i++) {
      const axisSize = (i === patchCnt - 1) ? axisRemain : axisBase;
      axisRemain -= axisSize;
      const box = boxes[i] || [0, 0, 1, 1];
      const bw = Math.max(1, Math.abs((box[2] ?? 1) - (box[0] ?? 0)));
      const bh = Math.max(1, Math.abs((box[3] ?? 1) - (box[1] ?? 0)));
      const patchW = Math.max(1, Math.round(axisSize * bw / bh));
      stripW = Math.max(stripW, patchW + 2 * borderW);
    }
    return Math.max(1, bigW + outerGap + stripW);
  };

  const estimateContentWidth = (bigW, bigH, boxes, patchCnt, position, borderW, innerGap, outerGap) => {
    if (position === "right") {
      return estimateRightContentWidth(bigW, bigH, boxes, patchCnt, borderW, innerGap, outerGap);
    }
    return estimateBottomContentWidth(bigW, patchCnt, borderW, innerGap);
  };

  elStitchPreview.style.setProperty("--example-gap", `${payload.example_gap}px`);

  const htmlParts = [];
  for (let gi = 0; gi < limit; gi++) {
    const group = groups[gi];
    htmlParts.push(`<div class="st-example" style="font-family:${payload.font_family};font-size:${payload.font_size}px;">`);
    let slotIdx = 0;

    for (let r = 0; r < payload.method_grid.length; r++) {
      const row = payload.method_grid[r];
      htmlParts.push(`<div class="st-row" style="gap:${payload.image_gap}px;">`);

      for (let m = 0; m < row.length; m++) {
        const mIdx = row[m];
        const mName = CFG.methods[mIdx]?.name || `Method-${mIdx}`;
        const showName = aliasMap[mName] || mName;
        const labelIndex = Math.max(0, flatMethodOrder.indexOf(mIdx));
        const labelTag = indexToAlphaTag(labelIndex);
        const patchCnt = Math.min(payload.patches_per_example, group.boxes.length);
        const usedBoxes = group.boxes.slice(0, patchCnt);
        const usedColors = usedBoxes.map((_, idx) => borderColors[idx % borderColors.length]);
        const slotKey = slotIdx;
        slotIdx += 1;
        const boxesJson = encodeURIComponent(JSON.stringify(usedBoxes));
        const colorsText = encodeURIComponent(usedColors.join(","));

        let baseBigHeight = payload.big_image_width;
        try {
          const s = await getImageSizeCached(mIdx, group.imgIdx);
          if (s && s.width > 0) {
            baseBigHeight = Math.max(1, Math.round(payload.big_image_width * s.height / s.width));
          }
        } catch (e) {
          baseBigHeight = payload.big_image_width;
        }

        const currentContentW = estimateContentWidth(
          payload.big_image_width,
          baseBigHeight,
          usedBoxes,
          patchCnt,
          payload.patch_position,
          payload.patch_border_width,
          patchInnerGap,
          payload.patch_big_gap,
        );

        if (gi === 0 && !slotTargetContentWidth.has(slotKey)) {
          slotTargetContentWidth.set(slotKey, currentContentW);
        }
        const targetContentW = slotTargetContentWidth.get(slotKey) || currentContentW;
        const widthScale = currentContentW > 0 ? (targetContentW / currentContentW) : 1;
        const scaledBigWidth = Math.max(1, Math.round(payload.big_image_width * widthScale));
        const scaledBigHeight = Math.max(1, Math.round(baseBigHeight * widthScale));
        const scaledPatchGap = Math.max(0, Math.round(payload.patch_big_gap * widthScale));
        const scaledPatchInnerGap = Math.max(0, Math.round(patchInnerGap * widthScale));

        const fullUrl = `/api/image-boxed/${mIdx}/${group.imgIdx}?boxes_json=${boxesJson}&colors=${colorsText}&border_width=${payload.full_box_border_width}&t=${Date.now()}`;

        if (myToken !== stitchRenderToken) return;

        htmlParts.push(`<div class="st-method">`);
        htmlParts.push(`<div class="st-image-wrap ${payload.patch_position}" style="gap:${scaledPatchGap}px;">`);
        htmlParts.push(`<img class="st-main-image" style="width:${scaledBigWidth}px;" src="${fullUrl}" alt="full" />`);
        htmlParts.push(`<div class="st-patches ${payload.patch_position}" style="gap:${scaledPatchInnerGap}px;">`);

        const gapTotal = scaledPatchInnerGap * Math.max(0, patchCnt - 1);
        const patchAxisTotal = payload.patch_position === "bottom"
          ? Math.max(patchCnt, scaledBigWidth - gapTotal)
          : Math.max(patchCnt, scaledBigHeight - gapTotal);
        const axisBase = Math.floor(patchAxisTotal / Math.max(1, patchCnt));
        let axisRemain = patchAxisTotal;

        for (let pi = 0; pi < patchCnt; pi++) {
          const box = group.boxes[pi];
          const c = borderColors[pi % borderColors.length];
          const patchUrl = `/api/crop-preview/${mIdx}/${group.imgIdx}?x1=${box[0]}&y1=${box[1]}&x2=${box[2]}&y2=${box[3]}&t=${Date.now()}`;
          const axisSize = (pi === patchCnt - 1) ? axisRemain : axisBase;
          axisRemain -= axisSize;
          const style = payload.patch_position === "bottom"
            ? `width:${axisSize}px;height:auto;border:${payload.patch_border_width}px solid ${c};`
            : `height:${axisSize}px;width:auto;border:${payload.patch_border_width}px solid ${c};`;
          htmlParts.push(`<img class="st-patch" style="${style}" src="${patchUrl}" alt="patch" />`);
        }

        htmlParts.push(`</div></div>`);
        htmlParts.push(`<div class="st-method-label">(${labelTag}) ${showName}</div>`);
        htmlParts.push(`</div>`);
      }

      htmlParts.push(`</div>`);
    }

    htmlParts.push(`</div>`);
  }

  if (myToken !== stitchRenderToken) return;
  elStitchPreview.innerHTML = htmlParts.join("");
}

// ---------------------------------------------------------------------------
// Initialisation
// ---------------------------------------------------------------------------
async function init() {
  try {
    CFG = await api("/api/config");
  } catch (e) {
    toast("Failed to load config: " + e.message, "error", 5000);
    return;
  }

  frameCount  = CFG.frame_count;
  methodCount = CFG.method_count;
  maxDisplay  = methodCount; // show all methods – grid auto-layouts

  elFrameInput.max = frameCount - 1;
  elFrameTotal.textContent = `/ ${frameCount}`;

  // Build method toggle buttons
  elMethodButtons.innerHTML = "";
  CFG.methods.forEach((m, i) => {
    const btn = document.createElement("button");
    btn.textContent = m.name;
    btn.dataset.idx = i;
    btn.addEventListener("click", () => toggleMethod(i));
    elMethodButtons.appendChild(btn);
  });

  // Build draw-method selector
  elDrawSelect.innerHTML = "";
  CFG.methods.forEach((m, i) => {
    const opt = document.createElement("option");
    opt.value = i;
    opt.textContent = m.name;
    elDrawSelect.appendChild(opt);
  });
  elDrawSelect.value = "0";

  // Build display grid – cells are created dynamically in refreshDisplays()
  elDisplayGrid.innerHTML = "";

  // Initially show ALL methods
  displayMethods = [];
  for (let i = 0; i < methodCount; i++) displayMethods.push(i);
  syncMethodButtons();

  // Initial load
  await loadCrops();
  await refreshAll();

  // Stitch controls init
  const allMethodNames = CFG.methods.map((m) => m.name);
  stitchState.methodLayoutText = buildDefaultMethodLayout(allMethodNames);
  stitchState.methodAliasText = JSON.stringify(buildDefaultAliasMap(allMethodNames), null, 2);

  elStitchMethodLayout.value = stitchState.methodLayoutText;
  elStitchMethodAlias.value = stitchState.methodAliasText;
  elStitchPatchCount.value = stitchState.patchCount;
  elStitchExampleLimit.value = stitchState.exampleLimit;
  elStitchExampleGap.value = stitchState.exampleGap;
  elStitchPatchPosition.value = stitchState.patchPosition;
  elStitchBorderColors.value = stitchState.borderColors;
  elStitchBorderWidth.value = stitchState.patchBorderWidth;
  elStitchFullBoxBorderWidth.value = stitchState.fullBoxBorderWidth;
  elStitchPatchGap.value = stitchState.patchGap;
  elStitchImageGap.value = stitchState.imageGap;
  elStitchFontFamily.value = stitchState.fontFamily;
  elStitchFontSize.value = stitchState.fontSize;
  elStitchBigWidth.value = stitchState.bigWidth;

  bindStitchInputListeners();
  bindStitchConfigActions();
  setMode("pick");
}

function setMode(mode) {
  uiMode = mode === "stitch" ? "stitch" : "pick";
  document.body.classList.toggle("mode-stitch", uiMode === "stitch");
  elBtnToggleMode.classList.toggle("active", uiMode === "stitch");
  elBtnToggleMode.textContent = uiMode === "stitch" ? "🎯 挑图模式" : "🧩 拼图模式";
  if (uiMode === "stitch") {
    pickModeRightPanelWidth = elRightPanel.style.width || "";
    elRightPanel.style.width = "";
    refreshStitchPreview();
  } else {
    if (pickModeRightPanelWidth !== "") {
      elRightPanel.style.width = pickModeRightPanelWidth;
    }
    refreshDisplays();
  }
}

function bindStitchInputListeners() {
  [
    elStitchMethodLayout,
    elStitchPatchCount,
    elStitchExampleLimit,
    elStitchExampleGap,
    elStitchPatchPosition,
    elStitchBorderColors,
    elStitchBorderWidth,
    elStitchFullBoxBorderWidth,
    elStitchPatchGap,
    elStitchImageGap,
    elStitchFontFamily,
    elStitchFontSize,
    elStitchBigWidth,
    elStitchMethodAlias,
  ].forEach((el) => {
    const evt = (el.tagName === "SELECT" || el.tagName === "TEXTAREA") ? "input" : "input";
    el.addEventListener(evt, () => {
      validateCurrentStitchFormat();
      refreshStitchPreview();
    });
  });
}

function bindStitchConfigActions() {
  if (elBtnExportPdfLossless) {
    elBtnExportPdfLossless.addEventListener("click", exportStitchPDFLossless);
  }
  if (elBtnSaveStitchConfig) {
    elBtnSaveStitchConfig.addEventListener("click", saveStitchConfigYaml);
  }
  if (elBtnLoadStitchConfig) {
    elBtnLoadStitchConfig.addEventListener("click", () => elStitchConfigFile.click());
  }
  if (elStitchConfigFile) {
    elStitchConfigFile.addEventListener("change", importStitchConfigYamlFromFile);
  }
}

async function exportStitchPDFLossless() {
  if (!validateCurrentStitchFormat()) {
    toast("当前配置存在格式问题，请先修复后再导出。", "error");
    return;
  }
  const payload = getStitchPayload();
  if (!payload.method_grid.length) {
    toast("请先填写有效的方法排列。", "error");
    return;
  }
  showLoading();
  try {
    const res = await fetch("/api/stitch-export-pdf-lossless", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text());
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "cherrypicker_stitch_lossless.pdf";
    a.click();
    URL.revokeObjectURL(url);
    toast("无损 PDF 已导出", "success");
  } catch (e) {
    setStitchAlert(`无损 PDF 导出失败: ${e.message}`);
    toast("无损 PDF 导出失败", "error");
  } finally {
    hideLoading();
  }
}

async function saveStitchConfigYaml() {
  if (!validateCurrentStitchFormat()) {
    toast("当前配置存在格式问题，请先修复后再导出。", "error");
    return;
  }
  const payload = getStitchPayload();
  if (!payload.method_grid.length) {
    toast("Methods Layout 无效，无法导出。", "error");
    return;
  }
  showLoading();
  try {
    const res = await fetch("/api/stitch-config/export-yaml", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text());
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "cherrypicker_stitch_config.yaml";
    a.click();
    URL.revokeObjectURL(url);
    toast("拼图配置 YAML 已导出", "success");
  } catch (e) {
    setStitchAlert(`导出失败: ${e.message}`);
    toast("导出配置失败", "error");
  } finally {
    hideLoading();
  }
}

async function importStitchConfigYamlFromFile() {
  const file = elStitchConfigFile.files && elStitchConfigFile.files[0];
  if (!file) return;
  showLoading();
  try {
    const text = await file.text();
    const res = await fetch("/api/stitch-config/import-yaml", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ yaml_text: text }),
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    applyImportedStitchConfig(data);
    setStitchAlert("");
    refreshStitchPreview();
    toast("拼图配置已导入", "success");
  } catch (e) {
    setStitchAlert(`导入失败: ${e.message}`);
    toast("导入配置失败", "error");
  } finally {
    hideLoading();
    elStitchConfigFile.value = "";
  }
}

function applyImportedStitchConfig(data) {
  const payload = data.payload || {};
  const methodLayout = data.method_layout || [];
  const methodLayoutText = methodLayout.map((row) => row.map((n) => `"${n}"`).join(",")).join("\n");

  elStitchMethodLayout.value = methodLayoutText;
  elStitchPatchCount.value = payload.patches_per_example ?? elStitchPatchCount.value;
  elStitchExampleLimit.value = payload.example_limit ?? elStitchExampleLimit.value;
  elStitchExampleGap.value = payload.example_gap ?? elStitchExampleGap.value;
  elStitchPatchPosition.value = payload.patch_position ?? elStitchPatchPosition.value;
  elStitchBorderColors.value = (payload.patch_border_colors || []).join(", ");
  elStitchBorderWidth.value = payload.patch_border_width ?? elStitchBorderWidth.value;
  elStitchFullBoxBorderWidth.value = payload.full_box_border_width ?? elStitchFullBoxBorderWidth.value;
  elStitchPatchGap.value = payload.patch_big_gap ?? elStitchPatchGap.value;
  elStitchImageGap.value = payload.image_gap ?? elStitchImageGap.value;
  elStitchFontFamily.value = payload.font_family ?? elStitchFontFamily.value;
  elStitchFontSize.value = payload.font_size ?? elStitchFontSize.value;
  elStitchBigWidth.value = payload.big_image_width ?? elStitchBigWidth.value;
  elStitchMethodAlias.value = JSON.stringify(payload.method_aliases || {}, null, 2);

  validateCurrentStitchFormat();
}

// ---------------------------------------------------------------------------
// Method toggling
// ---------------------------------------------------------------------------
function toggleMethod(idx) {
  const pos = displayMethods.indexOf(idx);
  if (pos >= 0) {
    displayMethods.splice(pos, 1);
  } else {
    displayMethods.push(idx);
  }
  syncMethodButtons();
  refreshDisplays();
}

function selectAllMethods() {
  displayMethods = Array.from({ length: methodCount }, (_, i) => i);
  syncMethodButtons();
  refreshDisplays();
}

function deselectAllMethods() {
  displayMethods = [];
  syncMethodButtons();
  refreshDisplays();
}

function nextMethods() {
  // If none or all shown, show all
  if (displayMethods.length === 0 || displayMethods.length === methodCount) {
    selectAllMethods();
    return;
  }
  // Shift every displayed index forward by 1
  displayMethods = displayMethods.map(i => (i + 1) % methodCount);
  syncMethodButtons();
  refreshDisplays();
}

function prevMethods() {
  if (displayMethods.length === 0 || displayMethods.length === methodCount) {
    selectAllMethods();
    return;
  }
  displayMethods = displayMethods.map(i => ((i - 1) + methodCount) % methodCount);
  syncMethodButtons();
  refreshDisplays();
}

function syncMethodButtons() {
  $$('#method-buttons button').forEach(btn => {
    const i = parseInt(btn.dataset.idx);
    btn.classList.toggle("active", displayMethods.includes(i));
  });
}

// ---------------------------------------------------------------------------
// Frame navigation
// ---------------------------------------------------------------------------
function setFrame(idx) {
  idx = Math.max(0, Math.min(idx, frameCount - 1));
  if (isNaN(idx)) return;
  frameIdx = idx;
  elFrameInput.value = frameIdx;
  refreshAll();
}

// ---------------------------------------------------------------------------
// Refresh everything
// ---------------------------------------------------------------------------
async function refreshAll() {
  await Promise.all([loadDrawBox(), refreshDisplays()]);
}

// ---------------------------------------------------------------------------
// Draw-box canvas
// ---------------------------------------------------------------------------
async function loadDrawBox() {
  const methodIdx = drawMethodIdx;
  const url = `/api/image/${methodIdx}/${frameIdx}?t=${Date.now()}`;
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      canvasImg = img;
      imgNatW = img.naturalWidth;
      imgNatH = img.naturalHeight;
      fitCanvas();
      drawCanvas();
      resolve();
    };
    img.onerror = () => {
      toast("Failed to load draw-box image", "error");
      resolve();
    };
    img.src = url;
  });
}

function fitCanvas() {
  const wrapper = $("#canvas-wrapper");
  const maxW = wrapper.parentElement.clientWidth - 24;
  const maxH = wrapper.parentElement.clientHeight - 24;
  const scaleW = maxW / imgNatW;
  const scaleH = maxH / imgNatH;
  canvasScale = Math.min(scaleW, scaleH, 1); // never upscale
  elCanvas.width  = Math.round(imgNatW * canvasScale);
  elCanvas.height = Math.round(imgNatH * canvasScale);
}

function drawCanvas() {
  if (!canvasImg) return;
  ctx.clearRect(0, 0, elCanvas.width, elCanvas.height);
  ctx.drawImage(canvasImg, 0, 0, elCanvas.width, elCanvas.height);

  // Draw crop rectangle
  const s = canvasScale;
  const rx = cropX * s, ry = cropY * s, rw = cropW * s, rh = cropH * s;

  ctx.strokeStyle = "#ff4444";
  ctx.lineWidth = 2;
  ctx.strokeRect(rx, ry, rw, rh);

  // Corner indicators
  ctx.fillStyle = "#4488ff";
  ctx.beginPath(); ctx.arc(rx, ry, 5, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = "#44ff88";
  ctx.beginPath(); ctx.arc(rx + rw, ry + rh, 5, 0, Math.PI * 2); ctx.fill();

  // Semi-transparent overlay outside the crop area
  ctx.fillStyle = "rgba(0,0,0,0.3)";
  // top
  ctx.fillRect(0, 0, elCanvas.width, ry);
  // bottom
  ctx.fillRect(0, ry + rh, elCanvas.width, elCanvas.height - ry - rh);
  // left
  ctx.fillRect(0, ry, rx, rh);
  // right
  ctx.fillRect(rx + rw, ry, elCanvas.width - rx - rw, rh);
}

// Canvas → image coords
function canvasToImg(cx, cy) {
  return { x: Math.round(cx / canvasScale), y: Math.round(cy / canvasScale) };
}

// ---------------------------------------------------------------------------
// Crop region helpers
// ---------------------------------------------------------------------------
function setCropRegion(x, y, w, h, fromInput = false) {
  // Ensure minimum size
  w = Math.max(1, w);
  h = Math.max(1, h);

  // Clamp within image bounds
  x = Math.max(0, Math.min(x, imgNatW - 1));
  y = Math.max(0, Math.min(y, imgNatH - 1));
  w = Math.min(w, imgNatW - x);
  h = Math.min(h, imgNatH - y);

  cropX = x; cropY = y; cropW = w; cropH = h;
  cropRatio = h / w;

  if (!fromInput) {
    elCropX.value = cropX;
    elCropY.value = cropY;
    elCropW.value = cropW;
    elCropH.value = cropH;
    elCropRatio.value = cropRatio.toFixed(4);
  }

  drawCanvas();
  refreshCropPreviews();
}

function applyCropFromInputs() {
  let x = parseInt(elCropX.value) || 0;
  let y = parseInt(elCropY.value) || 0;
  let w = parseInt(elCropW.value) || 100;
  let h = parseInt(elCropH.value) || 100;

  if (lockRatio) {
    h = Math.round(w * cropRatio);
  }
  setCropRegion(x, y, w, h, true);
  // sync back
  elCropW.value = cropW;
  elCropH.value = cropH;
  elCropRatio.value = (cropH / cropW).toFixed(4);
}

// ---------------------------------------------------------------------------
// Canvas interaction (click / drag)
// ---------------------------------------------------------------------------
elCanvas.addEventListener("mousedown", (e) => {
  e.preventDefault();
  const rect = elCanvas.getBoundingClientRect();
  const cx = e.clientX - rect.left;
  const cy = e.clientY - rect.top;
  const { x, y } = canvasToImg(cx, cy);

  if (e.button === 0) {
    // Left button – move box so top-left = click point (preserve size)
    isDragging = true;
    setCropRegion(x, y, cropW, cropH);
  } else if (e.button === 2) {
    // Right button – set bottom-right corner
    let nw = x - cropX;
    let nh = y - cropY;
    if (nw < 1 || nh < 1) return;
    if (lockRatio) {
      nh = Math.round(nw * cropRatio);
    }
    if (lockSize) {
      // move box so bottom-right is at click
      setCropRegion(x - cropW, y - cropH, cropW, cropH);
    } else {
      setCropRegion(cropX, cropY, nw, nh);
    }
  }
});

elCanvas.addEventListener("mousemove", (e) => {
  if (!isDragging) return;
  const rect = elCanvas.getBoundingClientRect();
  const cx = e.clientX - rect.left;
  const cy = e.clientY - rect.top;
  const { x, y } = canvasToImg(cx, cy);

  // Dragging with left button – move box following cursor
  setCropRegion(x, y, cropW, cropH);
});

elCanvas.addEventListener("mouseup", () => { isDragging = false; });
elCanvas.addEventListener("mouseleave", () => { isDragging = false; });
elCanvas.addEventListener("contextmenu", (e) => e.preventDefault());

// ---------------------------------------------------------------------------
// Input listeners
// ---------------------------------------------------------------------------
[elCropX, elCropY, elCropW, elCropH].forEach(el => {
  el.addEventListener("input", () => applyCropFromInputs());
});

elCropRatio.addEventListener("input", () => {
  if (lockRatio) return;
  const r = parseFloat(elCropRatio.value);
  if (isNaN(r) || r <= 0) return;
  cropRatio = r;
  const newH = Math.round(cropW * cropRatio);
  setCropRegion(cropX, cropY, cropW, newH);
});

elLockRatio.addEventListener("change", () => {
  lockRatio = elLockRatio.checked;
  elCropRatio.disabled = lockRatio;
  if (lockRatio) cropRatio = cropH / Math.max(cropW, 1);
});

elLockSize.addEventListener("change", () => {
  lockSize = elLockSize.checked;
  elCropW.disabled = lockSize;
  elCropH.disabled = lockSize;
});

elDrawSelect.addEventListener("change", () => {
  drawMethodIdx = parseInt(elDrawSelect.value);
  loadDrawBox();
});

elFrameInput.addEventListener("input", () => setFrame(parseInt(elFrameInput.value)));

// Button listeners
$("#btn-prev-frame").addEventListener("click", () => setFrame(frameIdx - 1));
$("#btn-next-frame").addEventListener("click", () => setFrame(frameIdx + 1));
$("#btn-prev-methods").addEventListener("click", prevMethods);
$("#btn-next-methods").addEventListener("click", nextMethods);
$("#btn-save-crop").addEventListener("click", saveCrop);
$("#btn-make-crops").addEventListener("click", makeCrops);
$("#btn-clear-crops").addEventListener("click", clearCrops);
$("#btn-export-html").addEventListener("click", exportStitchHTML);
$("#btn-export-pdf").addEventListener("click", exportStitchPDF);
elBtnToggleMode.addEventListener("click", () => setMode(uiMode === "pick" ? "stitch" : "pick"));

// ---------------------------------------------------------------------------
// Keyboard shortcuts
// ---------------------------------------------------------------------------
document.addEventListener("keydown", (e) => {
  if (uiMode !== "pick") return;
  // Ignore when inside inputs
  if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT" || e.target.tagName === "TEXTAREA") return;

  switch (e.key.toLowerCase()) {
    case "a": setFrame(frameIdx - 1); break;
    case "d": setFrame(frameIdx + 1); break;
    case "w": nextMethods(); break;
    case "s": prevMethods(); break;
    case " ": e.preventDefault(); saveCrop(); break;
    case "delete": e.preventDefault(); deleteLastCrop(); break;
  }
});

// ---------------------------------------------------------------------------
// Display grid refresh  (dynamic cell creation – smart auto-layout)
// ---------------------------------------------------------------------------
function computeGridColumns() {
  const panel = $("#right-panel");
  if (!panel) return 1;
  const availW = panel.clientWidth - 20; // padding
  const n = displayMethods.length;
  if (n === 0) return 1;

  // Target: maximize cell width. Try column counts from 1..n,
  // pick the most columns where each cell is still >= 280px.
  // Also cap at ceil(sqrt(n)) so layout stays roughly square.
  const maxColsBySqrt = Math.ceil(Math.sqrt(n));
  const maxColsByWidth = Math.floor(availW / 280) || 1;
  const cols = Math.max(1, Math.min(n, maxColsBySqrt, maxColsByWidth));
  return cols;
}

async function refreshDisplays() {
  // Compute optimal columns and apply
  const cols = computeGridColumns();
  elDisplayGrid.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;

  // Rebuild cells to match current displayMethods
  elDisplayGrid.innerHTML = "";
  displayMethods.forEach((mIdx, i) => {
    const cell = document.createElement("div");
    cell.className = "display-cell";
    cell.id = `cell-${i}`;
    const mName = CFG.methods[mIdx]?.name || "?";
    cell.innerHTML = `
      <div class="method-name">${mName}</div>
      <div class="images-row">
        <img class="full-img" src="/api/image/${mIdx}/${frameIdx}?t=${Date.now()}" alt="full" />
        <img class="crop-img" src="" alt="crop" />
      </div>`;
    elDisplayGrid.appendChild(cell);
  });
  refreshCropPreviews();
}

function refreshCropPreviews() {
  displayMethods.forEach((mIdx, i) => {
    const cell = $(`#cell-${i}`);
    if (!cell) return;
    const cropImg = cell.querySelector(".crop-img");
    if (cropW > 0 && cropH > 0) {
      cropImg.src = `/api/crop-preview/${mIdx}/${frameIdx}?x1=${cropX}&y1=${cropY}&x2=${cropX + cropW}&y2=${cropY + cropH}&t=${Date.now()}`;
    }
  });
}

// ---------------------------------------------------------------------------
// Crop management
// ---------------------------------------------------------------------------
async function loadCrops() {
  try {
    const data = await api("/api/crops");
    cropPatches = data.crop_patches || [];
    renderCropList();
    refreshStitchPreview();
  } catch (e) {
    console.error(e);
  }
}

function renderCropList() {
  elCropCount.textContent = `(${cropPatches.length})`;
  elCropList.innerHTML = "";
  cropPatches.forEach((p, i) => {
    const li = document.createElement("li");
    const box = p.crop_box;
    li.innerHTML = `<span title="Click to jump">Frame ${p.img_idx} [${box[0]},${box[1]}→${box[2]},${box[3]}]</span><span class="del-crop" title="Delete">×</span>`;
    li.querySelector("span").addEventListener("click", () => {
      setFrame(p.img_idx);
      setCropRegion(box[0], box[1], box[2] - box[0], box[3] - box[1]);
    });
    li.querySelector(".del-crop").addEventListener("click", (e) => {
      e.stopPropagation();
      deleteCrop(i);
    });
    elCropList.appendChild(li);
  });
  // Scroll to bottom
  elCropList.scrollTop = elCropList.scrollHeight;
}

async function saveCrop() {
  const box = [cropX, cropY, cropX + cropW, cropY + cropH];
  try {
    const data = await api("/api/crops", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ img_idx: frameIdx, crop_box: box }),
    });
    toast(`Crop saved! Frame ${frameIdx} [${box}]`, "success");
    await loadCrops();
  } catch (e) {
    toast("Failed to save crop: " + e.message, "error");
  }
}

async function deleteCrop(idx) {
  try {
    await api(`/api/crops/${idx}`, { method: "DELETE" });
    toast("Crop removed", "info");
    await loadCrops();
  } catch (e) {
    toast("Failed to delete crop: " + e.message, "error");
  }
}

async function deleteLastCrop() {
  if (cropPatches.length === 0) return;
  await deleteCrop(cropPatches.length - 1);
}

async function clearCrops() {
  if (!confirm("Delete ALL saved crops?")) return;
  try {
    await api("/api/crops", { method: "DELETE" });
    toast("All crops cleared", "info");
    await loadCrops();
  } catch (e) {
    toast("Failed to clear: " + e.message, "error");
  }
}

// ---------------------------------------------------------------------------
// Generate crops / stitch export
// ---------------------------------------------------------------------------
async function makeCrops() {
  showLoading();
  try {
    await api("/api/make-crops", { method: "POST" });
    toast("All crops generated!", "success");
  } catch (e) {
    toast("Crop generation failed: " + e.message, "error", 5000);
  } finally {
    hideLoading();
  }
}

async function exportStitchHTML() {
  const payload = getStitchPayload();
  if (!payload.method_grid.length) {
    toast("请先填写有效的方法排列。", "error");
    return;
  }
  showLoading();
  try {
    const res = await fetch("/api/stitch-export-html", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      throw new Error(await res.text());
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "cherrypicker_stitch.html";
    a.click();
    URL.revokeObjectURL(url);
    toast("HTML 已导出", "success");
  } catch (e) {
    toast("导出 HTML 失败: " + e.message, "error", 5000);
  } finally {
    hideLoading();
  }
}

async function exportStitchPDF() {
  const payload = getStitchPayload();
  if (!payload.method_grid.length) {
    toast("请先填写有效的方法排列。", "error");
    return;
  }
  showLoading();
  try {
    const res = await fetch("/api/stitch-export-html", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text());
    const htmlText = await res.text();

    const win = window.open("", "_blank");
    if (!win) throw new Error("浏览器阻止了弹窗，请允许弹窗后重试。");
    win.document.open();
    win.document.write(htmlText);
    win.document.close();
    win.focus();
    setTimeout(() => win.print(), 500);
    toast("已打开打印窗口，请选择 Save as PDF", "info", 4500);
  } catch (e) {
    toast("导出 PDF 失败: " + e.message, "error", 5000);
  } finally {
    hideLoading();
  }
}

// ---------------------------------------------------------------------------
// Window resize → refit canvas
// ---------------------------------------------------------------------------
window.addEventListener("resize", () => {
  if (uiMode === "pick") {
    fitCanvas();
    drawCanvas();
    const cols = computeGridColumns();
    elDisplayGrid.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;
  } else {
    refreshStitchPreview();
  }
});

// ---------------------------------------------------------------------------
// Draggable splitter between center and right panels
// ---------------------------------------------------------------------------
(function initSplitter() {
  const splitter  = $("#splitter");
  const container = $("#main-container");
  const leftPanel = $("#left-panel");
  const rightPanel = $("#right-panel");
  let dragging = false;

  splitter.addEventListener("mousedown", (e) => {
    e.preventDefault();
    dragging = true;
    splitter.classList.add("active");
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  });

  document.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    const containerRect = container.getBoundingClientRect();
    const splitterW = 6;

    if (uiMode === "stitch") {
      const minLeft = 220;
      const minRight = 260;
      const maxLeft = Math.min(620, containerRect.width - minRight - splitterW);
      let newLeftW = e.clientX - containerRect.left - splitterW / 2;
      newLeftW = Math.max(minLeft, Math.min(newLeftW, maxLeft));
      leftPanel.style.width = `${newLeftW}px`;
      rightPanel.style.width = "";
      refreshStitchPreview();
      return;
    }

    const leftW = leftPanel.getBoundingClientRect().width;
    let newRightW = containerRect.right - e.clientX - splitterW / 2;
    const minRight = 200;
    const minCenter = 200;
    const maxRight = containerRect.width - leftW - splitterW - minCenter;
    newRightW = Math.max(minRight, Math.min(newRightW, maxRight));
    rightPanel.style.width = newRightW + "px";
    fitCanvas();
    drawCanvas();
    const cols = computeGridColumns();
    elDisplayGrid.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;
  });

  document.addEventListener("mouseup", () => {
    if (!dragging) return;
    dragging = false;
    splitter.classList.remove("active");
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
  });
})();

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------
init();
