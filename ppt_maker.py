# Tool for sewing images into a PPT file.
# Made by Hylz.

from pptx import Presentation
from pptx.util import Inches, Mm
import glob
import cv2
import os

def make_ppt(config):

    root_path = config["output_crop_path"]
    method_names = [m["name"] for m in config["methods"]]
    method_cnt = len(method_names)

    SMALL_CNT = config.get("small_cnt", 3) # 每张大图下面放的放大图数量
    GROUPS_PER_PAGE = config.get("groups_per_page", 5) # 每页贴几组图
    # A4大小
    SLIDE_W = config.get("slide_w", 210)
    SLIDE_H = config.get("slide_h", 297)

    GROUP_HORI_GAP_RATIO = config.get("group_hori_gap_ratio", 0.05) # 每组之间横向间隔和每组横向宽度的比值
    GROUP_VERT_GAP_RATIO = config.get("group_vert_gap_ratio", 0.07) # 每组之间纵向间隔和每组纵向宽度的比值
    SMALL_HORI_GAP_RATIO = config.get("small_hori_gap_ratio", 0.05) # 小图-大图之间横向距离 / 小图宽度
    SMALL_VERT_GAP_RATIO = config.get("small_vert_gap_ratio", 0.05) # 小图-小图之间纵向距离 / 小图高度

    AREA_W = SLIDE_W * 0.8 # 图片要贴满PPT的多大范围
    AREA_H = SLIDE_W * 0.95 # 实际上会靠上放，如果太多了就向下溢出

    # img_paths[m] is a sequence of image paths for method m:
    # [big_1, small_1_1, small_1_2, big_2, small_2_1, small_2_2, ...]
    img_paths = []

    for m in method_names:
        all_imgs = sorted(
            glob.glob(os.path.join(root_path, m, "*.png"))
            + glob.glob(os.path.join(root_path, m, "*.jpg"))
        )
        seqs = {}
        for img in all_imgs:
            base = os.path.basename(img)
            seq = base.split("_")[0]
            if not seq in seqs:
                seqs[seq] = { "big": None, "small": [] }
            if "crop" in base:
                if len(seqs[seq]["small"]) == SMALL_CNT:
                    print("Warning: Sequence {} has more than {} crops. Extra crops will be neglected.".format(seq, SMALL_CNT))
                    continue
                else:
                    seqs[seq]["small"].append(img)
            if "full" in base:
                seqs[seq]["big"] = img

        my_imgs = []
        for seq in seqs:
            my_imgs.append(seqs[seq]["big"])
            my_imgs.extend(seqs[seq]["small"])
            for i in range(SMALL_CNT - len(seqs[seq]["small"])):
                # Not enough crops. Use a placeholder.
                my_imgs.append(config.get("placeholder_path", "placeholder.png"))
        img_paths.append(my_imgs)

    print(img_paths)
    # Do the real work

    group_cnt = len(img_paths[0]) // (SMALL_CNT+1)
    for pthlist in img_paths:
        assert len(pthlist) == group_cnt * (SMALL_CNT+1)
    page_cnt = (group_cnt + GROUPS_PER_PAGE - 1) // GROUPS_PER_PAGE

    bighpix, bigwpix, _ = cv2.imread(img_paths[0][0]).shape # 大图比例
    smallhpix, smallwpix, _ = cv2.imread(img_paths[0][1]).shape # 小图比例
    group_w = AREA_W / GROUPS_PER_PAGE # 每组图的宽度

    bigw = group_w / (1 + GROUP_HORI_GAP_RATIO) # 大图宽度
    bigh = bigw * bighpix / bigwpix # 大图高度
    smallw = bigw / (SMALL_CNT + (SMALL_CNT-1)*SMALL_HORI_GAP_RATIO) # 小图宽度
    smallh = smallw * smallhpix / smallwpix # 小图高度
    group_h = (bigh + smallh*(1+SMALL_VERT_GAP_RATIO))*(1+GROUP_VERT_GAP_RATIO) # 每组图的高度

    prs = Presentation()
    prs.slide_width = Mm(SLIDE_W)
    prs.slide_height = Mm(SLIDE_H)
    blank_slide_layout = prs.slide_layouts[6]

    for pagenum in range (page_cnt):
        slide = prs.slides.add_slide(blank_slide_layout)

        for row_i in range(method_cnt):
            
            big_top = (SLIDE_H - AREA_H) / 2 + group_h*row_i
            small_top = big_top + bigh + smallh*SMALL_VERT_GAP_RATIO

            text_left = 0
            text_top = (big_top + small_top) / 2
            text_width = (SLIDE_W - AREA_W) / 2
            text_height = small_top - big_top
            textbox = slide.shapes.add_textbox(Mm(text_left), Mm(text_top), Mm(text_width), Mm(text_height))
            text_frame = textbox.text_frame
            p = text_frame.add_paragraph()
            p.text = method_names[row_i]

            imglist = img_paths[row_i][pagenum*GROUPS_PER_PAGE*(1+SMALL_CNT):(pagenum+1)*GROUPS_PER_PAGE*(1+SMALL_CNT)]
            page_groupcnt = len(imglist) // (1+SMALL_CNT)
            for group_i in range(page_groupcnt):
                big_left = (SLIDE_W - AREA_W) / 2 + group_w*group_i
                pic = slide.shapes.add_picture(imglist[group_i*(1+SMALL_CNT)], Mm(big_left), Mm(big_top), width=Mm(bigw), height=Mm(bigh))
                for small_i in range(SMALL_CNT):
                    small_left = big_left + (1+SMALL_HORI_GAP_RATIO)*smallw*small_i
                    pic = slide.shapes.add_picture(imglist[group_i*(1+SMALL_CNT)+small_i+1], Mm(small_left), Mm(small_top), width=Mm(smallw), height=Mm(smallh))
            

    output_path = config["output_ppt_path"]
    prs.save(output_path)