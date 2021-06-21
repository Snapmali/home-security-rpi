import json
from json import JSONEncoder
from typing import List, Union


class Config:

    def __init__(self, data: dict):
        self.bond_user: int = data["bond_user"]

        self.capture = Config._Capture(data["capture"])
        self.http = Config._Http(data["http"])
        self.record = Config._Record(data["record"])
        self.sensor = Config._Sensor(data["sensor"])
        self.stream = Config._Stream(data["stream"])
        self.websocket = Config._Websocket(data["websocket"])

    class _Capture:
        def __init__(self, data: dict):
            self.fps: int = data["fps"]

    class _Http:
        def __init__(self, data: dict):
            self.base_url: str = data["base_url"]

    class _Record:
        def __init__(self, data: dict):
            self.fps: int = data["fps"]
            self.saving_buf_time: int = data["saving_buf_time"]

    class _Sensor:
        def __init__(self, data: dict):
            self.motion_gpio: int = data["motion_gpio"]
            self.smoke_gpio: int = data["smoke_gpio"]
            self.buzzer_gpio: int = data["buzzer_gpio"]

    class _Stream:
        def __init__(self, data: dict):
            self.rtmp_url: str = data["rtmp_url"]
            self.ffmpeg_cmd: str = data["ffmpeg_cmd"]
            self.fps: int = data['fps']
            self.resolution: List[int] = data["resolution"]

    class _Websocket:
        def __init__(self, data: dict):
            self.base_url: str = data["base_url"]


class _JsonEncoder(JSONEncoder):
    def default(self, o):
        return o.__dict__


def read_config() -> Config:
    with open('./config.json', 'r', encoding='utf8') as f:
        return Config(json.load(f))


def update_config():
    with open('./config.json', 'r+', encoding='utf8') as f:
        f.seek(0)
        f.truncate()
        f.write(json.dumps(config, indent=4, cls=_JsonEncoder, ensure_ascii=False))


class WifiProfile:
    def __init__(self, data: dict):
        self.ssid: str = data["ssid"]
        self.akm: List[int] = data["akm"]
        self.cipher: int = data["cipher"]
        self.password: str = data["password"]


def read_wifi_profile() -> WifiProfile:
    with open('./wifi_profile.json', 'r', encoding='utf-8') as f:
        return WifiProfile(json.load(f))


def _update_wifi_profile_file():
    with open('./wifi_profile.json', 'r+', encoding='utf-8') as f:
        f.seek(0)
        f.truncate()
        f.write(json.dumps(wifi_profile, indent=4, cls=_JsonEncoder, ensure_ascii=False))


def clear_wifi_profile():
    wifi_profile.ssid = ""
    wifi_profile.akm = []
    wifi_profile.cipher = 0
    wifi_profile.password = ""
    _update_wifi_profile_file()


def update_wifi_profile(ssid: str, akm: List[int], cipher: int, password: str):
    wifi_profile.ssid = ssid
    wifi_profile.akm = akm
    wifi_profile.cipher = cipher
    wifi_profile.password = password
    _update_wifi_profile_file()


config = read_config()
wifi_profile = read_wifi_profile()

capture = config.capture
http = config.http
record = config.record
sensor = config.sensor
stream = config.stream
websocket = config.websocket
