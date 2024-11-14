import yaml
import json
import glob
import os
import sys
import numpy as np
import cv2
from PyQt5.QtWidgets import QApplication, QMainWindow, QFileDialog, QMessageBox, QLabel, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QCheckBox, QSizePolicy, QGridLayout, QPushButton, QMessageBox, QComboBox
from PyQt5.QtGui import QImage, QPixmap, QPainter, QPen, QIcon
from PyQt5.QtCore import Qt, QPoint, QTimer

from visualizer import make_variance_map, make_ranking_map
from image_cropper import crop_images
from ppt_maker import make_ppt


PLACEHOLDER_PATH = "placeholder.png"
class SingleImageDisplay(QWidget):
    def __init__(self, parent=None, app=None):
        self.app = app
        super().__init__(parent=parent)
        self.image_path = PLACEHOLDER_PATH
        self.image = None
        layout = QVBoxLayout()
        self.info_label = QLabel("== empty display ==")
        layout.addWidget(self.info_label)
        self.full_image = QLabel()
        layout.addWidget(self.full_image)
        self.crop_image = QLabel()
        layout.addWidget(self.crop_image)
        self.setLayout(layout)

        # x, y, w, h
        self.corner_1 = QPoint(0, 0)
        self.corner_2 = QPoint(100, 100)

        # Set size policy to allow shrinking
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)

        self.load_images()

    def set_crop_points(self, corner_1, corner_2):
        self.corner_1 = corner_1
        self.corner_2 = corner_2
        self.load_images()


    def load_images(self):
        max_h = self.maximumHeight() - self.info_label.height()
        max_w = self.maximumWidth()

        PATCH_IMAGE_DISPLAY_SIZE_RATIO = 1.0

        image = QImage(self.image_path)
        full_h = max_h / (1 + PATCH_IMAGE_DISPLAY_SIZE_RATIO)
        h_ratio = image.height() / full_h
        w_ratio = image.width() / max_w
        ratio = max(h_ratio, w_ratio)
        image_scaled = image.scaled(int(image.width()/ratio), int(image.height()/ratio), Qt.KeepAspectRatio)
        self.full_image.setPixmap(QPixmap.fromImage(image_scaled))

        patch_h = max_h / (1 + PATCH_IMAGE_DISPLAY_SIZE_RATIO) * PATCH_IMAGE_DISPLAY_SIZE_RATIO
        
        h_ratio = (self.corner_2.y() - self.corner_1.y()) / patch_h
        w_ratio = (self.corner_2.x() - self.corner_1.x()) / max_w
        ratio = max(h_ratio, w_ratio)

        cropped_image = image.copy(self.corner_1.x(), self.corner_1.y(), self.corner_2.x()-self.corner_1.x(), self.corner_2.y()-self.corner_1.y())
        resized_image = cropped_image.scaled(int(cropped_image.width()/ratio), int(cropped_image.height()/ratio), Qt.KeepAspectRatio)
        self.crop_image.setPixmap(QPixmap.fromImage(resized_image))

    def set_image(self, image_path):
        self.image_path = image_path
        self.load_images()
    
    def set_info(self, info):
        info_str = json.dumps(info, indent=4)
        self.info_label.setText(info_str)

    def clear(self):
        self.full_image.clear()
        self.crop_image.clear()
        self.info_label.setText("== empty display ==")
        self.image_path = PLACEHOLDER_PATH

class DrawBox(QWidget):
    def __init__(self, parent=None, app=None):
        self.app = app
        self.controller = parent
        super().__init__(parent=parent)
        self.set_image(PLACEHOLDER_PATH)       
        # left-up
        self.corner_1 = QPoint(0, 0)
        # right-down
        self.corner_2 = QPoint(1, 1)
        self.update()
    
    def set_image(self, image_path):
        self.image_path = image_path
        self.qimg = QImage(self.image_path)
        self.max_H = self.qimg.height()
        self.max_W = self.qimg.width()
        self.setMinimumSize(self.max_W, self.max_H)  # Set minimum size to fit the image

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawImage(0, 0, self.qimg)
        painter.setPen(QPen(Qt.blue, 5, Qt.SolidLine))
        painter.drawEllipse(self.corner_1, 5, 5)
        painter.setPen(QPen(Qt.green, 5, Qt.SolidLine))
        painter.drawEllipse(self.corner_2, 5, 5)

        painter.setPen(QPen(Qt.red, 5, Qt.SolidLine))
        painter.drawRect(self.corner_1.x(), self.corner_1.y(), self.corner_2.x()-self.corner_1.x(), self.corner_2.y()-self.corner_1.y())
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if not self.point_in_image(event.pos()):
                return
            self.corner_1 = event.pos()
            # The controller decides how to deal with the changes. Then it gives the new corner_1 and corner_2 to the drawbox with a change_points call.
            self.controller.update_corner1(self.corner_1)

        elif event.button() == Qt.RightButton:
            if not self.point_in_image(event.pos()):
                return
            self.corner_2 = event.pos()
            self.controller.update_corner2(self.corner_2)


    def point_in_image(self, point):
        return point.x() >= 0 and point.y() >= 0 and point.x() < self.max_W and point.y() < self.max_H
    
    def check_points(self, corner_1, corner_2):
        assert corner_1.x() < corner_2.x()
        assert corner_1.y() < corner_2.y()
        assert corner_1.x() >= 0
        assert corner_1.y() >= 0
        assert corner_2.x() <= self.max_W
        assert corner_2.y() <= self.max_H

    def change_points(self, corner_1, corner_2):
        self.check_points(self.corner_1, corner_2)
        self.corner_1 = corner_1
        self.corner_2 = corner_2
        self.update()
        self.app.set_crop_points(self.corner_1, self.corner_2)

def wrap_widget(ipb, description, direction = Qt.Horizontal):
    layout = QHBoxLayout() if direction == Qt.Horizontal else QVBoxLayout()
    label = QLabel(description)
    #layout.addStretch(1)
    layout.addWidget(label)
    layout.addWidget(ipb)
    #layout.addStretch(1)
    return layout

class DrawBoxArea(QWidget):

    def __init__(self, app=None):
        self.app = app
        super().__init__()
        self.image_path = PLACEHOLDER_PATH
        
        layout = QVBoxLayout()
        layout.addStretch(1)
        
        self.hints = QLabel("Hint: On the image, left click to select upper-left corner, right click to select lower-right corner.")
        layout.addWidget(self.hints)  # Add the hints QLabel to the layout
        
        self.drawbox = DrawBox(parent=self, app=self.app)
        layout.addWidget(self.drawbox)

        self.qimg = QImage(self.image_path)
        self.max_H = self.qimg.height()
        self.max_W = self.qimg.width()
        default_size = min(self.max_H, self.max_W) // 4
        self.corner_1 = QPoint(0, 0)
        self.corner_2 = QPoint(default_size, default_size)
        self.drawbox.change_points(self.corner_1, self.corner_2)
        
        self.lock_ratio = False
        self.ratio = 1.0
        self.lock_h_w = False

        # Add input boxes for modifying corner_1 and corner_2
        self.corner1_x_input = QLineEdit()
        self.corner1_y_input = QLineEdit()
        self.h_input = QLineEdit()
        self.w_input = QLineEdit()
        self.ratio_input = QLineEdit()

        inputs_layout = QHBoxLayout()
        inputs_layout.addLayout(wrap_widget(self.corner1_x_input, "Corner1 x", Qt.Vertical))
        inputs_layout.addLayout(wrap_widget(self.corner1_y_input, "Corner1 y", Qt.Vertical))
        inputs_layout.addLayout(wrap_widget(self.w_input, "Patch W", Qt.Vertical))
        inputs_layout.addLayout(wrap_widget(self.h_input, "Patch H", Qt.Vertical))
        inputs_layout.addLayout(wrap_widget(self.ratio_input, "H/W Ratio", Qt.Vertical))
        layout.addLayout(inputs_layout)

        self.lock_ratio_checkbox = QCheckBox("Lock H/W Ratio")
        layout.addWidget(self.lock_ratio_checkbox)
        self.lock_h_w_checkbox = QCheckBox("Lock H and W")
        layout.addWidget(self.lock_h_w_checkbox)        

        layout.addStretch(1)
        self.setLayout(layout)  # Set the layout for the DrawBoxArea widget
        self.connect_signals()
        self.update_box()

    def set_image(self, img_path):
        self.image_path = img_path
        self.qimg = QImage(self.image_path)
        self.max_H = self.qimg.height()
        self.max_W = self.qimg.width()
        self.clip_corner()
        self.drawbox.set_image(self.image_path)
        self.update_box()

    def update_box(self):
        self.corner1_x_input.setText(str(self.corner_1.x()))
        self.corner1_y_input.setText(str(self.corner_1.y()))
        self.h_input.setText(str(self.corner_2.y() - self.corner_1.y()))
        self.w_input.setText(str(self.corner_2.x() - self.corner_1.x()))
        ratio = (self.corner_2.y() - self.corner_1.y()) / (self.corner_2.x() - self.corner_1.x())
        self.ratio_input.setText(f"{ratio:.4f}")
        self.drawbox.change_points(self.corner_1, self.corner_2)
        self.app.set_crop_points(self.corner_1, self.corner_2)

    def clip_corner(self):
        for corner in [self.corner_1, self.corner_2]:
            corner.setX(min(max(corner.x(), 0), self.max_W))
            corner.setY(min(max(corner.y(), 0), self.max_H))

    def update_corner1(self, corner_1):
        old_h = self.corner_2.y() - self.corner_1.y()
        old_w = self.corner_2.x() - self.corner_1.x()
        
        self.corner_1 = corner_1

        # The user probably wants the box to be moved
        if self.corner_1.x() >= self.corner_2.x() or self.lock_h_w:
            self.corner_2.setX(self.corner_1.x()+old_w)
        if self.corner_1.y() >= self.corner_2.y() or self.lock_h_w:
            self.corner_2.setY(self.corner_1.y()+old_h)
        self.clip_corner()

        # Force h & w to stay the same if corner2 gets clipped
        if self.lock_h_w:
            self.corner_1.setX(self.corner_2.x()-old_w)
            self.corner_1.setY(self.corner_2.y()-old_h)

        # Fix the ratio.
        if self.lock_ratio:
            # Default: fix new_w, change new_h
            new_w = self.corner_2.x() - self.corner_1.x()
            new_h = int(new_w * self.ratio)
            if self.corner_1.y() + new_h > self.max_H:
                new_h = self.max_H - self.corner_1.y()
                new_w = int(new_h / self.ratio)
            self.corner_2.setX(self.corner_1.x()+new_w)
            self.corner_2.setY(self.corner_1.y()+new_h)
        self.update_box()

    def update_corner2(self, corner_2):
        old_h = self.corner_2.y() - self.corner_1.y()
        old_w = self.corner_2.x() - self.corner_1.x()
        
        self.corner_2 = corner_2

        # The user probably wants the box to be moved
        if self.corner_1.x() >= self.corner_2.x() or self.lock_h_w:
            self.corner_1.setX(self.corner_2.x()-old_w)
        if self.corner_1.y() >= self.corner_2.y() or self.lock_h_w:
            self.corner_1.setY(self.corner_2.y()-old_h)
        self.clip_corner()

        # Force h & w to stay the same if corner1 gets clipped
        if self.lock_h_w:
            self.corner_2.setX(self.corner_1.x()+old_w)
            self.corner_2.setY(self.corner_1.y()+old_h)

        # Fix the ratio.
        if self.lock_ratio:
            # Default: fix new_w, change new_h
            new_w = self.corner_2.x() - self.corner_1.x()
            new_h = int(new_w * self.ratio)
            if self.corner_2.y() - new_h < 0:
                new_h = self.corner_2.y()
                new_w = int(new_h / self.ratio)
            self.corner_1.setX(self.corner_2.x()-new_w)
            self.corner_1.setY(self.corner_2.y()-new_h)

        self.update_box()

    def update_corner1_x(self, text):
        old_h = self.corner_2.y() - self.corner_1.y()
        old_w = self.corner_2.x() - self.corner_1.x()

        try:
            self.corner_1.setX(int(text))
        except:
            return
        
        if self.corner_1.x() >= self.corner_1.x() or self.lock_h_w:
            self.corner_2.setX(self.corner_1.x()+old_w)
        self.clip_corner()

        if self.lock_h_w:
            self.corner_1.setX(self.corner_2.x()-old_w)

        # Fix the ratio.
        if self.lock_ratio:
            # Default: fix new_w, change new_h
            new_w = self.corner_2.x() - self.corner_1.x()
            new_h = int(new_w * self.ratio)
            if self.corner_1.y() + new_h > self.max_H:
                new_h = self.max_H - self.corner_1.y()
                new_w = int(new_h / self.ratio)
            self.corner_2.setX(self.corner_1.x()+new_w)
            self.corner_2.setY(self.corner_1.y()+new_h)

        self.update_box()

    def update_corner1_y(self, text):
        old_h = self.corner_2.y() - self.corner_1.y()
        old_w = self.corner_2.x() - self.corner_1.x()
        try:
            self.corner_1.setY(int(text))
        except:
            return
        if self.corner_1.y() >= self.corner_2.y() or self.lock_h_w:
            self.corner_2.setY(self.corner_1.y()+old_h)
        self.clip_corner()

        if self.lock_h_w:
            self.corner_1.setY(self.corner_2.y()-old_h)

        # Fix the ratio.
        if self.lock_ratio:
            # Default: fix new_h, change new_w
            new_h = self.corner_2.y() - self.corner_1.y()
            new_w = int(new_h / self.ratio)
            if self.corner_1.x() + new_w > self.max_W:
                new_w = self.max_W - self.corner_1.x()
                new_h = int(new_w * self.ratio)
            self.corner_2.setX(self.corner_1.x()+new_w)
            self.corner_2.setY(self.corner_1.y()+new_h)

        self.update_box()

    def update_h(self, text):
        if self.lock_h_w:
            return
        
        old_h = self.corner_2.y() - self.corner_1.y()
        old_w = self.corner_2.x() - self.corner_1.x()
        
        try:
            new_h = int(text)
        except:
            # string not yet ready for parse
            return
        
        new_h = max(0, min(new_h, self.max_H))
        new_w = old_w
        if self.lock_ratio:
            new_w = int(new_h / self.ratio)
            if new_w > self.max_W:
                # Too bad! the new h cannot be achieved.
                new_w = self.max_W
                new_h = int(new_w * self.ratio)
        
        self.corner_2.setX(self.corner_1.x()+new_w)
        self.corner_2.setY(self.corner_1.y()+new_h)
        self.clip_corner()
        self.corner_1.setX(self.corner_2.x()-new_w)
        self.corner_1.setY(self.corner_2.y()-new_h)
        self.update_box()

    def update_w(self, text):
        if self.lock_h_w:
            return
        
        old_h = self.corner_2.y() - self.corner_1.y()
        old_w = self.corner_2.x() - self.corner_1.x()
        
        try:
            new_w = int(text)
        except:
            return
        new_w = max(0, min(new_w, self.max_W))
        new_h = old_h
        if self.lock_ratio:
            new_h = int(new_w * self.ratio)
            if new_h > self.max_H:
                # Too bad! the new w cannot be achieved.
                new_h = self.max_H
                new_w = int(new_h / self.ratio)
        
        self.corner_2.setX(self.corner_1.x()+new_w)
        self.corner_2.setY(self.corner_1.y()+new_h)
        self.clip_corner()
        self.corner_1.setX(self.corner_2.x()-new_w)
        self.corner_1.setY(self.corner_2.y()-new_h)
        self.update_box()
    
    def update_ratio(self, text):
        if self.lock_ratio:
            return
        try:
            self.ratio = float(text)
        except:
            return
        old_h = self.corner_2.y() - self.corner_1.y()
        old_w = self.corner_2.x() - self.corner_1.x()
        # Fix new_w, change new_h
        new_w = old_w
        new_h = int(old_w * self.ratio)
        if new_h > self.max_H:
            new_h = self.max_H
            new_w = int(new_h / self.ratio)
        self.corner_2.setX(self.corner_1.x()+new_w)
        self.corner_2.setY(self.corner_1.y()+new_h)
        self.clip_corner()
        self.corner_1.setX(self.corner_2.x()-new_w)
        self.corner_1.setY(self.corner_2.y()-new_h)
        self.update_box()
    
    def update_h_w_lock(self, state):
        if state == Qt.Checked:
            self.lock_h_w = True
            self.h_input.setEnabled(False)
            self.w_input.setEnabled(False)
        else:
            self.lock_h_w = False
            self.h_input.setEnabled(True)
            self.w_input.setEnabled(True)

    def update_ratio_lock(self, state):
        if state == Qt.Checked:
            self.lock_ratio = True
            self.ratio_input.setEnabled(False)
        else:
            self.lock_ratio = False
            self.ratio_input.setEnabled(True)
    
    def connect_signals(self):
        self.corner1_x_input.textChanged.connect(self.update_corner1_x)
        self.corner1_y_input.textChanged.connect(self.update_corner1_y)
        self.h_input.textChanged.connect(self.update_h)
        self.w_input.textChanged.connect(self.update_w)
        self.ratio_input.textChanged.connect(self.update_ratio)
        self.lock_ratio_checkbox.stateChanged.connect(self.update_ratio_lock)
        self.lock_h_w_checkbox.stateChanged.connect(self.update_h_w_lock)

class MyApp(QMainWindow):
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.setWindowTitle("CherryPicker 1.0")
        self.setWindowIcon(QIcon("icon.png"))
        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)
        self.whole_layout = QHBoxLayout(self.central_widget)
        self.left_part = QVBoxLayout()
        self.right_part = QGridLayout()

        self.image_displays = []
        self.max_display_cnt = config["display_rows"] * config["display_cols"]

        self.method_cnt = len(config["methods"])
        self.current_frame_idx = 0
        self.display_methods = []
        self.draw_method = 0
        
        self.img_paths = {}
        for idx, method in enumerate(self.config["methods"]):
            self.img_paths[idx] = sorted(
                glob.glob(os.path.join(method["path"], "**.png"))
                + glob.glob(os.path.join(method["path"], "**.jpg"))
            )

        self.frame_cnt = len(self.img_paths[0])
        for key in self.img_paths:
            assert len(self.img_paths[key]) == self.frame_cnt


        screen_size = app.primaryScreen().size()
        single_panel_size = screen_size.width() // (config["display_cols"]+3), screen_size.height() // (config["display_rows"]+1)

        for i in range(self.config["display_rows"]):
            for j in range(self.config["display_cols"]):
               imgd = SingleImageDisplay(app=self)
               imgd.setMaximumSize(single_panel_size[0], single_panel_size[1])
               self.right_part.addWidget(imgd, i, j)
               self.image_displays.append(imgd)

        self.current_methods_str = QLabel("Current displayed methods: []")
        self.left_part.addWidget(self.current_methods_str)
        self.method_buttons = []
        self.method_button_layout = QGridLayout()
        MAX_BUTTONS_PER_ROW = 4
        for idx, method in enumerate(config["methods"]):
            button = QPushButton(method["name"], self)
            button.setCheckable(True)
            button.clicked.connect(self.update_methods)
            self.method_buttons.append(button)
            self.method_button_layout.addWidget(button, idx//MAX_BUTTONS_PER_ROW, idx%MAX_BUTTONS_PER_ROW)
        
        self.left_part.addLayout(self.method_button_layout)

        self.left_part.addStretch(1)

        self.next_methods_button = QPushButton("Next Methods (Hotkey: W)", self)
        self.next_methods_button.clicked.connect(self.next_methods)
        self.next_methods_button.setShortcut("W")
        self.left_part.addWidget(self.next_methods_button)
        self.prev_methods_button = QPushButton("Prev Methods (Hotkey: S)", self)
        self.prev_methods_button.clicked.connect(self.prev_methods)
        self.prev_methods_button.setShortcut("S")
        self.left_part.addWidget(self.prev_methods_button)

        self.left_part.addStretch(2)

        self.select_draw_method = QComboBox(self)
        for idx, method in enumerate(config["methods"]):
            self.select_draw_method.addItem(method["name"])
        self.select_draw_method.currentIndexChanged.connect(self.update_draw_method)
        self.left_part.addLayout(wrap_widget(self.select_draw_method, "Method to show in draw box: ", Qt.Horizontal))
        self.select_draw_method.setCurrentIndex(0)

        self.draw_box_area = DrawBoxArea(app=self)
        self.left_part.addWidget(self.draw_box_area)

        self.current_frame_idx_input = QLineEdit()
        self.current_frame_idx_input.setText(str(self.current_frame_idx))
        self.current_frame_idx_input.textChanged.connect(self.update_frame_idx)
        self.left_part.addLayout(wrap_widget(self.current_frame_idx_input, "Current Frame Index: ", Qt.Horizontal))

        self.next_frame_button = QPushButton("Next Frame (Hotkey: D)", self)
        self.next_frame_button.clicked.connect(self.next_frame)
        self.next_frame_button.setShortcut("D")
        self.left_part.addWidget(self.next_frame_button)
        self.prev_frame_button = QPushButton("Prev Frame (Hotkey: A)", self)
        self.prev_frame_button.clicked.connect(self.prev_frame)
        self.prev_frame_button.setShortcut("A")
        self.left_part.addWidget(self.prev_frame_button)

        self.save_crop_button = QPushButton("Save Current Crop (Hotkey: Space) - Use this repeatedly first", self)
        self.save_crop_button.clicked.connect(self.save_crop)
        self.save_crop_button.setShortcut(" ")
        self.save_crop_button.setStyleSheet("background-color: lightgreen;")
        self.left_part.addWidget(self.save_crop_button)

        self.make_all_crops_button = QPushButton("Make All Crops (Hotkey: Enter) - Use this second", self)
        self.make_all_crops_button.clicked.connect(lambda: crop_images(self.config))
        self.make_all_crops_button.setShortcut("Return")
        self.left_part.addWidget(self.make_all_crops_button)

        self.make_ppt_button = QPushButton("Make PPT (Hotkey: P) - Use this last", self)
        self.make_ppt_button.clicked.connect(lambda: make_ppt(self.config))
        self.make_ppt_button.setShortcut("P")
        self.left_part.addWidget(self.make_ppt_button)
        
        self.whole_layout.addLayout(self.left_part)
        self.whole_layout.addLayout(self.right_part)
        self.central_widget.setLayout(self.whole_layout)

        self.next_methods()

        clear_previous = self.config.get("clear_previous", False)
        if clear_previous:
            output_info_path = self.config["output_info_path"]
            if os.path.exists(output_info_path):
                os.remove(output_info_path)


    def next_frame(self):
        self.current_frame_idx = (self.current_frame_idx + 1) % self.frame_cnt
        self.current_frame_idx_input.setText(str(self.current_frame_idx))
        self.assign_images()
    
    def prev_frame(self):
        self.current_frame_idx = (self.current_frame_idx - 1 + self.frame_cnt) % self.frame_cnt
        self.current_frame_idx_input.setText(str(self.current_frame_idx))
        self.assign_images()
    
    def update_frame_idx(self, text):
        try:
            self.current_frame_idx = int(text)
        except:
            return
        self.current_frame_idx = max(0, min(self.current_frame_idx, self.frame_cnt-1))
        self.current_frame_idx_input.setText(str(self.current_frame_idx))
        self.assign_images()

    def update_methods(self):
        for idx, button in enumerate(self.method_buttons):
            if button.isChecked() and idx not in self.display_methods:
                self.display_methods.append(idx)
            elif not button.isChecked() and idx in self.display_methods:
                self.display_methods.remove(idx)
        while len(self.display_methods) > self.max_display_cnt:
            kick = self.display_methods[0]
            self.method_buttons[kick].setChecked(False)
            self.display_methods.remove(kick)

        m_str = str([self.config["methods"][m]["name"] for m in self.display_methods])
        self.current_methods_str.setText(f"Current methods displayed: \n{m_str}\n Press buttons below to switch methods.")

        self.assign_images()

    def update_draw_method(self, idx):
        self.draw_method = idx
        self.assign_images()

    def update_methods_to_buttons(self):
        for idx, button in enumerate(self.method_buttons):
            if idx in self.display_methods:
                button.setChecked(True)
            else:
                button.setChecked(False)

    def next_methods(self):
        if len(self.display_methods) == 0:
            self.display_methods = [i%self.method_cnt for i in range(self.max_display_cnt)]
        else:
            max_displayed_idx = max(self.display_methods)
            self.display_methods = []
            for i in range(self.max_display_cnt):
                self.display_methods.append((max_displayed_idx+1+i) % self.method_cnt)
        self.update_methods_to_buttons()
        self.update_methods()

    def prev_methods(self):
        if len(self.display_methods) == 0:
            self.display_methods = [i%self.method_cnt for i in range(self.max_display_cnt)]
        else:
            min_displayed_idx = min(self.display_methods)
            self.display_methods = []
            for i in range(self.max_display_cnt):
                self.display_methods.append((min_displayed_idx-self.max_display_cnt+i+10*self.method_cnt) % self.method_cnt)
        self.update_methods_to_buttons()
        self.update_methods()
        

    def set_crop_points(self, corner_1, corner_2):
        for id in self.image_displays:
            id.set_crop_points(corner_1, corner_2)

    def assign_images(self):
        idx = self.current_frame_idx
        assert idx < self.frame_cnt and idx >= 0
        for i, m in enumerate(self.display_methods):
            self.image_displays[i].set_image(self.img_paths[m][idx])
            self.image_displays[i].set_info(self.config["methods"][m])
        for i in range(len(self.display_methods), self.max_display_cnt):
            self.image_displays[i].clear()
            self.image_displays[i].load_images()
        self.draw_box_area.set_image(self.img_paths[self.draw_method][idx])

    def save_crop(self):
        op = self.config["output_info_path"]
        d = os.path.dirname(op)
        if not os.path.exists(d):
            os.makedirs(d)
        content = None
        if os.path.exists(op):
            with open(op, "r") as f:
                content = yaml.load(f, Loader=yaml.FullLoader)
        if not type(content) == dict:
            content = {}
        items = content.get("crop_patches", [])
        item = {}
        item["img_idx"] = self.current_frame_idx
        item["img_paths"] = [self.img_paths[m][self.current_frame_idx] for m in range(self.method_cnt)]
        item["crop_box"] = [self.draw_box_area.corner_1.x(), self.draw_box_area.corner_1.y(), self.draw_box_area.corner_2.x(), self.draw_box_area.corner_2.y()]
        items.append(item)
        
        content["crop_patches"] = items

        with open(op, "w") as f:
            yaml.dump(content, f)
        
        if self.config.get("show_crop_alert", False):
            # Display the alert
            alert = QMessageBox()
            alert.setText(f"Saved cropping info to {op}: frame_idx = {self.current_frame_idx}, x1 =  {self.draw_box_area.corner_1.x()}, y1 = {self.draw_box_area.corner_1.y()}, x2 = {self.draw_box_area.corner_2.x()}, y2 = {self.draw_box_area.corner_2.y()}")
            alert.setWindowTitle("Crop successfully saved!")
            alert.setStandardButtons(QMessageBox.Ok)
            alert.exec_()


if __name__ == '__main__':
    if len(sys.argv) > 1:
        config_file = sys.argv[1]
    else:
        config_file = 'configs.yaml'
    with open(config_file) as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
    print(config)
    
    if config.get("make_variance_map", False):
        config = make_variance_map(config)
    if config.get("make_ranking_map", False):
        config = make_ranking_map(config, lambda x, y: -np.abs(x-y).sum(axis=2))

    PLACEHOLDER_PATH = config.get("placeholder_path", PLACEHOLDER_PATH)

    app = QApplication([])
    app.setStyleSheet("QLabel, QCheckBox{font-size: 12pt;}")
    my_app = MyApp(config)
    my_app.show()

    app.exec_()

