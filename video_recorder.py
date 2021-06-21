import multiprocessing as mp
import os
import queue
import signal
import subprocess as sp
import threading
import time

import cv2

import config
import log
from util import clear_pipe

logger = log.recorder_logger

CAPTURE_ALWAYS_SAVE = 1
CAPTURE_SAVE_WHEN_MOVING = 2

if not os.path.exists("./video"):
    os.makedirs("./video")


class VideoRecorder(object):

    def __init__(self, cam_pipe: mp.Queue):
        self.cam_pipe = cam_pipe
        self.cmd_pipe = mp.Queue()
        self.fps = config.record.fps
        self.buf_time = config.record.saving_buf_time
        self.buf_pipe = mp.Queue()
        self.save_flag = False
        self.is_running = True
        self.save_process = None

    def start(self, saving_mode: int):
        clear_pipe(self.cmd_pipe)
        self.is_running = True
        self.save_flag = False
        self.save_process = mp.Process(target=self._handler, args=(saving_mode,), daemon=True)
        self.save_process.start()

    def start_ffmpeg(self, saving_mode: int):
        self.save_process = mp.Process(target=self._ffmpeg_handler, args=(saving_mode,), daemon=True)
        self.save_process.start()

    def close(self):
        clear_pipe(self.cmd_pipe)
        self.is_running = False
        self.save_flag = False
        self.cmd_pipe.put('stop')
        try:
            self.save_process.join()
            self.save_process.close()
        except Exception:
            logger.info("Process already closed")
            return
        logger.info("Video recording module stopped")

    def _ffmpeg_handler(self, saving_mode):
        self.is_running = True
        self.save_flag = False
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        if saving_mode == CAPTURE_ALWAYS_SAVE:
            logger.info("Video recording module started: FFmpeg, Always save")
            self.save_flag = True
            saving_thread = threading.Thread(target=self._save_ffmpeg, args=(self.cam_pipe,), daemon=True)
            saving_thread.start()
            while True:
                cmd = self.cmd_pipe.get()
                if cmd == 'stop':
                    self.is_running = False
                self.save_flag = False
                clear_pipe(self.cam_pipe)
                saving_thread.join()
                break
        else:
            logger.info("Video recording module started: FFmpeg, Save when motion detected")
            save_pipe = mp.Queue()
            saving_thread = threading.Thread(target=self._save_ffmpeg, args=(save_pipe,), daemon=True)
            saving_thread.start()
            span_start = 0
            cmd = ""
            while True:
                try:
                    cmd = self.cmd_pipe.get_nowait()
                except queue.Empty:
                    pass
                try:
                    frame, status = self.cam_pipe.get(timeout=2)
                    if status:
                        span_start = 0
                        self.save_flag = True
                    else:
                        if self.save_flag:
                            if span_start == 0:
                                span_start = time.time()
                            if time.time() - span_start > 5:
                                self.save_flag = False
                        else:
                            continue
                    clear_pipe(save_pipe, 2)
                    save_pipe.put((frame, status))
                except queue.Empty:
                    pass
                if cmd == 'stop':
                    self.is_running = False
                    self.save_flag = False
                    clear_pipe(self.cam_pipe)
                    clear_pipe(save_pipe)
                    saving_thread.join()
                    break

    def _handler(self, saving_mode):
        self.is_running = True
        read_thread = threading.Thread(target=self._read_stream, daemon=True)
        read_thread.start()
        if saving_mode == CAPTURE_ALWAYS_SAVE:
            logger.info("Video recording module started: OpenCV, Always save")
            self.save_flag = True
            save_thread = threading.Thread(target=self._save, daemon=True)
            save_thread.start()
        else:
            logger.info("Video recording module started: OpenCV, Save when motion detected")
        while True:
            cmd = self.cmd_pipe.get()
            if saving_mode == CAPTURE_SAVE_WHEN_MOVING and cmd == 'alarm':
                self.save_flag = True
                read_thread = threading.Thread(target=self._save, daemon=True)
                read_thread.start()
            elif saving_mode == CAPTURE_SAVE_WHEN_MOVING and cmd == 'alarm_canceled':
                self.save_flag = False
            elif cmd == 'stop':
                self.is_running = False
                self.save_flag = False
                time.sleep(3)
                return

    def _save_ffmpeg(self, cam_pipe: mp.Queue):
        logger.info("Saving module started")
        frame, status = self.cam_pipe.get()
        resolution = (frame.shape[1], frame.shape[0])
        ffmpeg_cmd = ['ffmpeg',
                      '-thread_queue_size', '16',
                      '-y',
                      '-f', 'rawvideo',
                      '-rtbufsize', '50M',
                      '-vcodec', 'rawvideo',
                      '-pix_fmt', 'bgr24',
                      '-s', "{}x{}".format(resolution[0], resolution[1]),
                      '-r', str(self.fps),
                      '-i', '-',
                      '-f', 'pulse',
                      '-ac', '2',
                      '-rtbufsize', '10M',
                      '-i', 'default',
                      '-c:v', 'libx264',
                      '-c:a', 'aac',
                      '-pix_fmt', 'yuv420p',
                      '-preset', 'ultrafast',
                      '-tune:v', 'zerolatency',
                      '-tune:a', 'zerolatency',
                      '-f', 'flv',
                      './video/%s.avi' % time.strftime("%Y-%m-%d_%H-%M-%S")]
        while self.is_running:
            if self.save_flag:
                logger.info("Recording started...")
                last_hour = time.strftime("%H")
                ffmpeg_cmd[-1] = 'video/%s.avi' % time.strftime("%Y-%m-%d_%H-%M-%S")
                ffmpeg_process = sp.Popen(ffmpeg_cmd, stdin=sp.PIPE, stdout=sp.PIPE)
                while self.save_flag and self.is_running:
                    try:
                        frame, status = cam_pipe.get_nowait()
                        ffmpeg_process.stdin.write(frame.tostring())
                    except queue.Empty:
                        pass
                    if time.strftime("%H") != last_hour:
                        ffmpeg_process.send_signal(signal.SIGINT)
                        ffmpeg_process.communicate()
                        ffmpeg_process.wait()
                        ffmpeg_cmd[-1] = 'video/%s.avi' % time.strftime("%Y-%m-%d_%H-00-00")
                        ffmpeg_process = sp.Popen(ffmpeg_cmd, stdin=sp.PIPE)
                        last_hour = time.strftime("%H")
                logger.info("Recording stopped")
                ffmpeg_process.send_signal(signal.SIGINT)
                ffmpeg_process.communicate()
                ffmpeg_process.wait()
            else:
                time.sleep(0.1)

        logger.info("Saving module stopped")

    def _save(self):
        frame = self.buf_pipe.get()
        resolution = (frame.shape[1], frame.shape[0])
        fourcc = cv2.VideoWriter_fourcc(*'XVID')
        writer = cv2.VideoWriter('video/%s.avi' % time.strftime("%Y-%m-%d_%H-%M-%S"), fourcc, self.fps, resolution)
        last_hour = time.strftime("%H")
        while self.save_flag:
            try:
                frame = self.buf_pipe.get(timeout=1)
            except:
                continue
            writer.write(frame)
            if time.strftime("%H") != last_hour:
                writer.release()
                writer = cv2.VideoWriter('video/%s.avi' % time.strftime("%Y-%m-%d_%H-00-00"), fourcc, self.fps,
                                         resolution)
                last_hour = time.strftime("%H")
        while self.buf_pipe.qsize() != 0:
            frame = self.buf_pipe.get()
            writer.write(frame)
        writer.release()

    def _read_stream(self):
        t_prev_frame = 0
        while self.is_running:
            try:
                frame, status = self.cam_pipe.get(timeout=1)
            except queue.Empty:
                continue
            t_curr_frame = time.time()
            dur = (t_curr_frame - t_prev_frame) * self.fps
            count = int(dur)
            if t_prev_frame == 0:
                count = 1
            for i in range(count):
                self.buf_pipe.put(frame)
                t_prev_frame = time.time()
            while not self.save_flag and self.buf_pipe.qsize() > self.buf_time * self.fps:
                self.buf_pipe.get()
