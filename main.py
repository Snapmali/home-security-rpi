import json
import multiprocessing as mp
import queue
import threading
import time
from typing import List, Union

import cv2
import numpy as np

import config
import log
import net_conn
import wifi_manager
from bluetooth_service import BluetoothService
from camera_capture import CameraCapture
from net_conn import NetConn, Status
from sensors import SensorAlarm, SensorMonitoring
from stream_pusher import StreamPusher
from video_recorder import VideoRecorder


logger = log.main_logger

INIT = 1
START_STREAMING = 2
STOP_STREAMING = 3
START_MONITORING = 4
STOP_MONITORING = 5
BINDING = 6
UNBINDING = 7

CAPTURE_ALWAYS_SAVE = 1
CAPTURE_SAVE_WHEN_MOVING = 2


class Main(object):
    config = None

    def __init__(self):
        self.cam_pipes = [mp.Queue() for _ in range(2)]
        self.alarm_pipe = mp.Queue()
        self.bt_pipe = mp.Queue()
        self.ws_recv_pipe = mp.Queue()

        self.camera_capture = CameraCapture(0, self.cam_pipes)
        self.sensor_monitor = SensorMonitoring(self.alarm_pipe)
        self.stream_pusher = StreamPusher(self.cam_pipes[0])
        self.net_conn = NetConn(self.ws_recv_pipe)
        self.video_recorder = VideoRecorder(self.cam_pipes[1])
        self.bt_service = BluetoothService(self.bt_pipe)

        self.connected = False
        self.is_monitoring = False
        self.is_streaming = False
        self.is_reconnecting = False
        self.capture_save_mode = 0

    def run(self):
        logger.info("Booting...")
        self.bt_service.start()
        thread_status_report = threading.Thread(target=self.ws_status_report, daemon=True)
        thread_recv = threading.Thread(target=self.ws_recv_handler, daemon=True)
        thread_alarm = threading.Thread(target=self.sensor_alarm_handler, args=(self.cam_pipes[0],),
                                        daemon=True)
        thread_bt_msg = threading.Thread(target=self.bt_message_handler, daemon=True)
        update_auth_thread = threading.Thread(target=self._update_auth, daemon=True)
        update_auth_thread.start()
        thread_status_report.start()
        thread_recv.start()
        thread_alarm.start()
        thread_bt_msg.start()
        logger.info("Connecting to wifi")
        if wifi_manager.connect_wifi():
            self.connected = True
            logger.info("Wifi connected, trying to start the net module")
            status = self.net_conn.start()
            while status is not net_conn.STATUS_SUCCESS:
                logger.warning("Failed to login")
                time.sleep(5)
                status = self.net_conn.start()
            logger.info("Net module started")
        else:
            logger.warning("Failed to connect to wifi")
        while True:
            time.sleep(5)
            if not self.is_reconnecting:
                if not wifi_manager.is_connected():
                    logger.debug("Disconnected, trying to reconnect to wifi")
                    self.stop_net_modules(send_status=False)
                    self.connected = False
                    if wifi_manager.connect_wifi():
                        logger.debug("Reconnected to wifi")
                if wifi_manager.is_connected() and not self.connected:
                    logger.debug("Trying to restart the net module")
                    if self.net_conn.start() == net_conn.STATUS_SUCCESS:
                        self.connected = True
                        logger.info("Net module restarted")

    def _update_auth(self):
        logger.debug("Token updater started")
        while True:
            if self.net_conn.is_running and net_conn.host and net_conn.host.token_expr - time.time() <= 21600:
                logger.info("Token expired, trying to renew the token")
                net_conn.login()
                self.net_conn.wsClient.restart()
                logger.info("Token renewing finished")
            else:
                time.sleep(3600)

    def sensor_alarm_handler(self, frame_pipe: mp.Queue):
        logger.debug("Alarm handler started")
        while True:
            alarm: SensorAlarm = self.alarm_pipe.get()
            alarm_act_t = time.time()
            frame = np.zeros((480, 640), np.uint8)
            if alarm.cate == 1:
                flag = False
                while not flag and time.time() - alarm_act_t <= 1.0:
                    try:
                        frame, status = frame_pipe.get(timeout=0.5)
                        if status == 'error':
                            continue
                        flag = status[0]
                    except queue.Empty:
                        continue
                if flag:
                    logger.info("Sending motion alarm with an image of the moving object")
                else:
                    logger.info("Sending motion alarm with an image that doesn't contain moving object")
            else:
                try:
                    frame, status = frame_pipe.get(timeout=0.5)
                except queue.Empty:
                    frame = np.zeros((480, 640), np.uint8)
                logger.info("Sending smoke alarm")
            _, frame_byte = cv2.imencode('.jpg', frame)
            t = threading.Thread(target=net_conn.push_alarm, args=(alarm, frame_byte), daemon=True)
            t.start()

    def bt_message_handler(self):
        logger.debug("Bluetooth message handler started")
        while True:
            message = self.bt_pipe.get()
            logger.info("Bluetooth message received: %s" % message)
            try:
                cmd = message["type"]
                if cmd == 1:
                    ssid: str = message["ssid"]
                    akm: List[str] = message["key_management"]
                    cipher: str = message["cipher"]
                    try:
                        password: Union[str, None] = message["wifi_password"]
                    except KeyError:
                        password = None
                    user_id: int = message["user_id"]
                    # connect to wifi or bind user
                    if config.config.bond_user == 0 or config.config.bond_user == user_id:
                        self.bt_service.send_binding_status(config.config.bond_user != 0)
                        self.is_reconnecting = True
                        self.stop_net_modules()
                        connection_result = wifi_manager.connect_new_wifi(ssid, akm, cipher, password)
                        self.bt_service.send_wifi_message(connection_result)
                        if connection_result is wifi_manager.SUCCESS:
                            logger.info("Connect to wifi successfully")
                            net_status = self.net_conn.start()
                            self.bt_service.send_login_status(net_status)
                            if net_status == net_conn.STATUS_SUCCESS:
                                logger.info("Connected to the server")
                                if config.config.bond_user == 0:
                                    bind_result = net_conn.bind_user(user_id)
                                    if bind_result == net_conn.STATUS_SUCCESS:
                                        logger.info("Binding succeed")
                                    else:
                                        logger.warning("Binding failed, code %d" % bind_result)
                                    self.bt_service.send_bind_message(bind_result)
                            else:
                                logger.warning("Failed to connect to the server")
                        else:
                            logger.warning("Failed to connect to wifi")
                        self.is_reconnecting = False
                        self.bt_service.command_done()
                    else:
                        logger.warning("Device is not bound to this user and cannot be operated")
                        self.bt_service.send_unbound_message()
                        self.bt_service.command_done()
            except KeyError:
                logger.warning("Failed to decode the bluetooth message")
                self.bt_service.command_done()
                self.bt_service.close_connection()

    def ws_recv_handler(self):
        logger.debug("WebSocket message handler started")
        while True:
            msg = self.ws_recv_pipe.get()
            data = json.loads(msg)
            try:
                cmd = data["type"]
                payload = data["payload"]
                if cmd == INIT:
                    logger.info("Initialization message received: %s" % msg)
                    config.config.bond_user = payload["user_id"]
                    config.update_config()
                elif cmd == START_STREAMING:
                    logger.info("Start streaming message received: %s" % msg)
                    if not self.stream_pusher.is_streaming():
                        key = payload["key"]
                        self.stream_pusher.start(key=key)
                    self.send_status()
                elif cmd == STOP_STREAMING:
                    logger.info("Stop streaming message received: %s" % msg)
                    if self.stream_pusher.is_streaming():
                        self.stream_pusher.stop()
                    self.send_status()
                elif cmd == START_MONITORING:
                    logger.info("Start monitoring message received: %s" % msg)
                    if not self.is_monitoring:
                        self.is_monitoring = True
                        self.capture_save_mode = payload["save_mode"]
                        self.camera_capture.start()
                        self.sensor_monitor.start()
                        self.video_recorder.start_ffmpeg(self.capture_save_mode)
                    self.send_status()
                elif cmd == STOP_MONITORING:
                    logger.info("Stop monitoring received: %s" % msg)
                    if self.is_monitoring:
                        self.is_monitoring = False
                        self.is_streaming = False
                        self.capture_save_mode = 0
                        self.video_recorder.close()
                        self.stream_pusher.stop()
                        self.camera_capture.close()
                        self.sensor_monitor.close()
                    self.send_status()
                elif cmd == UNBINDING:
                    logger.info("Unbind message received: %s" % msg)
                    self.stop_net_modules()
                    config.config.bond_user = 0
                    config.update_config()
            except KeyError:
                continue

    def stop_net_modules(self, send_status=True):
        logger.info("Stopping network related modules")
        if self.is_monitoring:
            self.is_monitoring = False
            self.capture_save_mode = 0
            self.video_recorder.close()
            self.stream_pusher.stop()
            self.camera_capture.close()
            self.sensor_monitor.close()
        if send_status:
            self.send_status()
        self.net_conn.close()

    def ws_status_report(self):
        while True:
            if self.net_conn.is_running:
                self.send_status()
            time.sleep(10)

    def send_status(self):
        status = Status(
            monitoring=self.is_monitoring,
            streaming=self.stream_pusher.is_streaming()
        )
        logger.debug("Sending status: monitoring %s, streaming %s" % (status.monitoring, status.streaming))
        self.net_conn.ws_status_report(status)


def main():
    m = Main()
    m.run()


if __name__ == '__main__':
    main()
