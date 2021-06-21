import cv2
import numpy as np

from queue import Queue


class MovementDetection(object):
    def __init__(self, frame,
                 grayscale_threshold=15,
                 contour_area_threshold=10,
                 buf_frame_num=50):
        self.grayscale_threshold = grayscale_threshold
        self.contour_area_threshold = contour_area_threshold

        frame = self.frame_processing(frame)
        self.buf_frame = Queue(buf_frame_num)
        for i in range(buf_frame_num):
            self.buf_frame.put(frame)
        self.background = frame
        self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 4))

        # debug
        self.debug = True
        self.time0 = 0

    def frame_processing(self, frame):
        #frame = frame.copy()
        # 灰度处理
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        # 模糊，消除扰动
        gray_frame_blur = cv2.blur(gray_frame, (15, 15))
        return gray_frame_blur

    def get_diff(self, grayscale_frame, background):
        diff = cv2.absdiff(grayscale_frame, background)
        # 图像二值化，灰度值大于threshold时将该灰度赋值为maxval，type为二值化方式
        diff_bin = cv2.threshold(diff, self.grayscale_threshold, 255, cv2.THRESH_BINARY)[1]
        # 膨胀
        diff_dilate = cv2.dilate(diff_bin, self.kernel, iterations=2)
        # 查找轮廓
        contours_ori, hierarchy = cv2.findContours(diff_dilate.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        contours = [contour for contour in contours_ori if cv2.contourArea(contour) > self.contour_area_threshold]

        return contours

    def get_contours4show(self, frame):
        gray_frame_blur = self.frame_processing(frame)
        contours = self.get_diff(gray_frame_blur, self.background)

        frame_prev = self.buf_frame.get()
        self.buf_frame.put(gray_frame_blur)
        # 更新背景帧
        self.background = gray_frame_blur if not contours or not self.get_diff(gray_frame_blur, frame_prev) else self.background

        contours_frame = np.zeros(frame.shape, np.uint8)
        flag = False
        i = 1
        for c in contours:
            flag = True
            # 计算轮廓矩形边框
            x, y, w, h = cv2.boundingRect(c)
            cv2.rectangle(contours_frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(contours_frame, 'Difference %d' % i, (x, y - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            i += 1

        return contours_frame, flag

