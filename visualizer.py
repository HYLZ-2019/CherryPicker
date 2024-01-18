# Calculate some visualization results from the given results, so performance can be highlighted.
# For example, variance map, ranking map, etc.
# Made by Hylz.

import os
import glob
import cv2
import numpy as np

def load_image_paths(config):
    img_paths = {}
    for idx, method in enumerate(config["methods"]):
        img_paths[idx] = sorted(
            glob.glob(os.path.join(method["path"], "**.png"))
            + glob.glob(os.path.join(method["path"], "**.jpg"))
        )
    frame_cnt = len(img_paths[0])
    for key in img_paths:
        assert len(img_paths[key]) == frame_cnt
    return img_paths

def make_variance_map(config):
    path = os.path.join(config["visualization_path"], "variance_map")
    if not os.path.exists(path):
        os.makedirs(path)

    img_paths = load_image_paths(config)
    frame_cnt = len(img_paths[0])
    img0 = cv2.imread(img_paths[0][0])
    h, w, c = img0.shape
    m_cnt = len(img_paths)
    
    for i in range(frame_cnt):
        arr = np.zeros((m_cnt, h, w, c))
        for j in range(m_cnt):
            arr[j] = cv2.imread(img_paths[j][i])
        variance = np.var(arr, axis=0).sum(axis=2)
        viz = cv2.applyColorMap(variance.astype(np.uint8), cv2.COLORMAP_JET)
        cv2.imwrite(os.path.join(path, f"{i:06d}.png"), viz)
    
    config["methods"].append({"name": "variance_map", "path": path})
    return config

def make_ranking_map(config, metric):
    path = os.path.join(config["visualization_path"], "ranking_map")
    if not os.path.exists(path):
        os.makedirs(path)
    img_paths = load_image_paths(config)
    frame_cnt = len(img_paths[0])
    img0 = cv2.imread(img_paths[0][0])
    h, w, c = img0.shape
    m_cnt = len(img_paths)

    gt = None
    ours = None
    for i in range(m_cnt):
        if config["methods"][i].get("is_gt", False) == True:
            gt = i
        if config["methods"][i].get("is_ours", False) == True:
            ours = i

    for i in range(frame_cnt):
        gt_img = cv2.imread(img_paths[gt][i])
        arr = np.zeros((m_cnt, h, w))
        for j in range(m_cnt):
            comp = cv2.imread(img_paths[j][i])
            arr[j] = metric(comp, gt_img)
        sort_idx = np.argsort(arr, axis=0)
        # sort_idx[r, i, j] is the index of the r-th largest value in arr[:, i, j]
        our_where = np.where(sort_idx == ours)
        our_rank = np.zeros((h, w))
        our_rank[our_where[1], our_where[2]] = our_where[0]
        our_rank = our_rank / (m_cnt - 1)
        viz = cv2.applyColorMap((our_rank*255).astype(np.uint8), cv2.COLORMAP_JET)
        cv2.imwrite(os.path.join(path, f"{i:06d}.png"), viz)
    
    config["methods"].append({"name": "ranking_map", "path": path})
    return config