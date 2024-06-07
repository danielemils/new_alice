from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot
from alice_settings import AliceSettings
import os
import time
import subprocess
import math
import shutil
import tempfile
import platform
from mutagen.mp3 import MP3
import re

import traceback

class AliceStoppingException(Exception):
    def __init__(self, message=None):
        self.message = message

    def __str__(self):
        return f"AliceStoppingException: {self.message}"

class ConversionWorker(QObject):
    finished = pyqtSignal()
    curr_file_progress_updated = pyqtSignal(int)  # Signal to update progress modal
    total_progress_updated = pyqtSignal(str)
    current_task_updated = pyqtSignal(str)
    time_remaining_updated = pyqtSignal(int)
    
    MAX_CHARS = 20
    CHUNK_DURATION = 3600 # 1 hour in seconds

    OUTPUT_EXTENSION = ".mp3"

    def __init__(self, input_files: list, settings: AliceSettings):
        super().__init__()
        self.input_files = input_files
        self.settings = settings

        self.process = None
        
        # So subprocess doesn't open a CMD windowif platform.system() == "Windows":
        self.startupinfo = None
        if platform.system() == "Windows":
            self.startupinfo = subprocess.STARTUPINFO()
            self.startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            self.startupinfo.wShowWindow = subprocess.SW_HIDE

        self.file_durations = []
        self.estimated_times = []

        self.estimation_base_multi = 1.0
        self.estimated_merging_times = []

        self.time_remaining = 0
        self.time_started_last_file = None
        self.time_finished_last_file = None
        self.est_time_for_last_file = None
        self.dynamic_multi = 1.0

        self.stopped = False  # Flag to indicate if processing should be stopped

        self.files_to_seq_merge = []
        self.total_dur_seq_merge = 0
        self.merged_out_path = ""

        self.split_files = []

    @pyqtSlot()
    def convertFiles(self):
        self.current_task_updated.emit("Initializing...")
        self.fetchFileDurations()
        self.initEstimationMultiplier()
        self.initEstimatedMergingTimes()
        self.initEstimatedTimes()

        for index, input_file in enumerate(self.input_files):
            if self.stopped:
                break

            self.estimateRemainingTime(index)
            curr_file_duration = self.file_durations[index]

            filename, extension = os.path.splitext(os.path.basename(input_file))
            
            self.total_progress_updated.emit(f"{filename[:self.MAX_CHARS]}{'...' if len(filename) > self.MAX_CHARS else ''} ({index}/{len(self.input_files)})")
            self.current_task_updated.emit("Preparing file...")
            self.curr_file_progress_updated.emit(0)

            in_tmp_file_path = None
            out_tmp_file_path = None

            try:
                # sox cant handle non-ANSI characters (could be in filename or OS username)
                # so creating temp copy without weird characters for both input and output
                # input file:
                in_tmp_file_path = self.getTempFile(extension) # create temp file
                # remember to call self.delTempFile(tmp_file) when done using it
                self.copyFile(input_file, in_tmp_file_path) # copy input file to temp file

                if self.settings.save_as_60_min_chunks and len(self.files_to_seq_merge) == 0:
                    # final output path for merged files
                    self.merged_out_path = self.generateDestinationPath(f"{filename}(Merged)")

                # final output path for non-merged files
                output_file = self.generateDestinationPath(filename)

                out_tmp_file_path = self.getTempFile(self.OUTPUT_EXTENSION) # create temp file

                # self.estimateTotalTime(curr_file_duration, len(self.input_files) - index)

                if self.settings.save_as_60_min_chunks:
                    # if longer than 60 min: split into 60 min chunks then append remainder to to-merge list
                    if curr_file_duration > self.CHUNK_DURATION:
                        self.did_split = True
                        self.applyTremolo(in_tmp_file_path, out_tmp_file_path, extension, split=True)
                        
                        # sleep a little to wait for the files to be ready (just to be safe)
                        time.sleep(max(2, curr_file_duration * 0.00001))

                        # split file gets saved with diff name than original so this is empty file
                        self.delTempFile(out_tmp_file_path)

                        tmp_parent_dir = os.path.dirname(out_tmp_file_path)
                        tmp_filename = os.path.splitext(os.path.basename(out_tmp_file_path))
                        self.split_files = []
                        for file_in_tmp_dir in os.listdir(tmp_parent_dir):
                            file_in_tmp_dir_path = os.path.join(tmp_parent_dir, file_in_tmp_dir)
                            if os.path.isfile(file_in_tmp_dir_path):
                                if file_in_tmp_dir.startswith(tmp_filename):
                                    self.split_files.append(file_in_tmp_dir_path)

                        self.split_files.sort()

                        output_file_path_without_extension, output_file_extension = os.path.splitext(output_file)
                        for sf_idx, split_file in enumerate(self.split_files):
                            split_file_without_extension, _ = os.path.splitext(split_file)
                            split_file_number = split_file_without_extension[-3:]
                            split_file_output_path = f"{output_file_path_without_extension}{split_file_number}{output_file_extension}"
                            if sf_idx < len(self.split_files) - 1: # not last split file
                                self.copyFileAndFixMetadata(split_file, split_file_output_path)
                            else: # last split file
                                # the last split file after splitting will prob be shorter than 60 min
                                # so we include it in the merge array for next input files (it gets saved below if this is the last input file)
                                last_split_file = self.split_files.pop()
                                self.files_to_seq_merge.append(last_split_file)
                                self.total_dur_seq_merge += self.getFileDuration(last_split_file)
                                self.merged_out_path = f"{output_file_path_without_extension}{split_file_number}(Merged){output_file_extension}"
                                output_file = split_file_output_path
                    else:
                        self.applyTremolo(in_tmp_file_path, out_tmp_file_path, extension)
                        self.files_to_seq_merge.append(out_tmp_file_path)
                        self.total_dur_seq_merge += curr_file_duration
                else:
                    self.applyTremolo(in_tmp_file_path, out_tmp_file_path, extension)
                    self.copyFileAndFixMetadata(out_tmp_file_path, output_file) # copy temp output file to destination file

                # not last file
                if index + 1 < len(self.input_files):
                    next_file_duration = self.file_durations[index + 1]

                    if self.settings.save_as_60_min_chunks:
                        curr_chunk_diff = abs(self.total_dur_seq_merge - self.CHUNK_DURATION)
                        next_chunk_diff = abs(self.total_dur_seq_merge + next_file_duration - self.CHUNK_DURATION)
                        # if already past 60 min chunk
                        # or if closer to 60 min than we would be by including next file
                        # or next file will be split
                        if (self.total_dur_seq_merge >= self.CHUNK_DURATION
                        or curr_chunk_diff <= next_chunk_diff
                        or next_file_duration > self.CHUNK_DURATION):
                            # save/merge what we have now
                            if len(self.files_to_seq_merge) == 1: # no need to call merge cus just 1 file
                                self.copyFileAndFixMetadata(self.files_to_seq_merge[0], output_file) # copy temp output file to destination file
                                self.delTempChunkFiles()
                            else:
                                self.mergeFiles()
                else: # if last file
                    if self.settings.save_as_60_min_chunks:
                        if len(self.files_to_seq_merge) == 1: # no need to call merge cus just 1 file
                            self.copyFileAndFixMetadata(self.files_to_seq_merge[0], output_file) # copy temp output file to destination file
                            self.delTempChunkFiles()
                        else:
                            self.mergeFiles()

            except AliceStoppingException as e:
                self.delTempFile(out_tmp_file_path)
            except Exception as e:
                print(f"Exception in convertFiles, deleting temp files: {type(e)} ({e})")
                traceback.print_exc()
                self.stopConverting()

            self.delTempFile(in_tmp_file_path)
            if not self.settings.save_as_60_min_chunks:
                self.delTempFile(out_tmp_file_path)
            
            if len(self.split_files) > 0:
                self.delTempSplitFiles()
            
            self.current_task_updated.emit("")
        
        if len(self.files_to_seq_merge) > 0:
            self.delTempChunkFiles()
            
        self.finished.emit()

    def copyFile(self, src, dst):
        try:
            ret = shutil.copy(src, dst)
            if not isinstance(ret, str) or len(ret) < 4:
                print(f"shutil.copy returned: {ret}")
                return False
            return True
        except Exception as e:
                print(f"Failed copyFile: {type(e)} ({e})")
        return False
    
    def copyFileAndFixMetadata(self, src, dst):
        if src.endswith(".mp3"):
            try:
                mutagen_data = MP3(src)
                for md_key in mutagen_data:
                    if hasattr(mutagen_data[md_key], 'encoding') and hasattr(mutagen_data[md_key], 'text'):
                        mutagen_data[md_key].encoding = 3
                        # for some reason doing encode/decode twice results in correct encoding with noise enabled
                        if self.settings.noise:
                            try:
                                mutagen_data[md_key].text = [text.encode('latin-1').decode('utf-8').encode('latin-1').decode('utf-8') for text in mutagen_data[md_key].text]        
                            except:
                                mutagen_data[md_key].text = [text.encode('latin-1').decode('utf-8') for text in mutagen_data[md_key].text]
                        else: 
                            mutagen_data[md_key].text = [text.encode('latin-1').decode('utf-8') for text in mutagen_data[md_key].text]

                mutagen_data.save()
            except Exception as e:
                print(f"Error in copyFileAndFixMetadata: {type(e)} ({e})")
        self.copyFile(src, dst)

    def getTempFile(self, extension):
        temp_file_path = None
        try:
            # Create a temporary file
            temp_file_fd, temp_file_path = tempfile.mkstemp(suffix=extension)
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
    
    def delTempChunkFiles(self):
        for tmp_file in self.files_to_seq_merge:
            self.delTempFile(tmp_file)
        self.files_to_seq_merge = []
        self.total_dur_seq_merge = 0
        self.merged_out_path = ""
    
    def delTempSplitFiles(self):
        for tmp_file in self.split_files:
            self.delTempFile(tmp_file)
        self.split_files = []

    def getFileDuration(self, file):
        try:
            if file.endswith('.mp3'):
                return MP3(file).info.length
        except Exception as e:
            print(f"Failed getFileDuration: {type(e)} ({e})")
        return 1

    def fetchFileDurations(self):
        for inp_file in self.input_files:
            self.file_durations.append(self.getFileDuration(inp_file))
    
    def initEstimationMultiplier(self):
        # 11 min mp3 file stats:
        # tremolo only (with dc offset check)   ->  12.5 sec
        # with noise                            ->  +4.5 sec
        # with compressor                       ->  +2.5 sec

        # maybe file type multi too, mp3 prob slowest
        tremolo_multi = 0.0189
        noise_multi = 0.0068 * self.settings.noise # True or False so multiplying by 1 or 0
        compressor_multi = 0.0038 * self.settings.compressor

        self.estimation_base_multi = (tremolo_multi + noise_multi + compressor_multi)
    
    def initEstimatedMergingTimes(self):
        # merge doesnt always happen so predict how many merges will happen

        # merge 1 hour total -> 35 sec

        num_merges = 0
        curr_durations = []
        for dur_idx, file_dur in enumerate(self.file_durations):
            curr_durations.append(file_dur)
            if dur_idx < len(self.file_durations) - 1:
                next_dur = self.file_durations[dur_idx + 1]
                curr_dur_sum = sum(curr_durations)

                curr_chunk_diff = abs(curr_dur_sum - self.CHUNK_DURATION)
                next_chunk_diff = abs(curr_dur_sum + next_dur - self.CHUNK_DURATION)

                if (curr_dur_sum >= self.CHUNK_DURATION
                or curr_chunk_diff <= next_chunk_diff
                or next_dur > self.CHUNK_DURATION):
                    if len(curr_durations) > 1:
                        num_merges += 1
                        curr_durations = []
            else:
                if len(curr_durations) > 1:
                    num_merges += 1
        
        self.estimated_merging_times =  num_merges * [35]

    def initEstimatedTimes(self):
        for file_dur in self.file_durations:
            # time taken seems to be 2x normal estimate for 10h file
            # so assume it linearly increases by 2x per 10h
            self.estimated_times.append(self.estimation_base_multi * file_dur * (1.0 + (float(file_dur) / 36000.0)))

    @pyqtSlot()
    def estimateRemainingTime(self, idx):
        # to adjust to slower/faster computers
        if self.time_started_last_file is not None and self.time_finished_last_file is not None and self.est_time_for_last_file is not None:
            # print(f"Dynamic time multiplier was: {self.dynamic_multi}")
            self.dynamic_multi *= (self.time_finished_last_file - self.time_started_last_file) / self.est_time_for_last_file
            # print(f"Estimated time was: {self.est_time_for_last_file}")
            # print(f"Actual time was: {self.time_finished_last_file - self.time_started_last_file}")
            # print(f"Dynamic time multiplier set to: {self.dynamic_multi}")
            # print()

        # setting this ahead of time
        self.est_time_for_last_file = self.estimated_times[idx] * self.dynamic_multi

        # self.estimated_merging_times gets popped every merge so sum should be correct
        self.time_remaining = math.ceil((sum(self.estimated_times[idx:]) + sum(self.estimated_merging_times)) * self.dynamic_multi)
        self.time_remaining_updated.emit(self.time_remaining)


    def updateTimeRemaining(self, time_passed):
        new_time_remaining = max(0, self.time_remaining - time_passed)
        if math.ceil(new_time_remaining) != math.ceil(self.time_remaining): # no more than 1 update per sec
            self.time_remaining_updated.emit(math.floor(new_time_remaining))
        self.time_remaining = new_time_remaining

    @pyqtSlot()
    def mergeFiles(self):
        if len(self.files_to_seq_merge) > 0:
            try:
                self.estimated_merging_times.pop()
            except Exception as e:
                print(f"Error encountered: mergeFiles :: self.estimated_merging_times.pop() :: {e}")

            self.current_task_updated.emit("Merging previous files...")
            try:

                merged_fd, merged_path = tempfile.mkstemp(suffix=self.OUTPUT_EXTENSION) # Create a temporary file to store the output
                os.close(merged_fd) # Close the file descriptor as we won't be using it

                merge_command = ['sox-14-4-2/sox']
                for file_to_merge in self.files_to_seq_merge:
                    merge_command.append(file_to_merge)
                merge_command.append(merged_path)

                self.process = subprocess.Popen(merge_command, startupinfo=self.startupinfo)
                while not self.stopped and self.process.poll() is None:  # Check if the process is still running
                    time.sleep(0.1)
                    self.updateTimeRemaining(0.1)
                # check if user wants to cancel before proceeding further
                if self.stopped:
                    self.delTempFile(merged_path)
                    raise AliceStoppingException()
                
                self.copyFileAndFixMetadata(merged_path, self.merged_out_path) # copy temp output file to destination file

            except Exception as e:
                print(f"Error encountered: {e}")
                self.stopConverting()
            finally:
                self.delTempFile(merged_path)

        self.delTempChunkFiles()

    def createTempNoiseFile(self, in_file, extension):
        noise_fd, noise_path = tempfile.mkstemp(suffix=extension) # Create a temporary file to store the output
        os.close(noise_fd) # Close the file descriptor as we won't be using it

        self.current_task_updated.emit("Generating noise...")

        noise_command = ['sox-14-4-2/sox',in_file,noise_path,'synth','brownnoise','vol','0.05']
        self.process = subprocess.Popen(noise_command, startupinfo=self.startupinfo)
        while not self.stopped and self.process.poll() is None:  # Check if the process is still running
            time.sleep(0.1)
            self.updateTimeRemaining(0.1)
        # check if user wants to cancel before proceeding further
        if self.stopped:
            self.delTempFile(noise_path)
            raise AliceStoppingException()
        
        return noise_path

    # Check if file has DC Offset and fix it (bad quality files like Wuthering Heights chapter 1)
    def fixDCOffsetAndGetVolumeMulti(self, in_file, extension):
        stats_command = ['sox-14-4-2/sox',in_file, '-n', 'stat']
        self.process = subprocess.Popen(stats_command, stderr=subprocess.PIPE, text=True, encoding='utf-8', startupinfo=self.startupinfo)
        while not self.stopped and self.process.poll() is None:  # Check if the process is still running
            time.sleep(0.1)
            self.updateTimeRemaining(0.1)
        if self.stopped:
            raise AliceStoppingException()
        dc_offset = 0
        vol_multi = 1
        try:
            for std_err_line in self.process.stderr.readlines():
                if isinstance(std_err_line, str):
                    if std_err_line.startswith("Mean") and "amplitude" in std_err_line:
                        dc_offset = float(std_err_line.strip().split(":")[-1].strip())
                    if std_err_line.startswith("Volume") and "adjustment" in std_err_line:
                        vol_multi = float(std_err_line.strip().split(":")[-1].strip())
        except Exception as e:
            print(f"Error encountered: fixDCOffsetAndGetVolumeMulti :: reading/castng mean amplitude stat :: {e}")

        # Check if dc offset is so large that we need to fix it
        if round(dc_offset, 2) != 0.0:
            print(f"Found significant DC Offset of {dc_offset}, fixing...")

            fixed_dc_fd, fixed_dc_path = tempfile.mkstemp(suffix=extension) # Create a temporary file to store the output
            os.close(fixed_dc_fd) # Close the file descriptor as we won't be using it

            self.current_task_updated.emit("Bad DC offset, fixing it... (takes extra time)")

            fix_dc_command = ['sox-14-4-2/sox',in_file,fixed_dc_path, 'dcshift', f"{-dc_offset}"]
            self.process = subprocess.Popen(fix_dc_command, startupinfo=self.startupinfo)
            while not self.stopped and self.process.poll() is None:  # Check if the process is still running
                time.sleep(0.1)
                self.updateTimeRemaining(-0.1) # add to time est cus this wasnt included in estimate
            # check if user wants to cancel before proceeding further
            if self.stopped:
                self.delTempFile(fixed_dc_path)
                raise AliceStoppingException()
            
            return fixed_dc_path, vol_multi
        
        return None, vol_multi

    @pyqtSlot()
    def applyTremolo(self, in_file, out_file, extension, split=False):
        fixed_dc_path = None
        noise_path = None
        self.time_started_last_file = time.time()
        try:
            fixed_dc_path, vol_multi = self.fixDCOffsetAndGetVolumeMulti(in_file, extension)
            if fixed_dc_path != None:
                in_file = fixed_dc_path

            if (self.settings.noise):
                noise_path = self.createTempNoiseFile(in_file, extension)

            self.current_task_updated.emit("Applying effects...")

            # puzzle together command based on settings
            sox_command = ['sox-14-4-2/sox', '-S']
            if self.settings.noise:
                sox_command.append('-m')
                sox_command.append(noise_path)
            sox_command.extend(['-v', str(vol_multi), in_file])
            sox_command.extend([
                '-c', '2',
                out_file
            ])
            if split: # SPLIT
                sox_command.extend(['trim', '0', f"{self.CHUNK_DURATION}"])
            sox_command.extend(['rate', '-v', '44100'])
            if self.settings.compressor:
                # sox_command.extend(['compand', '0.01,0.5', '-35,-20,0,-1', '0', '-20', '0.5'])
                sox_command.extend(['compand', '0.01,1', '-30,-10,0,-1', '-1', '0', '0.02'])
            sox_command.extend(['gain', '-1'])
            sox_command.extend(['tremolo', str(self.settings.frequency), '100'])
            if split: # SPLIT
                sox_command.extend([':', 'newfile', ':', 'restart'])

            
            self.curr_file_progress_updated.emit(0)

            fake_progress_started_time = None
            fake_progress = 0

            self.process = subprocess.Popen(sox_command, stderr=subprocess.PIPE, text=True, encoding='utf-8', startupinfo=self.startupinfo)
            while not self.stopped and self.process.poll() is None:  # Check if the process is still running
                start_time = time.time()

                std_output = self.process.stderr.readline() # Read lines from stdout (blocking until something is ready)
                if std_output:  # Check if the line is not empty
                    progress = self.parseProgress(std_output)  # Parse the progress information
                    if progress is not None:  # Check if progress is valid
                        if progress >= 90: # (stuck at 100% (multiplied by 0.9 in parseProgress))
                            if fake_progress_started_time is None:
                                fake_progress_started_time = int(time.time())
                            if (int(time.time()) - fake_progress_started_time) % 3 == 0:
                                fake_progress += 1 # Show a lil movement on the progress bar every 3 sec
                        else:
                            fake_progress = progress
                        self.curr_file_progress_updated.emit(min(fake_progress, 99))  # Emit signal with progress value
                
                time_elapsed = time.time() - start_time
                self.updateTimeRemaining(time_elapsed)

            self.curr_file_progress_updated.emit(99)

        except Exception as e:
            print(f"Error encountered: {e}")
            traceback.print_exc()
            self.stopConverting()
        finally:
            if noise_path is not None:
                self.delTempFile(noise_path)
            if fixed_dc_path is not None:
                self.delTempFile(fixed_dc_path)
        
        self.time_finished_last_file = time.time()
        
        self.current_task_updated.emit("Finishing file...")

    def stopConverting(self):
        self.stopped = True  # Set the flag to stop processing
        if self.process is not None:
            self.process.terminate()
            self.process.wait()
            self.process = None

    def generateDestinationPath(self, filename):
        destination_path = os.path.join(self.settings.output_folder, f"{filename}(Converted).mp3")
        return destination_path

    def parseProgress(self, std_output: str):
        if std_output.startswith("In:") and len(std_output) > 7:
            try:
                return int(float(std_output[3:7].replace("%", "")) * 0.9)
            except Exception as e:
                print(f"Error encountered: parseProgress :: {e}")
        return None

