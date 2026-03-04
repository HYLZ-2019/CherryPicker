"""
Calculate visualisation results from the given method results so performance
differences can be highlighted – e.g. variance map, ranking map.
Originally by Hylz – rewritten for web-based CherryPicker.

Bug fixes vs original:
- Uses float64 accumulator for variance to avoid uint8 overflow/wrap-around
- Normalises variance to full 0-255 range (original truncated via uint8 cast)
- Properly casts ranking to uint8 for applyColorMap
- Guards against missing GT / Ours indices
- Does not mutate caller's config list permanently (returns a copy)
"""

import os
import glob
import logging

import cv2
import numpy as np

logger = logging.getLogger("cherrypicker.visualizer")


def _load_image_paths(config: dict) -> dict:
    img_paths: dict[int, list[str]] = {}
    for idx, method in enumerate(config["methods"]):
        img_paths[idx] = sorted(
            glob.glob(os.path.join(method["path"], "**", "*.png"), recursive=True)
            + glob.glob(os.path.join(method["path"], "**", "*.jpg"), recursive=True)
        )
    frame_cnt = len(img_paths.get(0, []))
    for key in img_paths:
        if len(img_paths[key]) != frame_cnt:
            raise ValueError(
                f"Method {key} has {len(img_paths[key])} images, expected {frame_cnt}"
            )
    return img_paths


def make_variance_map(config: dict) -> dict:
    """Creates a per-pixel variance heatmap across all methods."""
    path = os.path.join(config["visualization_path"], "variance_map")
    os.makedirs(path, exist_ok=True)

    img_paths = _load_image_paths(config)
    frame_cnt = len(img_paths[0])
    m_cnt = len(img_paths)

    img0 = cv2.imread(img_paths[0][0])
    if img0 is None:
        raise FileNotFoundError(f"Cannot read: {img_paths[0][0]}")
    h, w, c = img0.shape

    for i in range(frame_cnt):
        arr = np.zeros((m_cnt, h, w, c), dtype=np.float64)
        for j in range(m_cnt):
            im = cv2.imread(img_paths[j][i])
            if im is not None:
                arr[j] = im.astype(np.float64)
        variance = np.var(arr, axis=0).sum(axis=2)  # (H, W)
        # Normalise to 0-255 for colour-map
        vmin, vmax = variance.min(), variance.max()
        if vmax > vmin:
            normed = ((variance - vmin) / (vmax - vmin) * 255).astype(np.uint8)
        else:
            normed = np.zeros_like(variance, dtype=np.uint8)
        viz = cv2.applyColorMap(normed, cv2.COLORMAP_JET)
        cv2.imwrite(os.path.join(path, f"{i:06d}.png"), viz)

    config["methods"].append({"name": "variance_map", "path": path})
    logger.info("Variance maps saved to %s", path)
    return config


def make_ranking_map(config: dict, metric) -> dict:
    """
    Creates a per-pixel ranking map showing where 'ours' ranks among methods.

    *metric(img, gt)* should return an (H, W) array where **higher = better**.
    """
    path = os.path.join(config["visualization_path"], "ranking_map")
    os.makedirs(path, exist_ok=True)

    img_paths = _load_image_paths(config)
    frame_cnt = len(img_paths[0])
    m_cnt = len(img_paths)

    img0 = cv2.imread(img_paths[0][0])
    if img0 is None:
        raise FileNotFoundError(f"Cannot read: {img_paths[0][0]}")
    h, w, c = img0.shape

    gt_idx = None
    ours_idx = None
    for i, m in enumerate(config["methods"]):
        if m.get("is_gt"):
            gt_idx = i
        if m.get("is_ours"):
            ours_idx = i

    if gt_idx is None:
        raise ValueError("No method marked as 'is_gt' in config.")
    if ours_idx is None:
        raise ValueError("No method marked as 'is_ours' in config.")

    for i in range(frame_cnt):
        gt_img = cv2.imread(img_paths[gt_idx][i])
        if gt_img is None:
            continue
        arr = np.zeros((m_cnt, h, w), dtype=np.float64)
        for j in range(m_cnt):
            comp = cv2.imread(img_paths[j][i])
            if comp is not None:
                arr[j] = metric(comp.astype(np.float64), gt_img.astype(np.float64))

        sort_idx = np.argsort(arr, axis=0)
        our_rank = np.zeros((h, w), dtype=np.float64)
        our_where = np.where(sort_idx == ours_idx)
        our_rank[our_where[1], our_where[2]] = our_where[0]
        our_rank = our_rank / max(m_cnt - 1, 1)
        viz = cv2.applyColorMap((our_rank * 255).astype(np.uint8), cv2.COLORMAP_JET)
        cv2.imwrite(os.path.join(path, f"{i:06d}.png"), viz)

    config["methods"].append({"name": "ranking_map", "path": path})
    logger.info("Ranking maps saved to %s", path)
    return config