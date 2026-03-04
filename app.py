"""
CherryPicker Web – FastAPI backend
Serves the single-page frontend and provides REST endpoints for
image browsing, crop-region management, image cropping, and PPT generation.
"""

import os
import sys
import glob
import yaml
import json
import shutil
import logging
import base64
import io
from datetime import datetime
from html import escape
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np
import webcolors
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from image_cropper import crop_images
from ppt_maker import make_ppt
from visualizer import make_variance_map, make_ranking_map

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
logger = logging.getLogger("cherrypicker")

# ---------------------------------------------------------------------------
# Load configuration
# ---------------------------------------------------------------------------
config_file = sys.argv[1] if len(sys.argv) > 1 else "configs.yaml"
with open(config_file, encoding="utf-8") as f:
    CONFIG: dict = yaml.safe_load(f)
logger.info("Loaded config from %s", config_file)

# ---------------------------------------------------------------------------
# Pre-compute image paths  (sorted deterministically)
# ---------------------------------------------------------------------------
IMG_PATHS: dict[int, list[str]] = {}
for idx, method in enumerate(CONFIG["methods"]):
    IMG_PATHS[idx] = sorted(
        glob.glob(os.path.join(method["path"], "**", "*.png"), recursive=True)
        + glob.glob(os.path.join(method["path"], "**", "*.jpg"), recursive=True)
        + glob.glob(os.path.join(method["path"], "**", "*.jpeg"), recursive=True)
        + glob.glob(os.path.join(method["path"], "**", "*.bmp"), recursive=True)
    )

FRAME_COUNT: int = len(IMG_PATHS.get(0, []))
METHOD_COUNT: int = len(CONFIG["methods"])
for idx in IMG_PATHS:
    if len(IMG_PATHS[idx]) != FRAME_COUNT:
        logger.warning(
            "Method %d (%s) has %d images, expected %d",
            idx, CONFIG["methods"][idx]["name"], len(IMG_PATHS[idx]), FRAME_COUNT,
        )

# ---------------------------------------------------------------------------
# In-memory crop list  (persisted to YAML on each change)
# ---------------------------------------------------------------------------
CROP_PATCHES: list[dict] = []
_info_path = CONFIG.get("output_info_path", "./cut_positions.txt")

def _load_crops():
    global CROP_PATCHES
    if os.path.exists(_info_path):
        with open(_info_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict):
            CROP_PATCHES = data.get("crop_patches", [])

def _save_crops():
    d = os.path.dirname(_info_path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)
    with open(_info_path, "w", encoding="utf-8") as f:
        yaml.dump({"crop_patches": CROP_PATCHES}, f, allow_unicode=True)

# Handle clear_previous on startup
if CONFIG.get("clear_previous", False):
    if os.path.exists(_info_path):
        os.remove(_info_path)
    crop_dir = CONFIG.get("output_crop_path", "crop_img")
    if os.path.isdir(crop_dir):
        shutil.rmtree(crop_dir)
    ppt_path = CONFIG.get("output_ppt_path", "output.pptx")
    if os.path.exists(ppt_path):
        os.remove(ppt_path)
    CROP_PATCHES = []
else:
    _load_crops()

# ---------------------------------------------------------------------------
# Optional visualisation on startup
# ---------------------------------------------------------------------------
if CONFIG.get("make_variance_map", False):
    CONFIG = make_variance_map(CONFIG)
    # Refresh IMG_PATHS for newly-added method
    new_idx = len(CONFIG["methods"]) - 1
    m = CONFIG["methods"][new_idx]
    IMG_PATHS[new_idx] = sorted(
        glob.glob(os.path.join(m["path"], "**", "*.png"), recursive=True)
        + glob.glob(os.path.join(m["path"], "**", "*.jpg"), recursive=True)
    )
    METHOD_COUNT = len(CONFIG["methods"])

if CONFIG.get("make_ranking_map", False):
    CONFIG = make_ranking_map(CONFIG, lambda x, y: -np.abs(x.astype(float) - y.astype(float)).sum(axis=2))
    new_idx = len(CONFIG["methods"]) - 1
    m = CONFIG["methods"][new_idx]
    IMG_PATHS[new_idx] = sorted(
        glob.glob(os.path.join(m["path"], "**", "*.png"), recursive=True)
        + glob.glob(os.path.join(m["path"], "**", "*.jpg"), recursive=True)
    )
    METHOD_COUNT = len(CONFIG["methods"])

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="CherryPicker")

# Serve static frontend assets
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ---- Frontend ----------------------------------------------------------
@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


# ---- API: config & metadata -------------------------------------------
class ConfigResponse(BaseModel):
    methods: list
    frame_count: int
    method_count: int
    display_rows: int
    display_cols: int

@app.get("/api/config")
def get_config():
    return {
        "methods": CONFIG["methods"],
        "frame_count": FRAME_COUNT,
        "method_count": METHOD_COUNT,
        "display_rows": CONFIG.get("display_rows", 2),
        "display_cols": CONFIG.get("display_cols", 2),
    }


# ---- API: serve images -------------------------------------------------
@app.get("/api/image/{method_idx}/{frame_idx}")
def get_image(method_idx: int, frame_idx: int):
    if method_idx < 0 or method_idx >= METHOD_COUNT:
        raise HTTPException(404, "Invalid method index")
    paths = IMG_PATHS.get(method_idx, [])
    if frame_idx < 0 or frame_idx >= len(paths):
        raise HTTPException(404, "Invalid frame index")
    p = paths[frame_idx]
    if not os.path.isfile(p):
        raise HTTPException(404, f"File not found: {p}")
    return FileResponse(p, media_type="image/png")


# ---- API: image dimensions (needed for accurate canvas sizing) ----------
@app.get("/api/image-size/{method_idx}/{frame_idx}")
def get_image_size(method_idx: int, frame_idx: int):
    if method_idx < 0 or method_idx >= METHOD_COUNT:
        raise HTTPException(404, "Invalid method index")
    paths = IMG_PATHS.get(method_idx, [])
    if frame_idx < 0 or frame_idx >= len(paths):
        raise HTTPException(404, "Invalid frame index")
    img = cv2.imread(paths[frame_idx])
    if img is None:
        raise HTTPException(500, "Cannot read image")
    h, w = img.shape[:2]
    return {"width": w, "height": h}


# ---- API: crop management -----------------------------------------------
class CropItem(BaseModel):
    img_idx: int
    crop_box: list  # [x1, y1, x2, y2]

@app.get("/api/crops")
def list_crops():
    return {"crop_patches": CROP_PATCHES}

@app.post("/api/crops")
def add_crop(item: CropItem):
    patch = {
        "img_idx": item.img_idx,
        "img_paths": [IMG_PATHS[m][item.img_idx] for m in range(METHOD_COUNT) if item.img_idx < len(IMG_PATHS.get(m, []))],
        "crop_box": item.crop_box,
    }
    CROP_PATCHES.append(patch)
    _save_crops()
    return {"ok": True, "total": len(CROP_PATCHES), "patch": patch}

@app.delete("/api/crops/{crop_idx}")
def delete_crop(crop_idx: int):
    if crop_idx < 0 or crop_idx >= len(CROP_PATCHES):
        raise HTTPException(404, "Invalid crop index")
    removed = CROP_PATCHES.pop(crop_idx)
    _save_crops()
    return {"ok": True, "removed": removed, "total": len(CROP_PATCHES)}

@app.delete("/api/crops")
def clear_crops():
    CROP_PATCHES.clear()
    _save_crops()
    return {"ok": True, "total": 0}


class StitchExportRequest(BaseModel):
    method_grid: List[List[int]]
    patches_per_example: int = 3
    example_limit: int = 0
    example_gap: int = 16
    patch_position: str = "bottom"  # bottom or right
    patch_border_colors: List[str] = ["red", "green", "blue"]
    patch_border_width: int = 2
    full_box_border_width: int = 2
    patch_big_gap: int = 8
    image_gap: int = 16
    font_family: str = "Arial, sans-serif"
    font_size: int = 16
    big_image_width: int = 220
    method_aliases: dict[str, str] = {}


class StitchConfigYamlRequest(BaseModel):
    yaml_text: str


def _method_name_index_maps():
    idx_to_name = [m["name"] for m in CONFIG["methods"]]
    name_to_idx = {name.lower(): i for i, name in enumerate(idx_to_name)}
    return idx_to_name, name_to_idx


def _normalize_stitch_payload(data: dict) -> dict:
    idx_to_name, _ = _method_name_index_maps()
    method_grid = data.get("method_grid", [])
    if not isinstance(method_grid, list) or len(method_grid) == 0:
        raise ValueError("method_grid 不能为空")

    normalized_grid: list[list[int]] = []
    for row in method_grid:
        if not isinstance(row, list) or len(row) == 0:
            raise ValueError("method_grid 中存在空行")
        nr: list[int] = []
        for item in row:
            try:
                idx = int(item)
            except Exception:
                raise ValueError(f"method_grid 包含非法方法索引: {item}")
            if idx < 0 or idx >= len(idx_to_name):
                raise ValueError(f"method_grid 包含越界方法索引: {idx}")
            nr.append(idx)
        normalized_grid.append(nr)

    aliases = data.get("method_aliases", {})
    if aliases is None:
        aliases = {}
    if not isinstance(aliases, dict):
        raise ValueError("method_aliases 必须是对象")
    for k, v in aliases.items():
        if k not in idx_to_name:
            raise ValueError(f"method_aliases 包含不存在的方法名: {k}")
        if not isinstance(v, str):
            raise ValueError(f"method_aliases 的值必须是字符串: {k}")

    out = {
        "method_grid": normalized_grid,
        "patches_per_example": max(1, int(data.get("patches_per_example", 3))),
        "example_limit": max(0, int(data.get("example_limit", 0))),
        "example_gap": max(0, int(data.get("example_gap", 16))),
        "patch_position": "right" if str(data.get("patch_position", "bottom")) == "right" else "bottom",
        "patch_border_colors": data.get("patch_border_colors", ["red", "green", "blue"]),
        "patch_border_width": max(0, int(data.get("patch_border_width", 2))),
        "full_box_border_width": max(0, int(data.get("full_box_border_width", 2))),
        "patch_big_gap": max(0, int(data.get("patch_big_gap", 8))),
        "image_gap": max(0, int(data.get("image_gap", 16))),
        "font_family": str(data.get("font_family", "Arial, sans-serif")),
        "font_size": max(8, int(data.get("font_size", 16))),
        "big_image_width": max(60, int(data.get("big_image_width", 220))),
        "method_aliases": aliases,
    }

    colors = out["patch_border_colors"]
    if not isinstance(colors, list) or len(colors) == 0:
        raise ValueError("patch_border_colors 必须是非空数组")
    out["patch_border_colors"] = [str(c).strip() for c in colors if str(c).strip()]
    if len(out["patch_border_colors"]) == 0:
        raise ValueError("patch_border_colors 不能为空")

    return out


def _yaml_to_payload(yaml_text: str) -> dict:
    idx_to_name, name_to_idx = _method_name_index_maps()
    try:
        data = yaml.safe_load(yaml_text)
    except Exception as e:
        raise ValueError(f"YAML 解析失败: {e}")
    if not isinstance(data, dict):
        raise ValueError("YAML 顶层必须是对象")

    layout = data.get("method_layout")
    if not isinstance(layout, list) or len(layout) == 0:
        raise ValueError("method_layout 必须是非空二维数组")

    method_grid: list[list[int]] = []
    for row in layout:
        if not isinstance(row, list) or len(row) == 0:
            raise ValueError("method_layout 中存在空行")
        grid_row: list[int] = []
        for method_name in row:
            if not isinstance(method_name, str):
                raise ValueError(f"method_layout 包含非字符串方法名: {method_name}")
            idx = name_to_idx.get(method_name.lower())
            if idx is None:
                raise ValueError(f"method_layout 包含不存在的方法名: {method_name}")
            grid_row.append(idx)
        method_grid.append(grid_row)

    payload = {
        "method_grid": method_grid,
        "patches_per_example": data.get("patches_per_example", 3),
        "example_limit": data.get("example_limit", 0),
        "example_gap": data.get("example_gap", 16),
        "patch_position": data.get("patch_position", "bottom"),
        "patch_border_colors": data.get("patch_border_colors", ["red", "green", "blue"]),
        "patch_border_width": data.get("patch_border_width", 2),
        "full_box_border_width": data.get("full_box_border_width", 2),
        "patch_big_gap": data.get("patch_big_gap", 8),
        "image_gap": data.get("image_gap", 16),
        "font_family": data.get("font_family", "Arial, sans-serif"),
        "font_size": data.get("font_size", 16),
        "big_image_width": data.get("big_image_width", 220),
        "method_aliases": data.get("method_aliases", {name: name for name in idx_to_name}),
    }
    return _normalize_stitch_payload(payload)


def _payload_to_yaml_dict(payload: dict) -> dict:
    idx_to_name, _ = _method_name_index_maps()
    method_layout = [[idx_to_name[i] for i in row] for row in payload["method_grid"]]
    return {
        "method_layout": method_layout,
        "patches_per_example": payload["patches_per_example"],
        "example_limit": payload["example_limit"],
        "example_gap": payload["example_gap"],
        "patch_position": payload["patch_position"],
        "patch_border_colors": payload["patch_border_colors"],
        "patch_border_width": payload["patch_border_width"],
        "full_box_border_width": payload["full_box_border_width"],
        "patch_big_gap": payload["patch_big_gap"],
        "image_gap": payload["image_gap"],
        "font_family": payload["font_family"],
        "font_size": payload["font_size"],
        "big_image_width": payload["big_image_width"],
        "method_aliases": payload["method_aliases"],
    }


def _stack_h(images: list[np.ndarray], gap: int) -> np.ndarray:
    if not images:
        return np.zeros((1, 1, 3), dtype=np.uint8)
    max_h = max(img.shape[0] for img in images)
    total_w = sum(img.shape[1] for img in images) + gap * max(0, len(images) - 1)
    canvas = np.full((max_h, total_w, 3), 255, dtype=np.uint8)
    x = 0
    for img in images:
        h, w = img.shape[:2]
        canvas[0:h, x:x + w] = img
        x += w + gap
    return canvas


def _stack_v(images: list[np.ndarray], gap: int) -> np.ndarray:
    if not images:
        return np.zeros((1, 1, 3), dtype=np.uint8)
    max_w = max(img.shape[1] for img in images)
    total_h = sum(img.shape[0] for img in images) + gap * max(0, len(images) - 1)
    canvas = np.full((total_h, max_w, 3), 255, dtype=np.uint8)
    y = 0
    for img in images:
        h, w = img.shape[:2]
        canvas[y:y + h, 0:w] = img
        y += h + gap
    return canvas


def _add_border(img: np.ndarray, bgr: tuple[int, int, int], width: int) -> np.ndarray:
    if width <= 0:
        return img.copy()
    return cv2.copyMakeBorder(img, width, width, width, width, cv2.BORDER_CONSTANT, value=bgr)


def _draw_boxes(img: np.ndarray, boxes: list[list[int]], colors: list[str], width: int) -> np.ndarray:
    out = img.copy()
    if width <= 0:
        return out
    h, w = out.shape[:2]
    for i, box in enumerate(boxes):
        if not isinstance(box, list) or len(box) != 4:
            continue
        x1, y1, x2, y2 = box
        x1c = max(0, min(int(x1), w - 1))
        y1c = max(0, min(int(y1), h - 1))
        x2c = max(x1c + 1, min(int(x2), w))
        y2c = max(y1c + 1, min(int(y2), h))
        bgr = _parse_color_bgr(colors[i % len(colors)])
        cv2.rectangle(out, (x1c, y1c), (x2c, y2c), bgr, width)
    return out


_PDF_FONT_CACHE: dict[str, str] = {}


def _register_pdf_font(font_family_css: str) -> str:
    if not font_family_css:
        return "Helvetica"

    windir = os.environ.get("WINDIR", r"C:\\Windows")
    font_dir = os.path.join(windir, "Fonts")

    def _clean_token(token: str) -> str:
        return token.strip().strip("\"'").lower()

    def _try_register(font_path: str) -> Optional[str]:
        key = os.path.abspath(font_path)
        if key in _PDF_FONT_CACHE:
            return _PDF_FONT_CACHE[key]
        if not os.path.isfile(font_path):
            return None
        font_name = f"CPFont_{len(_PDF_FONT_CACHE) + 1}"
        try:
            pdfmetrics.registerFont(TTFont(font_name, font_path))
            _PDF_FONT_CACHE[key] = font_name
            return font_name
        except Exception:
            return None

    token_to_candidates: dict[str, list[str]] = {
        "arial": ["arial.ttf", "arialuni.ttf"],
        "helvetica": ["arial.ttf"],
        "sans-serif": ["arial.ttf", "segoeui.ttf", "calibri.ttf"],
        "segoe ui": ["segoeui.ttf"],
        "calibri": ["calibri.ttf"],
        "times new roman": ["times.ttf"],
        "times": ["times.ttf"],
        "serif": ["times.ttf", "georgia.ttf"],
        "courier new": ["cour.ttf", "consola.ttf"],
        "consolas": ["consola.ttf"],
        "monospace": ["consola.ttf", "cour.ttf"],
        "microsoft yahei": ["msyh.ttf", "msyh.ttc"],
        "微软雅黑": ["msyh.ttf", "msyh.ttc"],
        "simhei": ["simhei.ttf"],
        "黑体": ["simhei.ttf"],
        "simsun": ["simsun.ttc"],
        "宋体": ["simsun.ttc"],
    }

    tokens = [_clean_token(t) for t in str(font_family_css).split(",") if _clean_token(t)]
    for token in tokens:
        if token.endswith((".ttf", ".otf", ".ttc")):
            direct = token
            if not os.path.isabs(direct):
                direct = os.path.join(font_dir, token)
            name = _try_register(direct)
            if name:
                return name

        candidates = token_to_candidates.get(token, [])
        for filename in candidates:
            path = os.path.join(font_dir, filename)
            name = _try_register(path)
            if name:
                return name

    return "Helvetica"


def _pdf_string_width(text: str, font_name: str, font_size: float) -> float:
    try:
        return float(pdfmetrics.stringWidth(text, font_name, font_size))
    except Exception:
        return float(len(text) * font_size * 0.5)


def _layout_h(images: list[np.ndarray], gap: int) -> tuple[np.ndarray, list[int]]:
    if not images:
        return np.zeros((1, 1, 3), dtype=np.uint8), []
    max_h = max(img.shape[0] for img in images)
    total_w = sum(img.shape[1] for img in images) + gap * max(0, len(images) - 1)
    canvas = np.full((max_h, total_w, 3), 255, dtype=np.uint8)
    starts: list[int] = []
    x = 0
    for img in images:
        h, w = img.shape[:2]
        canvas[0:h, x:x + w] = img
        starts.append(x)
        x += w + gap
    return canvas, starts


def _layout_v(images: list[np.ndarray], gap: int) -> tuple[np.ndarray, list[int]]:
    if not images:
        return np.zeros((1, 1, 3), dtype=np.uint8), []
    max_w = max(img.shape[1] for img in images)
    total_h = sum(img.shape[0] for img in images) + gap * max(0, len(images) - 1)
    canvas = np.full((total_h, max_w, 3), 255, dtype=np.uint8)
    starts: list[int] = []
    y = 0
    for img in images:
        h, w = img.shape[:2]
        canvas[y:y + h, 0:w] = img
        starts.append(y)
        y += h + gap
    return canvas, starts


def _build_method_content_and_scale(
    frame_idx: int,
    method_idx: int,
    boxes: list[list[int]],
    payload: dict,
    target_content_width: Optional[int] = None,
) -> Optional[tuple[np.ndarray, float]]:
    paths = IMG_PATHS.get(method_idx, [])
    if frame_idx < 0 or frame_idx >= len(paths):
        return None
    full = cv2.imread(paths[frame_idx])
    if full is None:
        return None

    colors = payload["patch_border_colors"]
    patch_cnt = min(max(1, payload["patches_per_example"]), len(boxes))
    use_boxes = boxes[:patch_cnt]
    h, w = full.shape[:2]

    preview_big_w = max(1, int(payload.get("big_image_width", 220)))
    scale_ratio = max(1e-6, w / float(preview_big_w))

    full_marked = _draw_boxes(full, use_boxes, colors, payload["full_box_border_width"])

    raw_patches: list[np.ndarray] = []
    for box in use_boxes:
        x1, y1, x2, y2 = box
        x1c = max(0, min(int(x1), w - 1))
        y1c = max(0, min(int(y1), h - 1))
        x2c = max(x1c + 1, min(int(x2), w))
        y2c = max(y1c + 1, min(int(y2), h))
        patch = full[y1c:y2c, x1c:x2c]
        raw_patches.append(patch)

    patch_inner_gap = max(0, int(round((payload["patch_big_gap"] // 2) * scale_ratio)))
    patch_outer_gap = max(0, int(round(payload["patch_big_gap"] * scale_ratio)))
    patch_border_w = max(0, int(payload.get("patch_border_width", 0)))
    patches: list[np.ndarray] = []

    if raw_patches:
        gap_total = patch_inner_gap * max(0, patch_cnt - 1)
        if payload["patch_position"] == "right":
            axis_limit = h
        else:
            axis_limit = w

        patch_axis_total = max(patch_cnt, axis_limit - gap_total)

        patch_axis_base = patch_axis_total // patch_cnt
        patch_axis_remain = patch_axis_total

        for i, patch in enumerate(raw_patches):
            ph, pw = patch.shape[:2]
            axis_size = patch_axis_remain if i == patch_cnt - 1 else patch_axis_base
            patch_axis_remain -= axis_size

            if payload["patch_position"] == "right":
                target_h = max(1, int(axis_size))
                target_w = max(1, int(round(pw * target_h / max(ph, 1))))
            else:
                target_w = max(1, int(axis_size))
                target_h = max(1, int(round(ph * target_w / max(pw, 1))))

            interp = cv2.INTER_CUBIC if (target_w > pw or target_h > ph) else cv2.INTER_AREA
            patch_resized = cv2.resize(patch, (target_w, target_h), interpolation=interp)

            bgr = _parse_color_bgr(colors[i % len(colors)])
            patches.append(_add_border(patch_resized, bgr, patch_border_w))

    patch_strip = None
    if patches:
        if payload["patch_position"] == "right":
            patch_strip = _stack_v(patches, patch_inner_gap)
            if patch_strip.shape[0] > full_marked.shape[0] and patch_strip.shape[1] > 0:
                ratio = full_marked.shape[0] / float(max(1, patch_strip.shape[0]))
                dst_w = max(1, int(round(patch_strip.shape[1] * ratio)))
                patch_strip = cv2.resize(patch_strip, (dst_w, full_marked.shape[0]), interpolation=cv2.INTER_AREA)
        else:
            patch_strip = _stack_h(patches, patch_inner_gap)
            if patch_strip.shape[1] > full_marked.shape[1] and patch_strip.shape[0] > 0:
                ratio = full_marked.shape[1] / float(max(1, patch_strip.shape[1]))
                dst_h = max(1, int(round(patch_strip.shape[0] * ratio)))
                patch_strip = cv2.resize(patch_strip, (full_marked.shape[1], dst_h), interpolation=cv2.INTER_AREA)

    if patch_strip is None:
        content = full_marked
    elif payload["patch_position"] == "right":
        content = _stack_h([full_marked, patch_strip], patch_outer_gap)
    else:
        content = _stack_v([full_marked, patch_strip], patch_outer_gap)

    if target_content_width is not None and target_content_width > 0 and content.shape[1] > 0:
        src_w = int(content.shape[1])
        dst_w = int(target_content_width)
        if src_w != dst_w:
            resize_ratio = dst_w / float(src_w)
            dst_h = max(1, int(round(content.shape[0] * resize_ratio)))
            interp = cv2.INTER_CUBIC if resize_ratio > 1.0 else cv2.INTER_AREA
            content = cv2.resize(content, (dst_w, dst_h), interpolation=interp)
            scale_ratio *= resize_ratio

    return content, scale_ratio


def _method_block_original_res(
    frame_idx: int,
    method_idx: int,
    boxes: list[list[int]],
    payload: dict,
    label_tag: str,
    label_text: str,
) -> Optional[np.ndarray]:
    built = _build_method_content_and_scale(frame_idx, method_idx, boxes, payload)
    if built is None:
        return None
    content, scale_ratio = built

    text = f"({label_tag}) {label_text}"
    scaled_font_px = payload["font_size"] * scale_ratio
    scale = max(0.5, scaled_font_px / 24.0)
    thickness = max(1, int(round(scale * 2)))
    (tw, th), bl = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thickness)
    label_pad = max(4, int(round(8 * scale_ratio)))
    label_h = th + bl + label_pad
    block = np.full((content.shape[0] + label_h, content.shape[1], 3), 255, dtype=np.uint8)
    block[:content.shape[0], :content.shape[1]] = content
    tx = max(0, (content.shape[1] - tw) // 2)
    ty = content.shape[0] + th + max(1, label_pad // 4)
    cv2.putText(block, text, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thickness, cv2.LINE_AA)
    return block


def _build_lossless_pdf_bytes(req: StitchExportRequest) -> bytes:
    payload = _normalize_stitch_payload(req.model_dump())
    if not CROP_PATCHES:
        raise ValueError("No saved crops. Please save crops first.")

    grouped: dict[int, list[list[int]]] = {}
    for p in CROP_PATCHES:
        grouped.setdefault(p["img_idx"], []).append(p["crop_box"])

    frame_indices = sorted(grouped.keys())
    if payload["example_limit"] > 0:
        frame_indices = frame_indices[: payload["example_limit"]]
    if not frame_indices:
        raise ValueError("No valid examples to export")

    idx_to_name, _ = _method_name_index_maps()
    alias_map = payload.get("method_aliases", {})
    flat_order = [m for row in payload["method_grid"] for m in row]
    font_name = _register_pdf_font(payload.get("font_family", ""))

    pdf_buf = io.BytesIO()
    pdf = pdf_canvas.Canvas(pdf_buf)
    target_width_by_slot: dict[int, int] = {}

    for frame_order, frame_idx in enumerate(frame_indices):
        boxes = grouped.get(frame_idx, [])
        row_imgs: list[np.ndarray] = []
        row_starts: list[int] = []
        page_labels: list[dict] = []
        slot_idx = 0

        for row in payload["method_grid"]:
            method_contents: list[np.ndarray] = []
            method_texts: list[str] = []
            method_fonts: list[float] = []
            for m_idx in row:
                method_name = idx_to_name[m_idx]
                alias = alias_map.get(method_name, method_name)
                order_idx = flat_order.index(m_idx) if m_idx in flat_order else 0
                tag = _index_to_alpha_tag(order_idx)
                target_w = target_width_by_slot.get(slot_idx)
                built = _build_method_content_and_scale(
                    frame_idx,
                    m_idx,
                    boxes,
                    payload,
                    target_content_width=target_w,
                )
                slot_idx += 1
                if built is None:
                    continue
                content, scale_ratio = built
                if frame_order == 0 and target_w is None:
                    target_width_by_slot[slot_idx - 1] = int(content.shape[1])
                method_contents.append(content)
                method_texts.append(f"({tag}) {alias}")
                method_fonts.append(max(1.0, float(payload["font_size"]) * float(scale_ratio)))

            if not method_contents:
                continue

            row_content, starts = _layout_h(method_contents, payload["image_gap"])
            row_h, row_w = row_content.shape[:2]
            row_label_h = max(8, int(round(max(method_fonts) * 1.4)))
            row_img = np.full((row_h + row_label_h, row_w, 3), 255, dtype=np.uint8)
            row_img[:row_h, :row_w] = row_content

            row_top_in_page = 0
            if row_imgs:
                row_top_in_page = sum(img.shape[0] for img in row_imgs) + payload["image_gap"] * len(row_imgs)
            row_starts.append(row_top_in_page)
            row_imgs.append(row_img)

            for idx, x0 in enumerate(starts):
                page_labels.append({
                    "text": method_texts[idx],
                    "font_size": method_fonts[idx],
                    "method_x": x0,
                    "method_w": int(method_contents[idx].shape[1]),
                    "row_top": row_top_in_page,
                    "row_content_h": row_h,
                    "row_label_h": row_label_h,
                })

        if not row_imgs:
            continue

        page_img, _ = _layout_v(row_imgs, payload["image_gap"])
        h, w = page_img.shape[:2]
        ok, png_buf = cv2.imencode(".png", page_img)
        if not ok:
            raise ValueError("PNG encoding failed for PDF page")

        pdf.setPageSize((w, h))
        pdf.drawImage(ImageReader(io.BytesIO(png_buf.tobytes())), 0, 0, width=w, height=h, mask="auto")

        for item in page_labels:
            text = str(item["text"])
            font_size = float(item["font_size"])
            method_x = float(item["method_x"])
            method_w = float(item["method_w"])
            row_top = float(item["row_top"])
            row_content_h = float(item["row_content_h"])
            row_label_h = float(item["row_label_h"])

            text_w = _pdf_string_width(text, font_name, font_size)
            text_x = method_x + max(0.0, (method_w - text_w) / 2.0)
            baseline_top = row_top + row_content_h + row_label_h * 0.72
            text_y = h - baseline_top

            pdf.setFillColorRGB(0, 0, 0)
            pdf.setFont(font_name, font_size)
            pdf.drawString(text_x, text_y, text)

        pdf.showPage()

    pdf.save()
    return pdf_buf.getvalue()


@app.post("/api/stitch-config/export-yaml")
def export_stitch_config_yaml(req: StitchExportRequest):
    try:
        payload = _normalize_stitch_payload(req.model_dump())
        yaml_dict = _payload_to_yaml_dict(payload)
        yaml_text = yaml.safe_dump(yaml_dict, allow_unicode=True, sort_keys=False)
        headers = {"Content-Disposition": "attachment; filename=cherrypicker_stitch_config.yaml"}
        return Response(content=yaml_text, media_type="text/yaml; charset=utf-8", headers=headers)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/stitch-config/import-yaml")
def import_stitch_config_yaml(req: StitchConfigYamlRequest):
    try:
        payload = _yaml_to_payload(req.yaml_text)
        idx_to_name, _ = _method_name_index_maps()
        method_layout = [[idx_to_name[i] for i in row] for row in payload["method_grid"]]
        return {"ok": True, "payload": payload, "method_layout": method_layout}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/stitch-export-pdf-lossless")
def stitch_export_pdf_lossless(req: StitchExportRequest):
    try:
        pdf_bytes = _build_lossless_pdf_bytes(req)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        headers = {"Content-Disposition": f'attachment; filename="cherrypicker_stitch_lossless_{ts}.pdf"'}
        return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.exception("stitch-export-pdf-lossless failed")
        raise HTTPException(500, str(e))


def _img_to_data_url(img: np.ndarray) -> str:
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise ValueError("Image encoding failed")
    b64 = base64.b64encode(buf.tobytes()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _parse_color_bgr(color_name: str) -> tuple[int, int, int]:
    try:
        rgb = webcolors.name_to_rgb(color_name)
        return (int(rgb.blue), int(rgb.green), int(rgb.red))
    except Exception:
        return (0, 0, 255)


def _index_to_alpha_tag(idx: int) -> str:
    n = idx
    out = ""
    while n >= 0:
        out = chr(97 + (n % 26)) + out
        n = n // 26 - 1
    return out


def _build_stitch_html(req: StitchExportRequest) -> str:
    payload = _normalize_stitch_payload(req.model_dump())
    if not CROP_PATCHES:
        raise ValueError("No saved crops. Please save crops first.")
    if not payload["method_grid"]:
        raise ValueError("method_grid is empty")

    grouped: dict[int, list[list[int]]] = {}
    for p in CROP_PATCHES:
        grouped.setdefault(p["img_idx"], []).append(p["crop_box"])
    frame_indices = sorted(grouped.keys())
    if payload["example_limit"] > 0:
        frame_indices = frame_indices[: payload["example_limit"]]

    image_gap = max(0, payload["image_gap"])
    example_gap = max(0, payload["example_gap"])
    font_size = max(8, payload["font_size"])
    alias_map = payload.get("method_aliases", {})
    idx_to_name, _ = _method_name_index_maps()
    flat_method_order = [m for row in payload["method_grid"] for m in row]

    html_parts = []
    html_parts.append("<!DOCTYPE html><html><head><meta charset='UTF-8' />")
    html_parts.append("<meta name='viewport' content='width=device-width, initial-scale=1.0' />")
    html_parts.append("<title>CherryPicker Stitch Export</title>")
    html_parts.append("<style>")
    html_parts.append(
        "body{margin:0;padding:18px;background:#fff;color:#111;}"
        f".root{{display:flex;flex-direction:column;gap:{example_gap}px;}}"
        ".example{padding:0;overflow-x:auto;}"
        ".st-row{display:flex;flex-wrap:nowrap;align-items:flex-start;width:max-content;margin-bottom:10px;}"
        ".method{display:flex;flex-direction:column;align-items:center;width:max-content;}"
        ".method-img{display:block;height:auto;}"
        ".method-label{font-weight:600;margin-top:6px;text-align:center;}"
        "@media print{body{padding:8px;} .example{break-inside:avoid;}}"
    )
    html_parts.append("</style></head><body>")
    html_parts.append(
        f"<div class='root' style='font-family:{escape(payload['font_family'])};font-size:{font_size}px;'>"
    )

    target_width_by_slot: dict[int, int] = {}
    for frame_order, frame_idx in enumerate(frame_indices):
        boxes = grouped[frame_idx]
        html_parts.append("<div class='example'>")
        slot_idx = 0

        for row in payload["method_grid"]:
            html_parts.append(f"<div class='st-row' style='gap:{image_gap}px;'>")
            for m_idx in row:
                method_name = idx_to_name[m_idx]
                alias_name = alias_map.get(method_name, method_name)
                label_index = max(0, flat_method_order.index(m_idx)) if flat_method_order else 0
                label_tag = _index_to_alpha_tag(label_index)

                target_w = target_width_by_slot.get(slot_idx)
                built = _build_method_content_and_scale(
                    frame_idx,
                    m_idx,
                    boxes,
                    payload,
                    target_content_width=target_w,
                )
                slot_idx += 1
                if built is None:
                    continue

                content, scale_ratio = built
                if frame_order == 0 and target_w is None:
                    target_width_by_slot[slot_idx - 1] = int(content.shape[1])

                content_url = _img_to_data_url(content)
                label_px = max(8, int(round(font_size * scale_ratio)))

                html_parts.append("<div class='method'>")
                html_parts.append(
                    f"<img class='method-img' src='{content_url}' alt='method-content' style='width:{int(content.shape[1])}px;' />"
                )
                html_parts.append(
                    f"<div class='method-label' style='font-size:{label_px}px;'>({label_tag}) {escape(alias_name)}</div>"
                )
                html_parts.append("</div>")

            html_parts.append("</div>")

        html_parts.append("</div>")

    html_parts.append("</div></body></html>")
    return "".join(html_parts)


@app.post("/api/stitch-export-html")
def stitch_export_html(req: StitchExportRequest):
    try:
        html_text = _build_stitch_html(req)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"cherrypicker_stitch_{ts}.html"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return Response(content=html_text, media_type="text/html; charset=utf-8", headers=headers)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.exception("stitch-export-html failed")
        raise HTTPException(500, str(e))


@app.post("/api/stitch-export-html/")
def stitch_export_html_trailing(req: StitchExportRequest):
    return stitch_export_html(req)


@app.get("/api/image-boxed/{method_idx}/{frame_idx}")
def image_boxed(
    method_idx: int,
    frame_idx: int,
    boxes_json: str = Query("[]"),
    colors: str = Query(""),
    border_width: int = Query(2),
):
    if method_idx < 0 or method_idx >= METHOD_COUNT:
        raise HTTPException(404, "Invalid method index")
    paths = IMG_PATHS.get(method_idx, [])
    if frame_idx < 0 or frame_idx >= len(paths):
        raise HTTPException(404, "Invalid frame index")

    img = cv2.imread(paths[frame_idx])
    if img is None:
        raise HTTPException(500, "Cannot read image")

    try:
        parsed_boxes = json.loads(boxes_json)
        if not isinstance(parsed_boxes, list):
            parsed_boxes = []
    except Exception:
        parsed_boxes = []

    color_names = [x.strip() for x in colors.split(",") if x.strip()]
    if not color_names:
        color_names = ["red"]

    h, w = img.shape[:2]
    bw = max(0, int(border_width))
    for i, box in enumerate(parsed_boxes):
        if not isinstance(box, list) or len(box) != 4:
            continue
        x1, y1, x2, y2 = box
        x1c = max(0, min(int(x1), w - 1))
        y1c = max(0, min(int(y1), h - 1))
        x2c = max(x1c + 1, min(int(x2), w))
        y2c = max(y1c + 1, min(int(y2), h))
        bgr = _parse_color_bgr(color_names[i % len(color_names)])
        if bw > 0:
            cv2.rectangle(img, (x1c, y1c), (x2c, y2c), bgr, bw)

    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise HTTPException(500, "Encoding failed")
    return Response(content=buf.tobytes(), media_type="image/png")


# ---- API: generate cropped images & PPT ---------------------------------
@app.post("/api/make-crops")
def api_make_crops():
    try:
        crop_images(CONFIG)
        return {"ok": True}
    except Exception as e:
        logger.exception("make-crops failed")
        raise HTTPException(500, str(e))

@app.post("/api/make-ppt")
def api_make_ppt():
    try:
        make_ppt(CONFIG)
        ppt_path = CONFIG.get("output_ppt_path", "output.pptx")
        return {"ok": True, "path": ppt_path}
    except Exception as e:
        logger.exception("make-ppt failed")
        raise HTTPException(500, str(e))

@app.get("/api/download-ppt")
def download_ppt():
    ppt_path = CONFIG.get("output_ppt_path", "output.pptx")
    if not os.path.isfile(ppt_path):
        raise HTTPException(404, "PPT not yet generated")
    return FileResponse(ppt_path, filename=os.path.basename(ppt_path),
                        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation")


# ---- API: serve a cropped patch preview on-the-fly ----------------------
@app.get("/api/crop-preview/{method_idx}/{frame_idx}")
def crop_preview(method_idx: int, frame_idx: int,
                 x1: int = Query(...), y1: int = Query(...),
                 x2: int = Query(...), y2: int = Query(...)):
    """Return a cropped region of an image as PNG (for live preview)."""
    if method_idx < 0 or method_idx >= METHOD_COUNT:
        raise HTTPException(404, "Invalid method index")
    paths = IMG_PATHS.get(method_idx, [])
    if frame_idx < 0 or frame_idx >= len(paths):
        raise HTTPException(404, "Invalid frame index")
    img = cv2.imread(paths[frame_idx])
    if img is None:
        raise HTTPException(500, "Cannot read image")
    h, w = img.shape[:2]
    x1c, y1c = max(0, x1), max(0, y1)
    x2c, y2c = min(w, x2), min(h, y2)
    if x2c <= x1c or y2c <= y1c:
        raise HTTPException(400, "Invalid crop region")
    patch = img[y1c:y2c, x1c:x2c]
    # Encode to PNG in memory and return directly
    ok, buf = cv2.imencode(".png", patch)
    if not ok:
        raise HTTPException(500, "Encoding failed")
    return Response(content=buf.tobytes(), media_type="image/png")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8765))
    logger.info("Starting CherryPicker on http://localhost:%d", port)
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        timeout_keep_alive=1,
        timeout_graceful_shutdown=2,
    )
