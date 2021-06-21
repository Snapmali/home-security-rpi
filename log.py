import logging.handlers
import os

if not os.path.exists("./log"):
    os.makedirs("./log")

LOG_FORMAT = "[%(asctime)s][%(levelname)s][%(name)s]%(message)s"
DATE_FORMAT = "%Y/%m/%d %H:%M:%S"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt=DATE_FORMAT)
formatter = logging.Formatter("[%(asctime)s][%(levelname)s][%(name)s]%(message)s", datefmt="%Y/%m/%d %H:%M:%S")

main_logger = logging.getLogger("Main")
file_handler = logging.handlers.TimedRotatingFileHandler('./log/main.log', when='midnight', interval=1, backupCount=7)
file_handler.setFormatter(formatter)
file_handler.suffix = "%Y-%m-%d_%H-%M-%S.log"
main_logger.addHandler(file_handler)

ws_logger = logging.getLogger("WebSocket")
file_handler = logging.handlers.TimedRotatingFileHandler('./log/websocket_service.log', when='midnight', interval=1, backupCount=7)
file_handler.setFormatter(formatter)
file_handler.suffix = "%Y-%m-%d_%H-%M-%S.log"
ws_logger.addHandler(file_handler)

wifi_logger = logging.getLogger("WifiManager")
file_handler = logging.handlers.TimedRotatingFileHandler('./log/wifi_manager.log', when='midnight', interval=1, backupCount=7)
file_handler.setFormatter(formatter)
file_handler.suffix = "%Y-%m-%d_%H-%M-%S.log"
wifi_logger.addHandler(file_handler)

sensor_logger = logging.getLogger("Sensors")
file_handler = logging.handlers.TimedRotatingFileHandler('./log/sensors.log', when='midnight', interval=1, backupCount=7)
file_handler.setFormatter(formatter)
file_handler.suffix = "%Y-%m-%d_%H-%M-%S.log"
sensor_logger.addHandler(file_handler)

bt_logger = logging.getLogger("BluetoothService")
file_handler = logging.handlers.TimedRotatingFileHandler('./log/bluetooth_service.log', when='midnight', interval=1, backupCount=7)
file_handler.setFormatter(formatter)
file_handler.suffix = "%Y-%m-%d_%H-%M-%S.log"
bt_logger.addHandler(file_handler)

net_logger = logging.getLogger("NetConn")
file_handler = logging.handlers.TimedRotatingFileHandler('./log/net_conn.log', when='midnight', interval=1, backupCount=7)
file_handler.setFormatter(formatter)
file_handler.suffix = "%Y-%m-%d_%H-%M-%S.log"
net_logger.addHandler(file_handler)

capture_logger = logging.getLogger("CameraCapture")
file_handler = logging.handlers.TimedRotatingFileHandler('./log/camera_capture.log', when='midnight', interval=1, backupCount=7)
file_handler.setFormatter(formatter)
file_handler.suffix = "%Y-%m-%d_%H-%M-%S.log"
capture_logger.addHandler(file_handler)

stream_logger = logging.getLogger("StreamPusher")
file_handler = logging.handlers.TimedRotatingFileHandler('./log/stream_pusher.log', when='midnight', interval=1, backupCount=7)
file_handler.setFormatter(formatter)
file_handler.suffix = "%Y-%m-%d_%H-%M-%S.log"
stream_logger.addHandler(file_handler)

recorder_logger = logging.getLogger("VideoRecorder")
file_handler = logging.handlers.TimedRotatingFileHandler('./log/video_recorder.log', when='midnight', interval=1, backupCount=7)
file_handler.setFormatter(formatter)
file_handler.suffix = "%Y-%m-%d_%H-%M-%S.log"
recorder_logger.addHandler(file_handler)
