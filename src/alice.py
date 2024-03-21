import sys
import subprocess
import os
from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout,
    QFileDialog, QLabel, QListWidget, QListWidgetItem,
    QHBoxLayout, QDesktopWidget, QDialog, QProgressBar,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
    QCheckBox, QDoubleSpinBox
)
from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot, QSize, Qt, QSettings, QPoint
from PyQt5.QtGui import QIcon, QPixmap, QColor, QCloseEvent
import resources # required
import tempfile
import time
import platform
import shutil
import math
import datetime

ORG_NAME = "Alice Converter"
APP_NAME = "Alice"
QSETTINGS_KEY = "settings"
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

def getFilenameAndExtensionTuple(file_path):
    return os.path.splitext(os.path.basename(file_path))

def loadConfig():
    try:
        qsett = QSettings(ORG_NAME, APP_NAME)
        return qsett.value(QSETTINGS_KEY, None)

        # with open(CONFIG_FILE, "r") as f:
        #     data = json.load(f)
        #     return data
    except Exception:
        return None
    

class AliceSettings():
    MIN_FREQ = 30.0
    MAX_FREQ = 50.0

    def __init__(self, window_position = QPoint(200, 200), input_folder=None, output_folder=None, noise=True, compressor=True, frequency=40.0):
        self.window_position = window_position

        self.input_folder = input_folder
        self.output_folder = output_folder

        self.noise = noise
        self.compressor = compressor
        self.frequency = max(min(frequency, self.MAX_FREQ), self.MIN_FREQ)

    def to_diccy(self):
        return self.__dict__
    
    @classmethod
    def from_diccy(cls, diccy=None):
        if diccy is None:
            return cls()
        return cls(**diccy)

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.worker_thread = None
        self.progress_dialog = None

        self.settings = AliceSettings.from_diccy(loadConfig())

        self.selected_files = []

        # self.music_icon = QIcon(":/icons/music_icon_white.png")

        self.initUI()

    def closeEvent(self, event: QCloseEvent):
        self.settings.window_position = self.pos()
        self.saveConfig()
        event.accept()

    def saveConfig(self):
        try:
            # data = {}

            # curr_input_folder = self.saved_input_folder
            # if len(self.selected_files) > 0:
            #     curr_input_folder = os.path.dirname(self.selected_files[0])
            # data[cfg_input_folder_key] = curr_input_folder

            # curr_output_folder = self.saved_output_folder
            # if self.selected_destination_folder:
            #     curr_output_folder = self.selected_destination_folder
            # data[cfg_output_folder_key] = curr_output_folder
            
            # if isinstance(self.settings, AliceSettings):
            #     data[cfg_settings_key] = self.settings.to_diccy()

            # with open(CONFIG_FILE, "w") as f:
            #     json.dump(data, f)
            
            # self.saved_input_folder, self.saved_output_folder = curr_input_folder, curr_output_folder
            
            qsett = QSettings(ORG_NAME, APP_NAME)
            qsett.setValue(QSETTINGS_KEY, self.settings.to_diccy())

        except Exception:
            pass

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
        self.selected_files, _ = file_dialog.getOpenFileNames(self, 'Select Files', directory=self.settings.input_folder, filter="Audio Files (*.mp3 *.wav *.aac *.wma *.aiff *.aif *.aiffc *.aifc)")

        # save path
        if len(self.selected_files) > 0:
            selected_input_folder = os.path.dirname(self.selected_files[0])
            if selected_input_folder and selected_input_folder != self.settings.input_folder:
                self.settings.input_folder = selected_input_folder
                self.saveConfig()

        # update list widget
        self.lst_selected_files.clear()  # Clear the list first
        if len(self.selected_files) == 0:
            self.lst_selected_files.addItem(QListWidgetItem("No files selected"))
        else:
            for file in self.selected_files:
                filename, extension = getFilenameAndExtensionTuple(file)
                # item = QListWidgetItem(self.music_icon, f"{filename}{extension}")
                # self.lst_selected_files.addItem(item)
                self.lst_selected_files.addItem(f"{filename}{extension}")

        self.updateConvertButtonDisabled()


    def selectDestinationFolder(self):
        folder_dialog = QFileDialog()
        selected_destination_folder = folder_dialog.getExistingDirectory(self, 'Select Folder', directory=self.settings.output_folder)
        if selected_destination_folder and selected_destination_folder != self.settings.output_folder:
            self.settings.output_folder = selected_destination_folder
            self.saveConfig()
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
            self.progress_dialog.setCancelButtonText("Finish")
    
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
        self.saveConfig()

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


class ConversionWorker(QObject):
    finished = pyqtSignal()
    curr_file_progress_updated = pyqtSignal(int)  # Signal to update progress modal
    total_progress_updated = pyqtSignal(str)
    time_remaining_updated = pyqtSignal(int)
    
    max_chars = 20

    def __init__(self, input_files: str, settings: AliceSettings):
        super().__init__()
        self.input_files = input_files
        self.settings = settings

        self.tmp_copy = None
        self.process = None

        self.time_remaining = 0
        self.time_started_last_file = None
        self.est_time_for_last_file = None
        self.dynamic_multi = 1.0

        self.stopped = False  # Flag to indicate if processing should be stopped

    @pyqtSlot()
    def convertFiles(self):
        for index, input_file in enumerate(self.input_files):
            if self.stopped:
                return
            
            filename, extension = getFilenameAndExtensionTuple(input_file)
            
            self.total_progress_updated.emit(f"{filename[:self.max_chars]}{'...' if len(filename) > self.max_chars else ''} ({index}/{len(self.input_files)})")

            in_tmp_file_path = None
            out_tmp_file_path = None

            try:
                # sox cant handle non-ANSI characters (could be in filename or OS username)
                # so creating temp copy without weird characters for both input and output
                # input file:
                in_tmp_file_path = self.getTempFile(extension) # create temp file
                # remember to call self.delTempFile(tmp_file) when done using it
                self.copyFile(input_file, in_tmp_file_path) # copy input file to temp file
                # output file:
                output_file = self.generateDestinationPath(filename)
                out_tmp_file_path = self.getTempFile(extension) # create temp file

                self.estimateTotalTime(in_tmp_file_path, len(self.input_files) - index)

                self.applyTremolo(in_tmp_file_path, out_tmp_file_path, extension)

                self.copyFile(out_tmp_file_path, output_file) # copy temp output file to destination file
            except Exception as e:
                print(f"Exception in convertFiles, deleting temp files: {type(e)} ({e})")

            self.delTempFile(in_tmp_file_path) # IMPORTANT
            self.delTempFile(out_tmp_file_path) # IMPORTANT
        
        self.finished.emit()

    def copyFile(self, src, dst):
        try:
            ret = shutil.copy(src, dst)
            if not isinstance(ret, str) or len(ret) < 4:
                print(f"shutil.copy returned: {f}")
                return False
            return True
        except Exception as e:
                print(f"Failed copyFile: {type(e)} ({e})")
        return False

    def getTempFile(self, extension):
        temp_file_path = None
        try:
            # Create a temporary file
            temp_file_fd, temp_file_path = tempfile.mkstemp(suffix=extension)
            self.tmp_copy = temp_file_path
            # Close the file descriptor as we won't be using it
            os.close(temp_file_fd)
            return temp_file_path
        except Exception as e:
            print(f"Failed getTempFile: {type(e)} ({e})")
        return None


    def delTempFile(self, tmp_file):
        if tmp_file is not None and tmp_file != "":
            try:
                os.remove(tmp_file)
            except Exception as e:
                print(f"Failed to delete temp file: {type(e)} ({e})")

    # inefficient to make a copy of every file at the start just to estimate time
    # so just guessing based on one file
    def estimateTotalTime(self, curr_file, num_files_remaining):
        # to adjust to slower/faster computers
        if self.time_started_last_file is not None and self.est_time_for_last_file is not None:
            self.dynamic_multi *= (time.time() - self.time_started_last_file) / self.est_time_for_last_file
            print(self.est_time_for_last_file)
            print(time.time() - self.time_started_last_file)
            print(self.dynamic_multi)
        self.time_started_last_file = time.time()
        # 11 min mp3 file stats:
        # tremolo only      ->  11.5 sec
        # with noise        ->  +4.5 sec
        # with compressor   ->  +2.5 sec

        # maybe file type multi too, mp3 prob slowest
        tremolo_multi = 0.0174
        noise_multi = 0.0068 * self.settings.noise # True or False so multiplying by 1 or 0
        compressor_multi = 0.0038 * self.settings.compressor

        multi = (tremolo_multi + noise_multi + compressor_multi) * self.dynamic_multi

        command = ['sox-14-4-2/sox', '--i', '-D', curr_file]
        try:
            result = subprocess.run(command, stdout=subprocess.PIPE, check=True)
            output = result.stdout.decode('utf-8')

            self.est_time_for_last_file = float(output) * multi
            time_est = math.ceil(self.est_time_for_last_file * num_files_remaining)
            self.time_remaining = time_est
            self.time_remaining_updated.emit(time_est)
        except subprocess.CalledProcessError as e:
            print("Error:", e)
        except Exception as e:
            print(f"Failed estimateTotalTime: {type(e)} ({e})")

    def updateTimeRemaining(self, time_passed):
        new_time_remaining = max(0, self.time_remaining - time_passed)
        if math.ceil(new_time_remaining) != math.ceil(self.time_remaining): # no more than 1 update per sec
            self.time_remaining_updated.emit(math.floor(new_time_remaining))
        self.time_remaining = new_time_remaining

    @pyqtSlot()
    def applyTremolo(self, in_file, out_file, extension):
        noise_path = None

        try:
            # So subprocess doesn't open a CMD window
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            # noise
            if (self.settings.noise):
                noise_fd, noise_path = tempfile.mkstemp(suffix=extension) # Create a temporary file to store the output
                os.close(noise_fd) # Close the file descriptor as we won't be using it
                noise_command = ['sox-14-4-2/sox',in_file,noise_path,'synth','brownnoise','vol','0.05']
                self.process = subprocess.Popen(noise_command, startupinfo=startupinfo)
                while not self.stopped and self.process.poll() is None:  # Check if the process is still running
                    time.sleep(0.1)
                    self.updateTimeRemaining(0.1)
                # check if user wants to cancel before proceeding further
                if self.stopped:
                    return

            # puzzle together command based on settings
            sox_command = ['sox-14-4-2/sox', '-S']
            if self.settings.noise:
                sox_command.append('-m')
            sox_command.append(in_file)
            if self.settings.noise:
                sox_command.append(noise_path)
            sox_command.extend([
                out_file,
                'rate', '-v', '44100',
                'tremolo', str(self.settings.frequency), '100',
            ])
            if self.settings.compressor:
                sox_command.append('compand')
                if self.settings.noise:
                    sox_command.extend(['0.01,0.5', '-35,-20,0,-1', '0', '-20', '0.5'])
                else:
                    sox_command.extend(['0.05,1', '-40,-50,-20,-10,0,-10', '0', '-60', '0.5'])

            
            self.curr_file_progress_updated.emit(0)

            self.process = subprocess.Popen(sox_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, startupinfo=startupinfo)
            while not self.stopped and self.process.poll() is None:  # Check if the process is still running
                start_time = time.time()

                std_output = self.process.stdout.readline()  # Read a line from stdout
                if std_output:  # Check if the line is not empty
                    progress = self.parseProgress(std_output)  # Parse the progress information
                    if progress is not None:  # Check if progress is valid
                        self.curr_file_progress_updated.emit(progress)  # Emit signal with progress value
                
                time_elapsed = time.time() - start_time
                self.updateTimeRemaining(time_elapsed)

            self.curr_file_progress_updated.emit(100)

        except subprocess.CalledProcessError as e:
            print(f"Error encountered: {e}")
        finally:
            if noise_path is not None and noise_path != "":
                try:
                    os.remove(noise_path)
                except Exception as e:
                    print(f"Failed to delete temp noise file: {type(e)} ({e})")

    def stopConverting(self):
        self.stopped = True  # Set the flag to stop processing
        if self.process is not None:
            self.process.terminate()
            self.process.wait()

    def generateDestinationPath(self, filename):
        destination_path = os.path.join(self.settings.output_folder, f"{filename}(Converted).mp3")
        return destination_path

    def parseProgress(self, std_output: str):
        if std_output.startswith("In:") and len(std_output) > 7:
            try:
                return int(float(std_output[3:7]))
            except ValueError:
                pass
        return 0


class WorkerThread(QThread):
    def __init__(self, worker):
        super().__init__()
        self.worker = worker

    def run(self):
        self.worker.convertFiles()

    def quit(self):
        self.worker.stopConverting()
        self.worker.deleteLater()
        super().quit()


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
            self.move(parent_center - self.rect().center())

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
        self.label.setObjectName("selected_destination_folder") # reusing style
        self.label.setAlignment(Qt.AlignCenter)

        self.progress_bar = QProgressBar()
        self.progress_bar.setAlignment(Qt.AlignCenter)
        self.progress_bar.setRange(0, 100)

        self.time_label = QLabel("")
        self.time_label.setObjectName("selected_destination_folder") # reusing style
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

    def setValue(self, value):
        self.progress_bar.setValue(value)

    def setTimeRemaining(self, text):
        self.time_label.setText(text)

    def setCancelButtonText(self, text):
        self.cancel_button.setText(text)


class CustomSettingsDialog(QDialog):
    saved = pyqtSignal(AliceSettings)

    ITEM_HEIGHT = 30

    def __init__(self, parent, saved_settings: AliceSettings):
        super().__init__(parent)
        
        self.saved_settings = saved_settings
        self.chosen_settings = AliceSettings.from_diccy(saved_settings.to_diccy())
        
        self.setWindowFlag(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowModality(2)

        size = QSize(int(WINDOW_WIDTH * 0.8), int(WINDOW_HEIGHT * 0.8))
        shadow_offset = 5

        self.setFixedSize(size)
        self.setContentsMargins(10, 10, 10, 10)

        if parent:
            parent_center = parent.geometry().center()
            self.move(parent_center - self.rect().center())

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
        
        self.restore_defaults_button = QPushButton("Restore Defaults")
        self.restore_defaults_button.setObjectName("restore_defaults")
        self.restore_defaults_button.clicked.connect(self.restoreDefaults)

        self.noise_checkbox = QCheckBox("Noise")
        self.noise_checkbox.setFixedHeight(self.ITEM_HEIGHT)
        self.noise_checkbox.setToolTip("Adds noise to maintain stimulation during silent parts.")
        self.noise_checkbox.stateChanged.connect(self.noiseCheckboxChanged)

        self.compressor_checkbox = QCheckBox("Dynamic Volume")
        self.compressor_checkbox.setFixedHeight(self.ITEM_HEIGHT)
        self.compressor_checkbox.setToolTip("Makes quiet sounds louder.")
        self.compressor_checkbox.stateChanged.connect(self.compressorCheckboxChanged)

        frequency_input_wrapper = QWidget()
        frequency_input_wrapper.setFixedHeight(self.ITEM_HEIGHT)
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
        self.fromConfig()

    def noiseCheckboxChanged(self, state):
        self.chosen_settings.noise = state == 2 # 0, 1, 2 => unchecked, intermediate, checked

    def compressorCheckboxChanged(self, state):
        self.chosen_settings.compressor = state == 2 # 0, 1, 2 => unchecked, intermediate, checked

    def frequencyValueChanged(self, value):
        self.chosen_settings.frequency = value


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
            with open("src/style.qss", "r") as f:
                _style = f.read()
                app.setStyleSheet(_style)
        except:
            pass

    sys.exit(app.exec_())
