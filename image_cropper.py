"""
Crop selected areas of images based on saved crop information.
Rewritten for the web-based CherryPicker.

Bug fixes vs original:
- Proper error handling for missing images
- Safe colour parsing with fallback
- Avoid zero-area crop boxes
- Guard against empty or missing crop_info file
- shutil.rmtree only when directory exists
- Clamp crop coordinates to image bounds
"""

import os
import shutil
import logging

import cv2
import yaml

logger = logging.getLogger("cherrypicker.cropper")


def _parse_colour_bgr(name: str):
    """Convert a CSS colour name to BGR tuple. Falls back to red."""
    try:
        import webcolors
        rgb = webcolors.name_to_rgb(name)
        return (rgb.blue, rgb.green, rgb.red)
    except Exception:
        return (0, 0, 255)


def crop_images(configs: dict) -> None:
    crop_info_file = configs["output_info_path"]
    if not os.path.isfile(crop_info_file):
        logger.warning("Crop info file not found: %s – nothing to do.", crop_info_file)
        return

    with open(crop_info_file, "r", encoding="utf-8") as fd:
        crop_info = yaml.safe_load(fd)

    if not isinstance(crop_info, dict):
        logger.warning("Crop info file is empty or malformed.")
        return

    method_names = [m["name"] for m in configs["methods"]]
    method_cnt = len(method_names)

    patches = crop_info.get("crop_patches", [])
    if not patches:
        logger.info("No crop patches found.")
        return

    # Group patches by image index
    crop_dict: dict = {}
    for patch in patches:
        idx = patch["img_idx"]
        if idx not in crop_dict:
            crop_dict[idx] = {"patches": [], "img_paths": patch["img_paths"]}
        crop_dict[idx]["patches"].append(patch["crop_box"])

    crop_colors = configs.get(
        "crop_box_colors",
        ["red", "green", "blue", "yellow", "cyan", "magenta", "white", "black"],
    )
    logger.info("Using crop box colours: %s", crop_colors)

    out_dir = configs["output_crop_path"]
    clear_previous = configs.get("clear_previous", False)
    if clear_previous and os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    pbw = configs.get("patch_border_width", 2)
    bbw = configs.get("box_border_width", 2)

    for img_idx, info in crop_dict.items():
        crop_boxes = sorted(info["patches"], key=lambda b: b[0])
        img_paths = info["img_paths"]

        for m in range(min(method_cnt, len(img_paths))):
            image = cv2.imread(img_paths[m])
            if image is None:
                logger.warning("Cannot read image: %s", img_paths[m])
                continue

            h_img, w_img = image.shape[:2]

            for i, box in enumerate(crop_boxes):
                x1, y1, x2, y2 = box
                # Clamp to image bounds
                x1 = max(0, min(x1, w_img))
                y1 = max(0, min(y1, h_img))
                x2 = max(x1 + 1, min(x2, w_img))
                y2 = max(y1 + 1, min(y2, h_img))

                color = _parse_colour_bgr(crop_colors[i % len(crop_colors)])
                crop_img = image[y1:y2, x1:x2].copy()

                if pbw > 0:
                    crop_img = cv2.copyMakeBorder(
                        crop_img, pbw, pbw, pbw, pbw,
                        cv2.BORDER_CONSTANT, value=color,
                    )

                out_path = os.path.join(
                    out_dir, method_names[m],
                    f"img{img_idx:06d}_crop{i:02d}_{method_names[m]}.png",
                )
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                cv2.imwrite(out_path, crop_img)

                if bbw > 0:
                    cv2.rectangle(image, (x1, y1), (x2, y2), color, bbw)

            full_path = os.path.join(
                out_dir, method_names[m],
                f"img{img_idx:06d}_full_{method_names[m]}.png",
            )
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            cv2.imwrite(full_path, image)

    logger.info("Crop images generated in %s", out_dir)