import multiprocessing as mp
import time
from queue import Empty
from typing import List

import cv2
import numpy as np

import config
import log
from movement_detection import MovementDetection
from util import clear_pipe

logger = log.capture_logger


class CameraCapture(object):

    def __init__(self, camera_num: int, output_frame_pipes: List[mp.Queue]):
        self.camera_num = camera_num
        self.fps = config.capture.fps
        self.get_cap_process = None
        self.output_process = None
        self.frame_processors = []
        self.output_frame_pipes = output_frame_pipes
        self.resolution = None
        self.cmd_pipes = [mp.Queue() for _ in range(3)]

    def get_resolution(self):
        return self.resolution.copy() if self.resolution else None

    def start(self):
        for pipe in self.cmd_pipes:
            clear_pipe(pipe)

        logger.info("Starting camera modules...")

        source_pipe4output = mp.Queue()
        source_pipes4processing = [mp.Queue() for _ in range(1)]
        processed_pipes = [mp.Queue() for _ in range(1)]

        self.get_cap_process = mp.Process(target=self._get_cap_frame,
                                          args=(self.camera_num, source_pipes4processing, source_pipe4output, self.cmd_pipes[0]))
        self.output_process = mp.Process(target=_output_frame,
                                         args=(source_pipe4output, processed_pipes, self.output_frame_pipes, self.cmd_pipes[1]))
        self.get_cap_process.daemon = True
        self.output_process.daemon = True

        self.frame_processors = [
            mp.Process(target=_mov_detector, args=(source_pipes4processing[0], processed_pipes[0], self.cmd_pipes[2]))
        ]
        self.get_cap_process.start()
        self.output_process.start()
        for process in self.frame_processors:
            process.daemon = True
            process.start()

    def close(self):
        logger.info("Stopping camera modules...")
        for pipe in self.cmd_pipes:
            clear_pipe(pipe)
            pipe.put('stop')
        try:
            self.get_cap_process.join()
            self.get_cap_process.close()
            self.output_process.join()
            self.output_process.close()
            for p in self.frame_processors:
                p.join()
                p.close()
        except Exception:
            logger.info("Process already closed")
            return
        logger.info("Camera modules all stopped")

    def _get_cap_frame(self, camera_num: int, source_pipes4processing: List[mp.Queue], source_pipe4output: mp.Queue, cmd_pipe: mp.Queue, restart_on_err=False):
        logger.info("Capture module started")
        camera = cv2.VideoCapture(camera_num)
        while not camera.isOpened():
            logger.error("Camera failed to start!")
            if restart_on_err:
                camera.release()
                time.sleep(2)
                camera = cv2.VideoCapture(camera_num)
            else:
                self.close()
                for pipe in source_pipes4processing:
                    clear_pipe(pipe)
                clear_pipe(source_pipe4output)
                return
        logger.info("Camera %d is activated." % camera_num)
        resolution_hw = (int(camera.get(cv2.CAP_PROP_FRAME_HEIGHT)), int(camera.get(cv2.CAP_PROP_FRAME_WIDTH)), 3)
        fps = int(camera.get(cv2.CAP_PROP_FPS))
        logger.info('Resolution: %d x %d | Input fps: %d | Output fps: %d' %
                    (resolution_hw[1], resolution_hw[0], fps, config.capture.fps))

        start = time.time()
        initialing = True
        failure_times = 0
        logger.info("Fetching frames from camera")
        frame_time = 1 / config.capture.fps
        while True:
            start_time = time.time()
            try:
                cmd = cmd_pipe.get_nowait()
                if cmd == 'stop':
                    camera.release()
                    logger.info("Camera module stopped")
                    for pipe in source_pipes4processing:
                        clear_pipe(pipe)
                    clear_pipe(source_pipe4output)
                    break
            except Empty:
                pass

            res, frame = camera.read()
            if res:
                if not initialing or time.time() - start > 5:
                    initialing = False
                    for pipe in source_pipes4processing:
                        clear_pipe(pipe, 2)
                        pipe.put(frame)
                clear_pipe(source_pipe4output, 2)
                source_pipe4output.put(frame)
                failure_times = 0
            else:
                logger.warning("Failed to get frame from camera")
                failure_times += 1
                if failure_times > 1:
                    time.sleep(2)
                    logger.info("Trying to restart the capture module")
                    camera.release()
                    self._get_cap_frame(camera_num, source_pipes4processing, source_pipe4output, cmd_pipe, restart_on_err=True)
                    return
            end_time = time.time()
            if end_time - start_time < frame_time:
                time.sleep(frame_time - (end_time - start_time))


def _mov_detector(source_pipe: mp.Queue, contours_pipe: mp.Queue, cmd_pipe: mp.Queue):
    logger.info("Motion detector module started")
    frame = source_pipe.get()
    md = MovementDetection(frame)
    while True:
        try:
            cmd = cmd_pipe.get_nowait()
            if cmd == 'stop':
                logger.info("Motion detector module stopped")
                clear_pipe(source_pipe)
                clear_pipe(contours_pipe)
                break
        except Empty:
            pass
        try:
            frame = source_pipe.get(timeout=1)
            contours_frame, flag = md.get_contours4show(frame)
            clear_pipe(contours_pipe, 2)
            contours_pipe.put((contours_frame, flag))
        except Empty:
            pass


def _output_frame(source_pipe4output: mp.Queue, processed_frame_pipes: List[mp.Queue], output_pipes: List[mp.Queue], cmd_pipe: mp.Queue):
    logger.info("Output module started")
    frame = source_pipe4output.get()
    pipes_frame = [np.zeros(frame.shape, np.uint8) for i in range(len(processed_frame_pipes))]
    pipes_flag = [False for i in range(len(processed_frame_pipes))]
    status = tuple(pipes_flag)
    error_frame = np.zeros(frame.shape, np.uint8)
    cv2.putText(error_frame, 'NO SIGNAL', (20, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
    frame_update_time = time.time()
    overlay_update_time = [time.time() for i in range(len(processed_frame_pipes))]
    error_state = False
    error_start_time = 0
    frame_time = 1 / config.capture.fps
    while True:
        start_time = time.time()
        try:
            cmd = cmd_pipe.get_nowait()
            if cmd == 'stop':
                logger.info("Output module stopped")
                clear_pipe(source_pipe4output)
                for pipe in processed_frame_pipes:
                    clear_pipe(pipe)
                for pipe in output_pipes:
                    clear_pipe(pipe)
                break
        except Empty:
            pass
        try:
            frame = source_pipe4output.get_nowait()
            error_state = False
            cur_time_str = time.strftime("%Y/%m/%d %H:%M:%S")
            # cv2.putText(frame, 'refresh_span: %.3f' % (t - frame_update_time), (4, frame.shape[0] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            cv2.putText(frame, cur_time_str, (4, frame.shape[0] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2,
                        cv2.LINE_AA)
            cv2.putText(frame, cur_time_str, (4, frame.shape[0] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1,
                        cv2.LINE_AA)
            for i in range(len(processed_frame_pipes)):
                q = processed_frame_pipes[i]
                t = time.time()
                span = t - overlay_update_time[i]
                try:
                    pipes_frame[i], pipes_flag[i] = q.get_nowait()
                    overlay_update_time[i] = t
                    cv2.putText(pipes_frame[i], 'span %d: %.3f' % (i, span), (4, 13 + i * 14), cv2.FONT_HERSHEY_SIMPLEX,
                                0.5, (0, 255, 0), 1)
                except Empty:
                    if span > 1:
                        pipes_frame[i] = np.zeros(frame.shape, np.uint8)
                        pipes_flag[i] = False
                frame = cv2.addWeighted(frame, 1.0, pipes_frame[i], 0.5, 0)
                status = tuple(pipes_flag)
        except Empty:
            if not error_state:
                error_state = True
                error_start_time = time.time()
            else:
                if time.time() - error_start_time >= 2:
                    logger.debug("Failed to get source frame!")
                    frame = error_frame
                    status = "error"
                    for q in processed_frame_pipes:
                        if not q.empty():
                            q.get()
        for pipe in output_pipes:
            clear_pipe(pipe, 2)
            pipe.put((frame, status))
        end_time = time.time()
        if end_time - start_time < frame_time:
            time.sleep(frame_time - (end_time - start_time))


# For debugging
def main():
    cam_pipes = [mp.Queue() for i in range(2)]
    camera_capture = CameraCapture(0, cam_pipes)
    camera_capture.start()
    ct = time.time()
    while time.time() - ct < 10:
        frame, status = cam_pipes[0].get()
    camera_capture.close()
    time.sleep(5)
    camera_capture.start()
    ct = time.time()
    while time.time() - ct < 10:
        frame, status = cam_pipes[0].get()
    camera_capture.close()
    time.sleep(5)
    camera_capture.start()
    ct = time.time()
    while time.time() - ct < 10:
        frame, status = cam_pipes[0].get()
    camera_capture.close()
    time.sleep(5)
    camera_capture.start()
    ct = time.time()
    while time.time() - ct < 10:
        frame, status = cam_pipes[0].get()
    camera_capture.close()


if __name__ == '__main__':
    main()
