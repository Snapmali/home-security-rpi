import multiprocessing
import queue
import signal
import subprocess as sp

import config
import log
from util import clear_pipe

logger = log.stream_logger


class StreamPusher(object):

    def __init__(self, frame_pipe: multiprocessing.Queue):
        self.frame_pipe = frame_pipe
        self.rtmp_url = config.stream.rtmp_url
        self.key = ''
        self.resolution = tuple(config.stream.resolution)
        self.fps = config.stream.fps
        self.ffmpeg_cmd = config.stream.ffmpeg_cmd
        self.ffmpeg_process = None
        self.push_process = multiprocessing.Process()
        self._cmd_pipe = multiprocessing.Queue()

    def _push(self):
        logger.info('Streaming started')
        if self.key != '':
            rtmp_url = self.rtmp_url + '/' + self.key
        else:
            rtmp_url = self.rtmp_url
        if self.ffmpeg_cmd == '':
            ffmpeg_cmd = ['ffmpeg',
                          '-thread_queue_size', '16',
                          '-y',
                          '-f', 'rawvideo',
                          '-rtbufsize', '50M',
                          '-vcodec', 'rawvideo',
                          '-pix_fmt', 'bgr24',
                          '-s', "{}x{}".format(self.resolution[0], self.resolution[1]),
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
                          rtmp_url]
        else:
            ffmpeg_cmd = self.ffmpeg_cmd
        self.ffmpeg_process = sp.Popen(ffmpeg_cmd, stdin=sp.PIPE)
        while True:
            if not self.frame_pipe.empty():
                try:
                    frame, status = self.frame_pipe.get(timeout=1)
                    self.ffmpeg_process.stdin.write(frame.tostring())
                except queue.Empty:
                    pass
            try:
                cmd = self._cmd_pipe.get_nowait()
                if cmd == 'stop':
                    self.ffmpeg_process.send_signal(signal.SIGINT)
                    self.ffmpeg_process.communicate()
                    self.ffmpeg_process.wait()
                    break
            except queue.Empty:
                continue

    def is_streaming(self):
        try:
            return self.push_process.is_alive()
        except ValueError:
            return False

    def start(self, key=''):
        clear_pipe(self._cmd_pipe)
        self.key = key
        self.push_process = multiprocessing.Process(target=self._push)
        self.push_process.daemon = True
        self.push_process.start()

    def stop(self):
        clear_pipe(self._cmd_pipe)
        self._cmd_pipe.put('stop')
        try:
            self.push_process.join()
            self.push_process.close()
        except Exception:
            logger.info("Process already closed")
            return
        logger.info("Streaming stopped")
