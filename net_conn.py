import json
import multiprocessing
import time

import jwt
import requests

import config
import log
from sensors import SensorAlarm
from ws_client import WsClient

logger = log.net_logger

TYPE_STATUS = 1

STATUS_SUCCESS = 0


class Status(object):

    def __init__(self, monitoring=False, streaming=False):
        self.monitoring = monitoring
        self.streaming = streaming


class Host(object):
    def __init__(self, hostname: str, password: str):
        self.hostname = hostname
        self.password = password
        self.host_id = 0
        self.token = ""
        self.token_expr = 0


def _read_config():
    with open('./authorization.json', 'r', encoding='utf8') as f:
        auth_config = json.load(f)
        hostname: str = auth_config["hostname"]
        password: str = auth_config["password"]
        return hostname, password


_auth_config = _read_config()
host = Host(_auth_config[0], _auth_config[1])


class NetConn(object):

    def __init__(self, ws_recv_pipe: multiprocessing.Queue):
        self.wsClient = WsClient(ws_recv_pipe)
        self.ws_recv_pipe = self.wsClient.recv_pipe

        self.update_auth_thread = None
        self.is_running = False

    def start(self) -> int:
        if self.is_running:
            return STATUS_SUCCESS
        status = login()
        if status == STATUS_SUCCESS:
            self.is_running = True
            self.wsClient.start()
            return status
        else:
            return status

    def close(self):
        self.is_running = False
        self.wsClient.close()

    def ws_status_report(self, status: Status):
        data = {
            "type": TYPE_STATUS,
            "payload": {
                "monitoring": status.monitoring,
                "streaming": status.streaming
            }
        }
        data = json.dumps(data)
        self.wsClient.send_msg(data)


def push_alarm(alarm: SensorAlarm, frame: bytes) -> bool:
    data = {
        'host_id': host.host_id,
        'type': alarm.cate,
        'desc': alarm.desc,
        'time': alarm.time
    }
    data = {"data": json.dumps(data)}
    img_name = "%s%03d.jpg" % (time.strftime('%Y%m%d_%H%M%S', time.localtime(alarm.time)),
                               (alarm.time - int(alarm.time)) * 1000)
    files = {'img': (img_name, frame)}
    response = _post('/home_host/sensor_alarm', data=data, files=files)
    if response:
        if response.status_code == 200:
            logger.info("Push alarm succeed: %s" % data)
            return True
        elif response.status_code == 401:
            logger.warning("Token expired, renewing the token")
            if login():
                return push_alarm(alarm, frame)
        else:
            logger.warning("Push alarm failed, response: %s message: %s" % (response.text, data))
    logger.warning("Push alarm failed with no response, message: %s" % data)
    return False


def login() -> int:
    data = {"hostname": host.hostname, "password": host.password}
    response = _post("/auth/home_host/login", retry_times=1, json=data)
    if response:
        try:
            response_json = response.json()
            if response_json["code"] == STATUS_SUCCESS:
                host.token = response_json["token"]
                host.token_expr = jwt.decode(host.token, options={"verify_signature": False})['exp']
                host.host_id = response_json["host_id"]
                config.config.bond_user = response_json["user_id"]
                config.update_config()
                logger.info("Login succeed: %s" % response_json)
            else:
                logger.warning("Login failed, response: %s message: %s" % (response.text, data))
            return response_json["code"]
        except ValueError:
            logger.warning("Login failed, response: %s message: %s" % (response.text, data))
            return response.status_code
    else:
        logger.warning("Login failed with no response, message: %s" % data)
        return -1


def bind_user(user_id: int) -> int:
    data = {"host_id": host.host_id, "user_id": user_id}
    response = _post("/home_host/binding", retry_times=-1, json=data)
    if response:
        try:
            response_json = response.json()
            if response_json["code"] == STATUS_SUCCESS:
                config.config.bond_user = user_id
                config.update_config()
                logger.info("Bind user succeed: %s" % data)
            elif response.status_code == 401:
                logger.warning("Token expired, renewing the token")
                if login():
                    return bind_user(user_id)
            else:
                logger.warning("Bind user failed, response: %s message: %s" % (response.text, data))
            return response_json["code"]
        except ValueError:
            logger.warning("Bind user failed, response: %s message: %s" % (response.text, data))
            return response.status_code
    else:
        logger.warning("Bind user failed with no response, message: %s" % data)
        return -1


def _post(path: str, retry_times=5, **kwargs):
    url = config.http.base_url + path
    headers = dict()
    if host.token != "":
        headers["Authorization"] = "Bearer " + host.token
    i = 0
    while True:
        try:
            response = requests.request('POST', url, headers=headers, timeout=(10, 10), **kwargs)
            return response
        except:
            time.sleep(5)
        i += 1
        if retry_times != -1 and i > 5:
            return None
