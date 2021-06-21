import logging
import time
import traceback
from typing import List, Union

import pywifi
from pywifi import const

import config
import log

logger = log.wifi_logger
pywifi.set_loglevel(logging.WARNING)
iface = pywifi.PyWiFi().interfaces()[1]

SUCCESS = 0
CONNECTION_FAILURE = 1
WIFI_NOT_FOUND = 2

akm_dict = {"NONE": const.AKM_TYPE_NONE, "WPA": const.AKM_TYPE_WPA, "WPA-PSK": const.AKM_TYPE_WPAPSK,
            "WPA2": const.AKM_TYPE_WPA2, "WPA2-PSK": const.AKM_TYPE_WPA2PSK}
cipher_dict = {"NONE": const.CIPHER_TYPE_NONE, "WEP": const.CIPHER_TYPE_WEP,
               "TKIP": const.CIPHER_TYPE_TKIP, "CCMP": const.CIPHER_TYPE_CCMP}


def connect_new_wifi(ssid: str, akm_list: List[str], cipher: str, password: Union[str, None]) -> int:
    logger.debug("Connecting to wifi")
    iface.disconnect()
    config.clear_wifi_profile()
    iface.remove_all_network_profiles()
    time.sleep(3)
    profile = pywifi.Profile()
    try:
        profile.ssid = ssid
        profile.auth = const.AUTH_ALG_OPEN
        for akm in akm_list:
            profile.akm.append(akm_dict[akm])
        profile.cipher = cipher_dict[cipher]
        profile.key = password
        iface.add_network_profile(profile)
        iface.connect(profile)
        if _connect_wifi_with_profile(profile):
            config.update_wifi_profile(ssid, profile.akm, profile.cipher, password)
            return SUCCESS
        else:
            return CONNECTION_FAILURE
    except KeyError:
        traceback.print_stack()
        if iface.status() != const.IFACE_CONNECTED:
            logger.warn("Failed to connect to wifi")
            return CONNECTION_FAILURE


def connect_wifi() -> bool:
    logger.info("Connecting to wifi")
    if iface.status() == const.IFACE_CONNECTED:
        logger.info("Already connected to wifi")
        return True
    if config.wifi_profile.ssid != "":
        iface.remove_all_network_profiles()
        profile = pywifi.Profile()
        profile.ssid = config.wifi_profile.ssid
        profile.auth = const.AUTH_ALG_OPEN
        profile.akm = config.wifi_profile.akm
        profile.cipher = config.wifi_profile.cipher
        profile.key = config.wifi_profile.password
        iface.add_network_profile(profile)
        return _connect_wifi_with_profile(profile)
    else:
        logger.info("No saved wifi")
        return False


def _connect_wifi_with_profile(profile: pywifi.Profile) -> bool:
    iface.connect(profile)
    count = 0
    while iface.status() is not const.IFACE_CONNECTED:
        if iface.status() == const.IFACE_CONNECTING:
            time.sleep(1)
        else:
            if count >= 3:
                break
            count += 1
            time.sleep(1)
    if iface.status() == const.IFACE_CONNECTED:
        logger.info("Successfully connected to the wifi: %s" % profile.ssid)
        return True
    logger.warn("Failed to connect to the wifi: %s" % profile.ssid)
    return False


def is_connected():
    return iface.status() == const.IFACE_CONNECTED
