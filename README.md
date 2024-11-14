# CherryPicker
CherryPicker is a tool for visually inspecting image results. It is developed by Hylz.

The input of the tool is several directories. Each directory corresponds to the results of a method. **The user must assert that each directory contains the same number of images, the images in each directory (after sort by pathname) are in the same order.**

The tool will display results of different methods on the screen. The user can inspect the results and zoom in to see details. Patches can be selected and highlighted.

## Usage

1. Make environment.
```
conda create -n cherrypicker
conda activate cherrypicker
pip install -r requirements.txt
```

2. Set configurations.
By default, the configs are read from `configs.yaml`. You can also specify a config file by:
```
python main.py {your_config_file.yaml}
```
The most important setting is "methods". It is a list of methods with arbitrary length. Each method should be a dictionary with at least two keys: "name" and "path". "name" is the name of the method, which will be displayed on the screen and used for output file paths. "path" is the path to the directory containing the results of the method. **You must assert that each directory contains the same number of images, the images in each directory (after sort by pathname) are in the same order.** 

3. Run the tool.
```
python main.py
```
A GUI will appear. You can use the the buttons "Next Frame" and "Prev Frame" to switch from image to image. At the same time, only results from `{display_rows}*{display_cols}` (you can change them in the config file) methods are displayed. You can use the "Next Methods" and "Prev Methods" buttons to switch the methods displayed.

You can click on the draw box (on the left) to select a patch. The selected patch will be boxed in the image, and the corresponding patch in each displayed method will be zoomed in. You can press the "Save Current Crop" button to save information about the selected patch into `{output_path}`.

After you have selected all the patches you want, you can press the "Make All Crops" button to crop them out. They will be saved to `{crop_img_path}`.

Finally, you can press the "Make PPT" button to generate a PPT file `{output_ppt_path}`, in which all cropped patches will be displayed compactly.

