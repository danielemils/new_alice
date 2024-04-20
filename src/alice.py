import sys
import subprocess
import os
from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout,
    QFileDialog, QLabel, QListWidget, QListWidgetItem,
    QHBoxLayout, QDialog, QProgressBar,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
    QCheckBox, QDoubleSpinBox,
)
from PyQt5.QtCore import (
    QObject, QThread, pyqtSignal, pyqtSlot, QSize, Qt,
    QSettings, QPoint
)
from PyQt5.QtGui import QIcon, QPixmap, QColor, QCloseEvent
import resources # required
import tempfile
import time
import platform
import shutil
import math
import datetime
from alice_settings import AliceSettings
from conversion import ConversionWorker

# CONFIG_FILE = "alice_config.json"
# cfg_input_folder_key = "input_folder"
# cfg_output_folder_key = "output_folder"
# cfg_settings_key = "settings"

WINDOW_WIDTH = 390
WINDOW_HEIGHT = 460


# important for temp file creation while converting
if platform.system() == "Windows":
    dir = "C:/Temp"
    tempfile.tempdir = dir
else:
    # untested
    dir = "/tmp"
    tempfile.tempdir = dir
os.makedirs(dir, exist_ok=True)
# ------------
    

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.worker_thread = None
        self.progress_dialog = None

        self.settings = AliceSettings.load()

        self.selected_files = []

        # self.music_icon = QIcon(":/icons/music_icon_white.png")

        self.initUI()

    def closeEvent(self, event: QCloseEvent):
        self.settings.window_position = self.pos()
        self.settings.save()
        event.accept()


    # def center(self):
    #     # Get the screen's geometry
    #     screen_geometry = QDesktopWidget().screenGeometry()

    #     # Calculate the center position for the window
    #     center_x = int((screen_geometry.width() - self.width()) / 2)
    #     center_y = int((screen_geometry.height() - self.height()) / 2)

    #     # Move the window to the center position
    #     return center_x, center_y

    def initUI(self):
        self.setWindowTitle('Alice')
        self.setWindowIcon(QIcon(":icons/alicelogo128.png"))
        self.setObjectName("main")
        # self.setGeometry(*(self.center()), 10, 10)
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)

        self.setWindowFlags(Qt.FramelessWindowHint) # borderless window
        self.draggable = False
        self.offset = None

        self.setAttribute(Qt.WA_TranslucentBackground)

        self.move(self.settings.window_position)


        border = QWidget(self)
        border.setObjectName("border")
        frame = QWidget(border)
        frame.setObjectName("main_frame")
        frame.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        frame_layout = QVBoxLayout(frame)
        self.content_frame = QWidget(frame)
        self.content_frame.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)

        # layouts
        titlebar_layout = QHBoxLayout()
        content_layout = QVBoxLayout()
        settings_layout = QHBoxLayout()

        frame_layout.addLayout(titlebar_layout)
        frame_layout.addLayout(content_layout)
        frame_layout.addLayout(settings_layout)

        # content
        self.alice_pic = QLabel(self)
        self.alice_pic.setObjectName("alice_pic")
        self.alice_pic.setScaledContents(True)
        self.alice_pic.setFixedSize(QSize(30, 30))
        self.alice_pic.setPixmap(QPixmap(":icons/alicelogo128.png"))
        titlebar_layout.addWidget(self.alice_pic, 0, Qt.AlignLeft | Qt.AlignVCenter)
        
        titlebar_layout.addSpacing(33)

        self.alice_text = QLabel(self)
        self.alice_text.setScaledContents(True)
        self.alice_text.setFixedSize(QSize(57, 25))
        self.alice_text.setPixmap(QPixmap(":icons/alice_title.png"))
        titlebar_layout.addWidget(self.alice_text, 1, Qt.AlignHCenter | Qt.AlignVCenter)

        self.minimize_button = QPushButton("−", self)
        self.minimize_button.clicked.connect(self.minimize_window)
        self.minimize_button.setObjectName("minimize_button")
        self.minimize_button.setFixedSize(QSize(30, 30))
        titlebar_layout.addWidget(self.minimize_button, 0, Qt.AlignRight | Qt.AlignVCenter)

        self.close_button = QPushButton("🞪", self)
        self.close_button.clicked.connect(self.close_window)
        self.close_button.setObjectName("exit_button")
        self.close_button.setFixedSize(QSize(30, 30))
        titlebar_layout.addWidget(self.close_button, 0, Qt.AlignRight | Qt.AlignVCenter)

        content_layout.addSpacing(20)

        self.btn_select_files = QPushButton('Select Files', self)
        self.btn_select_files.clicked.connect(self.selectFile)
        content_layout.addWidget(self.btn_select_files)

        self.lst_selected_files = QListWidget(self)
        self.lst_selected_files.setFocusPolicy(Qt.NoFocus)
        self.lst_selected_files.setSelectionMode(QListWidget.NoSelection)
        self.lst_selected_files.setFixedHeight(120)
        self.lst_selected_files.setIconSize(QSize(12, 12))
        self.lst_selected_files.setViewportMargins(0, 0, 10, 0)
        self.lst_selected_files.addItem(QListWidgetItem("No files selected"))
        content_layout.addWidget(self.lst_selected_files)

        self.btn_select_destination_folder = QPushButton('Select Destination Folder', self)
        self.btn_select_destination_folder.setObjectName("select_destination_folder")
        self.btn_select_destination_folder.clicked.connect(self.selectDestinationFolder)
        content_layout.addWidget(self.btn_select_destination_folder)
        
        self.lbl_selected_destination_folder = QLabel(text=self.settings.output_folder, parent=self)
        self.lbl_selected_destination_folder.setObjectName("selected_destination_folder")
        self.lbl_selected_destination_folder.setAlignment(Qt.AlignCenter)
        self.lbl_selected_destination_folder.setWordWrap(True)
        content_layout.addWidget(self.lbl_selected_destination_folder)

        content_layout.addStretch(1)

        self.btn_settings = QPushButton(self)
        self.btn_settings.setFixedWidth(60)
        self.btn_settings.setIcon(QIcon(":icons/settings_icon.png"))
        self.btn_settings.clicked.connect(self.showSettingsDialog)
        settings_layout.addWidget(self.btn_settings)

        self.btn_apply_effect = QPushButton('Convert', self)
        self.btn_apply_effect.setObjectName("main_button")
        self.btn_apply_effect.setDisabled(True)
        self.btn_apply_effect.clicked.connect(self.convert)
        settings_layout.addWidget(self.btn_apply_effect)

        self.content_frame.setLayout(frame_layout)

        # Connect window destruction signal to cleanup slot
        self.destroyed.connect(self.cleanup)

    def selectFile(self):
        file_dialog = QFileDialog()
        # See SoX_important_info.txt for supporting more file extensions
        # Audio Files (*.mp3 *.wav *.aac *.wma *.aiff *.aif *.aiffc *.aifc)
        self.selected_files, _ = file_dialog.getOpenFileNames(self, 'Select Files', directory=self.settings.input_folder, filter="Audio Files (*.mp3)")
        self.selected_files.sort()

        # save path
        if len(self.selected_files) > 0:
            selected_input_folder = os.path.dirname(self.selected_files[0])
            if selected_input_folder and selected_input_folder != self.settings.input_folder:
                self.settings.input_folder = selected_input_folder
                self.settings.save()

        # update list widget
        self.lst_selected_files.clear()  # Clear the list first
        if len(self.selected_files) == 0:
            self.lst_selected_files.addItem(QListWidgetItem("No files selected"))
        else:
            for file in self.selected_files:
                filename, extension = os.path.splitext(os.path.basename(file))
                # item = QListWidgetItem(self.music_icon, f"{filename}{extension}")
                # self.lst_selected_files.addItem(item)
                self.lst_selected_files.addItem(f"{filename}{extension}")

        self.updateConvertButtonDisabled()


    def selectDestinationFolder(self):
        folder_dialog = QFileDialog()
        selected_destination_folder = folder_dialog.getExistingDirectory(self, 'Select Folder', directory=self.settings.output_folder)
        if selected_destination_folder and selected_destination_folder != self.settings.output_folder:
            self.settings.output_folder = selected_destination_folder
            self.settings.save()
            self.lbl_selected_destination_folder.setText(selected_destination_folder)
            # self.lbl_selected_destination_folder.adjustSize()
            self.updateConvertButtonDisabled()

    def updateConvertButtonDisabled(self):
        self.btn_apply_effect.setDisabled(not (len(self.selected_files) > 0 and self.settings.output_folder))

    def convert(self):
        if len(self.selected_files) > 0 and self.settings.output_folder:
            self.showProgressDialog()
            self.worker = ConversionWorker(self.selected_files, self.settings)
            self.worker.curr_file_progress_updated.connect(self.updateProgressDialogBar)
            self.worker.total_progress_updated.connect(self.updateProgressDialogText)
            self.worker.current_task_updated.connect(self.updateProgressDialogTask)
            self.worker.time_remaining_updated.connect(self.updateProgressDialogTime)
            self.worker.finished.connect(self.onFinished)
            self.worker_thread = WorkerThread(self.worker)
            self.worker_thread.start()

    def showProgressDialog(self):
        self.progress_dialog = CustomProgressDialog(self)
        self.progress_dialog.canceled.connect(self.cleanup)
        self.progress_dialog.rejected.connect(self.cleanup)

        self.progress_dialog.show()
        self.blurMain()

    @pyqtSlot(str)
    def updateProgressDialogText(self, text):
        self.progress_dialog.setLabelText(text)

    @pyqtSlot(str)
    def updateProgressDialogTask(self, text):
        self.progress_dialog.setTaskText(text)

    @pyqtSlot(int)
    def updateProgressDialogBar(self, progress):
        self.progress_dialog.setValue(progress)

    @pyqtSlot(int)
    def updateProgressDialogTime(self, secs):
        text = ""
        try:
            text = str(datetime.timedelta(seconds=secs))
        except Exception as e:
            print(f"Failed updateProgressDialogTime: {type(e)} ({e})")
        self.progress_dialog.setTimeRemaining(f"Estimated time remaining: {text}")

    @pyqtSlot()
    def onFinished(self):
        if self.progress_dialog is not None:
            self.progress_dialog.setLabelText("Conversion completed.")
            # self.progress_dialog.setAutoReset(False)
            self.progress_dialog.setValue(100)
            self.progress_dialog.setFinishButton()
    
    @pyqtSlot()
    def cleanup(self):
        try:
            self.worker_thread.quit()
            self.worker_thread.wait()
            self.worker_thread.deleteLater()
        except:
            pass
        try:
            self.progress_dialog.setValue(0)
            self.progress_dialog.accept()
            self.progress_dialog.deleteLater()
            self.content_frame.setGraphicsEffect(None)
        except:
            pass
    
    def blurMain(self):
        opacity_effect = QGraphicsOpacityEffect()
        opacity_effect.setOpacity(0.5)
        self.content_frame.setGraphicsEffect(opacity_effect)

    def showSettingsDialog(self):
        self.settings_dialog = CustomSettingsDialog(self, self.settings)
        self.settings_dialog.saved.connect(self.saveAndCloseSettingsDialog)
        self.settings_dialog.rejected.connect(self.cancelSettingsDialog)

        self.settings_dialog.show()
        self.blurMain()


    def cancelSettingsDialog(self):
        self.settings_dialog.deleteLater()
        self.content_frame.setGraphicsEffect(None)

    @pyqtSlot(AliceSettings)
    def saveAndCloseSettingsDialog(self, new_settings: AliceSettings):
        self.settings = new_settings
        self.settings.save()

        self.settings_dialog.accept()
        self.settings_dialog.deleteLater()
        self.content_frame.setGraphicsEffect(None)
        
    
    # borderless window code
    def mousePressEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            self.draggable = True
            self.offset = event.pos()

    def mouseMoveEvent(self, event):
        if self.draggable:
            self.move(event.globalPos() - self.offset)

    def mouseReleaseEvent(self, _):
        self.draggable = False

    def minimize_window(self):
        self.showMinimized()

    def close_window(self):
        self.close()
    # end borderless window code


class CustomProgressDialog(QDialog):
    canceled = pyqtSignal()

    def __init__(self, parent):
        super().__init__(parent)
        
        self.setWindowFlag(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowModality(2)

        size = QSize(int(WINDOW_WIDTH * 0.8), int(WINDOW_WIDTH * 0.7))
        shadow_offset = 5

        self.setFixedSize(size)
        self.setContentsMargins(10, 10, 10, 10)

        if parent:
            parent_center = parent.geometry().center()
            self.move(parent_center + QPoint(shadow_offset, shadow_offset) - self.rect().center())

        border = QWidget(self)
        border.setObjectName("border")
        frame = QWidget(border)
        frame.setObjectName("main_frame")
        frame.setFixedSize(size.width() - shadow_offset * 2, size.height() - shadow_offset * 2)

        drop_shadow = QGraphicsDropShadowEffect()
        drop_shadow.setBlurRadius(shadow_offset)
        drop_shadow.setXOffset(shadow_offset)
        drop_shadow.setYOffset(shadow_offset)
        drop_shadow.setColor(QColor(0, 0, 0, 160))
        self.setGraphicsEffect(drop_shadow)

        # Content
        self.title_label = QLabel("Converting")
        self.title_label.setObjectName("dialog_title")
        self.title_label.setAlignment(Qt.AlignCenter)

        self.label = QLabel("")
        self.label.setAlignment(Qt.AlignCenter)

        self.task_label = QLabel("")
        self.task_label.setObjectName("not_bold")
        self.task_label.setAlignment(Qt.AlignCenter)

        self.progress_bar = QProgressBar()
        self.progress_bar.setAlignment(Qt.AlignCenter)
        self.progress_bar.setRange(0, 100)

        self.time_label = QLabel("")
        self.time_label.setObjectName("not_bold")
        self.time_label.setAlignment(Qt.AlignCenter)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setDefault(True)
        self.cancel_button.clicked.connect(self.cancel)
        
        # Layout
        frame_layout = QVBoxLayout(frame)

        layout = QVBoxLayout()
        frame_layout.addLayout(layout)

        layout.addWidget(self.title_label)
        layout.addWidget(self.label)
        layout.addWidget(self.task_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.time_label)
        layout.addWidget(self.cancel_button)
        
        frame.setLayout(frame_layout)
        
    @pyqtSlot()
    def cancel(self):
        # Implement cancel behavior
        self.canceled.emit()

    def setLabelText(self, text):
        self.label.setText(text)

    def setTaskText(self, text):
        self.task_label.setText(text)

    def setValue(self, value):
        self.progress_bar.setValue(value)

    def setTimeRemaining(self, text):
        self.time_label.setText(text)

    def setFinishButton(self):
        self.cancel_button.setText("Finish")
        self.cancel_button.setObjectName("main_button")
        self.cancel_button.style().unpolish(self.cancel_button)
        self.cancel_button.style().polish(self.cancel_button)


class CustomSettingsDialog(QDialog):
    saved = pyqtSignal(AliceSettings)

    def __init__(self, parent, saved_settings: AliceSettings):
        super().__init__(parent)
        
        self.saved_settings = saved_settings
        self.chosen_settings = saved_settings.copy()
        
        self.setWindowFlag(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowModality(2)

        size = QSize(int(WINDOW_WIDTH * 0.8), int(WINDOW_HEIGHT * 0.65))
        shadow_offset = 5

        item_height = 24

        self.setFixedSize(size)
        self.setContentsMargins(10, 10, 10, 10)

        if parent:
            parent_center = parent.geometry().center()
            self.move(parent_center + QPoint(shadow_offset, shadow_offset) - self.rect().center())

        border = QWidget(self)
        border.setObjectName("border")
        frame = QWidget(border)
        frame.setObjectName("main_frame")
        frame.setFixedSize(size.width() - shadow_offset * 2, size.height() - shadow_offset * 2)

        drop_shadow = QGraphicsDropShadowEffect()
        drop_shadow.setBlurRadius(shadow_offset)
        drop_shadow.setXOffset(shadow_offset)
        drop_shadow.setYOffset(shadow_offset)
        drop_shadow.setColor(QColor(0, 0, 0, 160))
        self.setGraphicsEffect(drop_shadow)

        # Content
        self.title_label = QLabel("Settings")
        self.title_label.setObjectName("dialog_title")
        self.title_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.title_label.setContentsMargins(16,0,0,0)
        
        self.restore_defaults_button = QPushButton("Restore Defaults")
        self.restore_defaults_button.setObjectName("restore_defaults")
        self.restore_defaults_button.clicked.connect(self.restoreDefaults)

        self.noise_checkbox = QCheckBox("Noise")
        self.noise_checkbox.setFixedHeight(item_height)
        self.noise_checkbox.setToolTip("Adds noise to maintain stimulation during silent parts.")
        self.noise_checkbox.stateChanged.connect(self.noiseCheckboxChanged)

        self.compressor_checkbox = QCheckBox("Dynamic Volume")
        self.compressor_checkbox.setFixedHeight(item_height)
        self.compressor_checkbox.setToolTip("Makes quiet sounds louder.")
        self.compressor_checkbox.stateChanged.connect(self.compressorCheckboxChanged)

        frequency_input_wrapper = QWidget()
        frequency_input_wrapper.setFixedHeight(item_height)
        frequency_input_wrapper.setObjectName("frequency_wrapper")
        frequency_tooltip = "Adjusts the frequency of the stimulation."
        self.frequency_input = QDoubleSpinBox()
        self.frequency_input.setToolTip(frequency_tooltip)
        self.frequency_input.setFixedWidth(60)
        self.frequency_input.setMinimum(AliceSettings.MIN_FREQ)
        self.frequency_input.setMaximum(AliceSettings.MAX_FREQ)
        self.frequency_input.setSingleStep(0.5)
        self.frequency_input.lineEdit().setFocusPolicy(Qt.NoFocus)
        self.frequency_input.lineEdit().setCursor(Qt.ArrowCursor)
        self.frequency_input.setDecimals(1)
        self.frequency_input.setValue(40.0)
        self.frequency_input.valueChanged.connect(self.frequencyValueChanged)
        frequency_label = QLabel("Frequency")
        frequency_label.setObjectName("frequency_label")
        frequency_label.setToolTip(frequency_tooltip)

        self.save_as_60_min_checkbox = QCheckBox("Merge into ~1-hour files")
        self.save_as_60_min_checkbox.setFixedHeight(item_height)
        self.save_as_60_min_checkbox.setToolTip("Tries to merge input files into 1 hour long output files.")
        self.save_as_60_min_checkbox.stateChanged.connect(self.saveAs60MinCheckboxChanged)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel)

        self.save_button = QPushButton("Save")
        self.save_button.setObjectName("main_button")
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self.save)
        
        # Layout
        frame_layout = QVBoxLayout(frame)

        layout = QVBoxLayout()
        title_restore_layout = QHBoxLayout()
        checkbox_layout = QVBoxLayout()
        frequency_layout = QHBoxLayout()
        frequency_layout.setContentsMargins(6,0,0,0)
        cancel_save_layout = QHBoxLayout()

        frame_layout.addLayout(layout)

        title_restore_layout.addWidget(self.title_label)
        title_restore_layout.addWidget(self.restore_defaults_button)
        layout.addLayout(title_restore_layout)

        checkbox_layout.setContentsMargins(20, 10, 10, 10)
        checkbox_layout.addWidget(self.noise_checkbox)
        checkbox_layout.addWidget(self.compressor_checkbox)
        frequency_layout.addWidget(self.frequency_input)
        frequency_layout.addWidget(frequency_label)
        frequency_input_wrapper.setLayout(frequency_layout)
        checkbox_layout.addWidget(frequency_input_wrapper)
        checkbox_layout.addWidget(self.save_as_60_min_checkbox)
        checkbox_layout.addStretch(1)
        layout.addLayout(checkbox_layout)

        cancel_save_layout.addWidget(self.cancel_button, 1)
        cancel_save_layout.addWidget(self.save_button, 2)
        layout.addLayout(cancel_save_layout)
        
        self.fromConfig()

        frame.setLayout(frame_layout)

    def fromConfig(self):
        self.noise_checkbox.setCheckState(self.chosen_settings.noise * 2)
        self.compressor_checkbox.setCheckState(self.chosen_settings.compressor * 2)
        self.frequency_input.setValue(self.chosen_settings.frequency)
        self.save_as_60_min_checkbox.setCheckState(self.chosen_settings.save_as_60_min_chunks * 2)

    @pyqtSlot()
    def save(self):
        self.saved.emit(self.chosen_settings)

    @pyqtSlot()
    def cancel(self):
        self.rejected.emit()

    @pyqtSlot()
    def restoreDefaults(self):
        default_settings = AliceSettings()
        self.chosen_settings.noise = default_settings.noise
        self.chosen_settings.compressor = default_settings.compressor
        self.chosen_settings.frequency = default_settings.frequency
        self.chosen_settings.save_as_60_min_chunks = default_settings.save_as_60_min_chunks
        self.fromConfig()

    def noiseCheckboxChanged(self, state):
        self.chosen_settings.noise = state == 2 # 0, 1, 2 => unchecked, intermediate, checked

    def compressorCheckboxChanged(self, state):
        self.chosen_settings.compressor = state == 2 # 0, 1, 2 => unchecked, intermediate, checked

    def frequencyValueChanged(self, value):
        self.chosen_settings.frequency = value

    def saveAs60MinCheckboxChanged(self, state):
        self.chosen_settings.save_as_60_min_chunks = state == 2 # 0, 1, 2 => unchecked, intermediate, checked


class WorkerThread(QThread):
    def __init__(self, worker: ConversionWorker):
        super().__init__()
        self.worker = worker

    def run(self):
        self.worker.convertFiles()

    def quit(self):
        self.worker.stopConverting()
        self.worker.deleteLater()
        super().quit()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()

    try:
        with open(os.path.join(sys._MEIPASS, "style.qss"), "r") as f:
            _style = f.read()
            app.setStyleSheet(_style)
    except:
        try:
            with open("src/old_style.qss", "r") as f:
                _style = f.read()
                app.setStyleSheet(_style)
        except:
            pass

    sys.exit(app.exec_())
