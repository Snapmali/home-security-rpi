import multiprocessing as mp
import time

from gpiozero import MotionSensor, Buzzer, DigitalInputDevice

import log
import config

logger = log.sensor_logger

MOTION_ALARM = 1
SMOKE_ALARM = 2


class SensorAlarm(object):
    def __init__(self, alarm_type: int, alarm_desc: str, alarm_time: float):
        self.cate = alarm_type
        self.desc = alarm_desc
        self.time = alarm_time


class SensorMonitoring(object):

    def __init__(self, pipe: mp.Queue):
        self.alarm_pipe = pipe
        self.motion_GPIO = config.sensor.motion_gpio
        self.smoke_GPIO = config.sensor.smoke_gpio
        self.buzzer_GPIO = config.sensor.buzzer_gpio
        self.process = None
        self.ms_is_activated = False
        self.ms_activation_time = 0
        self.ms_activation_count = 0
        self.ms_deact_time = 0
        self.ms_interval_time = 0
        self.ms_interval_count = 0
        self.ss_activation_time = 0
        self.ss_deact_time = 0
        self.ss_is_activated = False

    def _ss_activated(self):
        self.ss_activation_time = time.time()
        logger.info("Smoke detected")
        alarm = SensorAlarm(SMOKE_ALARM, "Smoke detected!", self.ss_activation_time)
        self._report_alarm(alarm)

    def _ss_deactivated(self):
        self.ss_deact_time = time.time()
        logger.info("Smoke sensor deactivated, duration: %f" % (self.ss_deact_time - self.ss_activation_time))

    def _ms_activated(self):
        self.ms_activation_count += 1
        self.ms_interval_count += 1
        self.ms_activation_time = time.time()
        logger.info("Motion sensor activated")
        alarm = SensorAlarm(MOTION_ALARM, "Motion detected!", self.ms_activation_time)
        self._report_alarm(alarm)

    def _ms_deactivated(self):
        self.ms_interval_count = 0
        self.ms_deact_time = time.time()
        logger.info("Motion sensor deactivated, duration: %f" % (self.ms_deact_time - self.ms_activation_time))

    def _report_alarm(self, alarm: SensorAlarm):
        if self.alarm_pipe.qsize() > 2:
            self.alarm_pipe.get()
        self.alarm_pipe.put(alarm)

    def _run_process(self):
        self.motion_sensor = MotionSensor(self.motion_GPIO)
        self.smoke_sensor = DigitalInputDevice(self.smoke_GPIO)
        self.buzzer = Buzzer(self.buzzer_GPIO)
        self.motion_sensor.when_activated = self._ms_activated
        self.motion_sensor.when_deactivated = self._ms_deactivated
        self.smoke_sensor.when_activated = self._ss_activated
        self.smoke_sensor.when_deactivated = self._ss_deactivated
        logger.info("Sensor module started")
        while True:
            time.sleep(0.1)

    def start(self):
        self.process = mp.Process(target=self._run_process)
        self.process.daemon = True
        self.process.start()

    def close(self):
        try:
            self.process.terminate()
            self.process.join()
            self.process.close()
        except Exception:
            logger.info("Process already closed")
            return
        logger.info("Sensor module stopped")


# For debugging
if __name__ == '__main__':
    q = mp.Queue()
    s = SensorMonitoring(q)
    s.start()
    ct = time.time()
    while True:
        print(q.get())
    s.close()
