import json
import multiprocessing
import threading
import time

import bluetooth

import log
import net_conn
import wifi_manager
from util import clear_pipe

logger = log.bt_logger


class BluetoothService:

    def __init__(self, cmd_pipe: multiprocessing.Queue):
        self._uuid = "00001101-0000-1000-8000-00805F9B34FB"
        self._server_sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
        self._client_sock = None
        self._recv_pipe = cmd_pipe
        self._cmd_pipe = multiprocessing.Queue()
        self._is_connecting = False
        self._service_process = None
        self._processing_message = False

    def start(self):
        clear_pipe(self._cmd_pipe)
        self._service_process = multiprocessing.Process(target=self._start_service, daemon=True)
        self._service_process.start()

    def _start_service(self):
        self._is_connecting = False
        self._server_sock.bind(("", bluetooth.PORT_ANY))
        self._server_sock.listen(1)
        bluetooth.advertise_service(self._server_sock, "HomeSecurity", service_id=self._uuid,
                                    service_classes=[self._uuid, bluetooth.SERIAL_PORT_CLASS],
                                    profiles=[bluetooth.SERIAL_PORT_PROFILE])

        self._server_sock.settimeout(1)
        thread_recv = threading.Thread(target=self._cmd_handler, daemon=True)
        thread_recv.start()
        logger.info("Bluetooth service started")
        self._accept_connection()

    def close(self):
        clear_pipe(self._cmd_pipe)
        self._cmd_pipe.put("close")
        try:
            self._service_process.join()
            self._service_process.close()
        except Exception:
            logger.info("Process already closed")
            return
        logger.info("Bluetooth service stopped")

    def close_connection(self):
        self._cmd_pipe.put("close_connection")

    def command_done(self):
        self._cmd_pipe.put("done")

    def send_binding_status(self, bound: bool):
        if bound:
            message = {"type": 3, "message": "device is bound to the user", "code": 1}
        else:
            message = {"type": 3, "message": "device unbound", "code": 0}
        self._cmd_pipe.put(json.dumps(message))

    def send_unbound_message(self):
        message = {"type": 3, "message": "device is bound to another user", "code": 2}
        self._cmd_pipe.put(json.dumps(message))

    def send_wifi_message(self, code: int):
        message = {"type": 1, "code": code}
        if code == wifi_manager.SUCCESS:
            message["message"] = "success"
        elif code == wifi_manager.CONNECTION_FAILURE:
            message["message"] = "failed to connect to wifi"
        elif code == wifi_manager.WIFI_NOT_FOUND:
            message["message"] = "cannot find the wifi"
        self._cmd_pipe.put(json.dumps(message))

    def send_login_status(self, code: int):
        message = {"type": 4, "code": code}
        if code == net_conn.STATUS_SUCCESS:
            message["message"] = "success"
        else:
            message["message"] = "failed"
        self._cmd_pipe.put(json.dumps(message))

    def send_bind_message(self, code: int):
        message = {"type": 2, "code": code}
        if code == net_conn.STATUS_SUCCESS:
            message["message"] = "success"
        else:
            message["message"] = "failed to bind user"
        self._cmd_pipe.put(json.dumps(message))

    def _accept_connection(self):
        while True:
            try:
                self._client_sock, client_info = self._server_sock.accept()
                logger.info("Accepted connection from %s", client_info)
                self._is_connecting = True
                self._client_sock.settimeout(1)
                self._processing_message = False
                while True:
                    try:
                        data = self._client_sock.recv(1024)
                        if data:
                            logger.info("Received %s", data)
                            if not self._processing_message:
                                message = json.loads(data)
                                self._recv_pipe.put(message)
                                self._processing_message = True
                            else:
                                logger.info("Processing another message now, ignored")
                        else:
                            logger.debug("Empty message, ignored")
                    except json.JSONDecodeError as e:
                        logger.warning("Decode message error %s", e)
                        break
                    except OSError as e:
                        if str(e) == "timed out":
                            pass
                        else:
                            break
                logger.info("Disconnected")
                self._processing_message = False
                self._client_sock.close()
                self._is_connecting = False
            except OSError as e:
                if str(e) == "timed out":
                    pass
                else:
                    logger.info("Server socket is closed")
                    break

    def _cmd_handler(self):
        while True:
            cmd: str = self._cmd_pipe.get()
            if self._is_connecting and cmd == "close_connection":
                self._processing_message = False
                logger.info("Closing connection")
                self._client_sock.close()
            elif cmd == "done":
                self._processing_message = False
            elif cmd == "close":
                self._server_sock.close()
                break
            elif self._is_connecting:
                logger.info("Sending message: %s" % cmd)
                self._client_sock.send(cmd.encode(encoding="utf-8"))


# For debugging
def main():
    pipe = multiprocessing.Queue()
    bts = BluetoothService(pipe)
    bts.start()
    time.sleep(7)
    bts.close_connection()
    time.sleep(5)
    bts.close()


if __name__ == '__main__':
    main()
