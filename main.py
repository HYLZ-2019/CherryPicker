import yaml
from PyQt5.QtWidgets import QApplication, QMainWindow, QFileDialog, QMessageBox, QLabel, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QCheckBox
from PyQt5.QtGui import QImage, QPixmap, QPainter, QPen
from PyQt5.QtCore import Qt, QPoint

PLACEHOLDER_PATH = "/home/hylou/nas-cp/hylou/Results/disparity_tester/deblur_nowarp/EDI/data_000000/0001.png"

class SingleImageDisplay(QWidget):
    def __init__(self, parent=None, app=None):
        self.app = app
        super().__init__(parent=parent)
        self.image_path = PLACEHOLDER_PATH
        self.image = None
        layout = QVBoxLayout()
        self.full_image = QLabel()
        layout.addWidget(self.full_image)
        self.crop_image = QLabel()
        layout.addWidget(self.crop_image)
        self.setLayout(layout)

        # x, y, w, h
        self.corner_1 = QPoint(0, 0)
        self.corner_2 = QPoint(100, 100)

        self.load_images()

    def set_crop_points(self, corner_1, corner_2):
        self.corner_1 = corner_1
        self.corner_2 = corner_2
        self.load_images()


    def load_images(self):
        image = QImage(self.image_path)
        self.full_image.setPixmap(QPixmap.fromImage(image))

        cropped_image = image.copy(self.corner_1.x(), self.corner_1.y(), self.corner_2.x()-self.corner_1.x(), self.corner_2.y()-self.corner_1.y())
        self.crop_image.setPixmap(QPixmap.fromImage(cropped_image))

class DrawBox(QWidget):
    def __init__(self, parent=None, app=None):
        self.app = app
        self.controller = parent
        super().__init__(parent=parent)
        self.image_path = PLACEHOLDER_PATH

        self.qimg = QImage(self.image_path)
        self.max_H = self.qimg.height()
        self.max_W = self.qimg.width()

        # left-up
        self.corner_1 = QPoint(0, 0)
        # right-down
        self.corner_2 = QPoint(1, 1)

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
            self.corner_1 = event.pos()
            # The controller decides how to deal with the changes. Then it gives the new corner_1 and corner_2 to the drawbox with a change_points call.
            self.controller.update_corner1(self.corner_1)
            #self.fix_points(prior=1)
        elif event.button() == Qt.RightButton:
            self.corner_2 = event.pos()
            self.controller.update_corner2(self.corner_2)
            #self.fix_points(prior=2)
        print(self.corner_1, self.corner_2)
        #self.update()
        #self.app.set_crop_points(self.corner_1, self.corner_2)
    
    def check_points(self, corner_1, corner_2):
        print("check_points: ", corner_1, corner_2)
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

def wrap_input(ipb, description):
    layout = QVBoxLayout()
    label = QLabel(description)
    layout.addStretch(1)
    layout.addWidget(label)
    layout.addWidget(ipb)
    layout.addStretch(1)
    return layout

class DrawBoxArea(QWidget):

    def __init__(self, parent=None):
        self.app = parent
        super().__init__(parent=parent)
        self.image_path = PLACEHOLDER_PATH
        
        layout = QVBoxLayout()
        
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
        inputs_layout.addLayout(wrap_input(self.corner1_x_input, "Corner1 x"))
        inputs_layout.addLayout(wrap_input(self.corner1_y_input, "Corner1 y"))
        inputs_layout.addLayout(wrap_input(self.h_input, "Patch H"))
        inputs_layout.addLayout(wrap_input(self.w_input, "Patch W"))
        inputs_layout.addLayout(wrap_input(self.ratio_input, "H/W Ratio"))
        layout.addLayout(inputs_layout)

        self.lock_ratio_checkbox = QCheckBox("Lock H/W Ratio")
        layout.addWidget(self.lock_ratio_checkbox)
        self.lock_h_w_checkbox = QCheckBox("Lock H and W")
        layout.addWidget(self.lock_h_w_checkbox)        

        self.setLayout(layout)  # Set the layout for the DrawBoxArea widget
        self.connect_signals()
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
        print("original", self.corner_1, self.corner_2)
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
        print("controller result", self.corner_1, self.corner_2)
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
    def __init__(self):
        super().__init__()
        self.setWindowTitle("My Application")
        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)
        self.layout = QHBoxLayout(self.central_widget)
        self.label = QLabel(text="Hello World!", parent=self)
        self.layout.addWidget(self.label)
        self.image_displays = [SingleImageDisplay(self)]
        for id in self.image_displays:
           self.layout.addWidget(id)

        self.draw_box_area = DrawBoxArea(self)
        self.layout.addWidget(self.draw_box_area)

    def set_crop_points(self, corner_1, corner_2):
        for id in self.image_displays:
            id.set_crop_points(corner_1, corner_2)

if __name__ == '__main__':
    with open('configs.yaml') as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
    print(config)

    app = QApplication([])
    my_app = MyApp()
    my_app.show()

    app.exec_()

