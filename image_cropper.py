# Crop selected areas of images.

import os
import cv2
import yaml
import webcolors
import shutil

def crop_images(configs):
    crop_info_file = configs["output_info_path"]
    with open(crop_info_file, 'r') as fd:
        crop_info = yaml.load(fd, Loader=yaml.FullLoader)

    method_names = [m["name"] for m in configs["methods"]]
    method_cnt = len(method_names)

    crop_dict = {}

    patches = crop_info.get("crop_patches", [])
    for patch in patches:
        if patch["img_idx"] not in crop_dict:
            crop_dict[patch["img_idx"]] = {
                "patches": [],
                "img_paths": patch["img_paths"]
            }
        crop_dict[patch["img_idx"]]["patches"].append(patch["crop_box"])

    crop_colors = configs.get("crop_box_colors", ["red", "green", "blue", "yellow", "cyan", "magenta", "white", "black"])
    print(f"Using crop box colors: {crop_colors}")

    out_dir = configs["output_crop_path"]
    clear_previous = configs.get("clear_previous", False)
    if clear_previous:
        shutil.rmtree(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    for img_idx in crop_dict:
        crop_boxes = crop_dict[img_idx]["patches"]
        crop_boxes.sort(key=lambda x: x[0])  # Sort by the first element of the list
        for m in range(method_cnt):
            image = cv2.imread(crop_dict[img_idx]["img_paths"][m])
            for i in range(len(crop_boxes)):
                box = crop_boxes[i] # x1, y1, x2, y2
                color = webcolors.name_to_rgb(crop_colors[i % len(crop_colors)])
                color = (color[2], color[1], color[0])
                crop_img = image[box[1]:box[3], box[0]:box[2]]
                # Pad color borders
                pbw = configs.get("patch_border_width", 2)
                if pbw != 0:
                    crop_img_padded = cv2.copyMakeBorder(crop_img, pbw, pbw, pbw, pbw, cv2.BORDER_CONSTANT, value=color)
                else:
                    crop_img_padded = crop_img

                out_path = os.path.join(configs["output_crop_path"], method_names[m], f"img{img_idx:06d}_crop{i:02d}_{method_names[m]}.png")
                os.makedirs(os.path.dirname(out_path), exist_ok=True)

                cv2.imwrite(out_path, crop_img_padded)

                bbw = configs.get("box_border_width", 2)
                if bbw != 0:
                    image = cv2.rectangle(image, (box[0], box[1]), (box[2], box[3]), color, configs.get("box_border_width", 2))

            full_path = os.path.join(configs["output_crop_path"], method_names[m], f"img{img_idx:06d}_full_{method_names[m]}.png")               
            cv2.imwrite(full_path, image)