import asyncio
import multiprocessing
import threading
import time
from queue import Empty

import websockets

import config
import log
import net_conn
from util import clear_pipe

logger = log.ws_logger

PING_INTERVAL = 5
PING_TIMEOUT = 10
CLOSE_TIMEOUT = 10
TIMEOUT = 5


class WsClient:

    def __init__(self, recv_pipe: multiprocessing.Queue):
        self.conn = None
        self._url = config.websocket.base_url + '/ws/home_host'
        self._process = None
        self._closed = False
        self._close_pipe = multiprocessing.Queue()
        self.send_pipe = multiprocessing.Queue()
        self.recv_pipe = recv_pipe
        self._loop = None
        self._loop_thread = None

    def start(self):
        self._closed = False
        self.conn = None
        clear_pipe(self._close_pipe)
        self._process = multiprocessing.Process(target=self._run_process)
        self._process.daemon = True
        self._process.start()

    def close(self):
        clear_pipe(self._close_pipe)
        self._close_pipe.put("close")
        self._closed = True
        try:
            self._process.join()
            self._process.close()
        except Exception:
            logger.info("Process already closed")
            return
        logger.info("WebSocket service stopped")

    def restart(self):
        logger.info("Restarting...")
        self.close()
        self.start()

    def send_msg(self, msg: str):
        self.send_pipe.put(msg)

    def _run_process(self):
        self._start_loop_thread()
        self._handle_close()

    def _start_loop_thread(self):
        self._closed = False
        self.conn = None
        self._loop = asyncio.new_event_loop()
        asyncio.ensure_future(self._connect(), loop=self._loop)
        asyncio.ensure_future(self._recv_loop(), loop=self._loop)
        asyncio.ensure_future(self._send_loop(), loop=self._loop)
        self._loop_thread = threading.Thread(target=self._start_loop, daemon=True)
        self._loop_thread.start()

    def _handle_close(self):
        while True:
            msg = self._close_pipe.get()
            if msg == "close":
                self._closed = True
                self._loop.call_soon_threadsafe(self._loop.create_task, self.conn.close())
                while not self.conn.closed:
                    time.sleep(0.5)
                break
            if msg == "closed":
                logger.warning("WebSocket service stopped unexpectedly, preparing to restart...")
                time.sleep(5)
                self._loop.call_soon_threadsafe(self._loop.create_task, self._connect())
                continue

    def _start_loop(self):
        self._loop.run_forever()

    async def _connect(self):
        try:
            self.conn = await websockets.connect(self._url,
                                                 ping_interval=PING_INTERVAL,
                                                 ping_timeout=PING_TIMEOUT,
                                                 close_timeout=CLOSE_TIMEOUT,
                                                 timeout=TIMEOUT,
                                                 extra_headers=(("Authorization", "Bearer " + net_conn.host.token),))
            self._closed = False
            logger.info("WebSocket service started")
        except:
            self._closed = True
            self._close_pipe.put("closed")
            logger.error("Failed to start WebSocket service")

    async def _recv_loop(self):
        while not self.conn:
            if self._closed:
                return
            await asyncio.sleep(1)
        logger.debug("Recv loop running")
        while True:
            if not self._closed:
                try:
                    msg = await self.conn.recv()
                    logger.info("Message received: %s" % msg)
                    self.recv_pipe.put(msg)
                except:
                    if not self._closed:
                        self._close_pipe.put("closed")
                        self._closed = True
            else:
                await asyncio.sleep(1)

    async def _send_loop(self):
        while not self.conn:
            if self._closed:
                return
            await asyncio.sleep(1)
        logger.debug("Send loop running")
        while True:
            if not self._closed:
                try:
                    msg: str = self.send_pipe.get(block=False)
                    asyncio.ensure_future(self._handle_send(msg))
                except Empty:
                    await asyncio.sleep(0.5)
            else:
                await asyncio.sleep(1)

    async def _handle_send(self, msg: str):
        logger.debug("Sending message: %s" % msg)
        while True:
            if not self._closed:
                for i in range(5):
                    try:
                        if self._closed:
                            break
                        await self.conn.send(msg)
                        logger.debug("Message sent: %s" % msg)
                        return
                    except:
                        pass
                if not self._closed:
                    logger.warning("Cannot send message, closing connection...")
                    self._close_pipe.put("closed")
                    self._closed = True
            else:
                await asyncio.sleep(1)


# For debugging
def main():
    url = "ws://echo.websocket.org"
    pipe = multiprocessing.Queue()
    wsc = WsClient(pipe)
    wsc.start()
    i = 0
    ct = time.time()
    while time.time() - ct < 10:
        i += 1
        wsc.send_msg("hello %d" % i)
        time.sleep(2)
    wsc.close()


if __name__ == '__main__':
    main()
