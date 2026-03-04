# CherryPicker
CherryPicker is a **web-based** tool for visually inspecting and comparing image results from different methods. It is developed by Hylz, rewritten from the original PyQt5 version to a modern browser-based UI.

The input of the tool is several directories. Each directory corresponds to the results of a method. **The user must ensure that each directory contains the same number of images, and that images in each directory (after sorting by pathname) are in the same order.**

The tool displays results of different methods in the browser. The user can inspect the results, zoom in to see details, and select patches to highlight. Selected patches can be stitched in a dedicated HTML collage mode and exported as HTML or PDF (via browser print).

## Features
- **Web UI** – runs in any modern browser, no Qt dependency
- **Interactive crop selection** – click or drag on the canvas to define crop regions
- **Lock aspect ratio / size** – keep the crop box consistent across frames
- **Keyboard shortcuts** – `A`/`D` navigate frames, `W`/`S` cycle methods, `Space` saves a crop, `Delete` removes the last crop
- **Live crop preview** – see the zoomed-in patch for every method in real time
- **Crop history** – view, jump to, or delete previously saved crops
- **Stitch mode (HTML collage)** – configure method layout / spacing / typography and preview in real time
- **Export HTML & PDF** – download a self-contained HTML file, or print to PDF directly from the browser

## Usage

1. **Install dependencies.**
```bash
conda create -n cherrypicker python=3.10
conda activate cherrypicker
pip install -r requirements.txt
```

2. **Edit `configs.yaml`.**
Set the `methods` list. Each method needs `name` and `path` keys. Mark one method with `is_gt: true` and one with `is_ours: true` if you want ranking maps.

You can also specify a custom config file:
```bash
python app.py your_config.yaml
```

3. **Run the server.**
```bash
python app.py
```
Then open **http://localhost:8765** in your browser.

4. **Workflow.**
   1. Browse frames with **Prev/Next Frame** (or `A`/`D`).
   2. Switch displayed methods with the toggle buttons or **Prev/Next Methods** (`W`/`S`).
   3. Draw a crop box on the canvas (left panel). Adjust with inputs or drag.
   4. Press **Save Current Crop** (`Space`) to record the crop.
   5. Repeat for all desired patches/frames.
   6. Click the top-left mode button to switch to **拼图模式**.
   7. Configure method layout and stitch parameters in the left panel.
   8. Use **导出 HTML** or **导出 PDF（打印）**.

## Configuration Reference

| Key | Description |
|-----|-------------|
| `methods` | List of `{name, path, is_gt?, is_ours?}` |
| `display_rows`, `display_cols` | How many methods to show at once |
| `output_info_path` | Where crop positions are saved (YAML) |
| `output_crop_path` | Directory for cropped images |
| `output_ppt_path` | Legacy PPT output path (optional) |
| `crop_box_colors` | Colour names for crop-box borders |
| `patch_border_width` | Border width around cropped patches |
| `box_border_width` | Border width of crop-box on full images |
| `small_cnt` | Legacy PPT option |
| `groups_per_page` | Legacy PPT option |
| `slide_w`, `slide_h` | Legacy PPT option |
| `clear_previous` | Whether to clear old outputs on startup |
| `make_variance_map` | Generate variance visualisation |
| `make_ranking_map` | Generate ranking visualisation |

