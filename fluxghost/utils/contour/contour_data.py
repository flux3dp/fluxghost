import cv2
import numpy as np


def normalize_hu_moments(hu_moments):
    """
    basically like openCV log transform
    but hu[4], hu[5] may be very small with different sign,
    so we use the absolute value to normalize.
    hu[6] is ignored cause it's so different for the same shapes
    """
    # avoid log(0) and log of negative numbers
    hu_moments = np.where(np.abs(hu_moments) < 1e-30, 1e-30, hu_moments)

    return np.array(
        [
            -np.sign(hu_moments[0]) / np.log10(np.abs(hu_moments[0])),
            -np.sign(hu_moments[1]) / np.log10(np.abs(hu_moments[1])),
            -np.sign(hu_moments[2]) / np.log10(np.abs(hu_moments[2])),
            -np.sign(hu_moments[3]) / np.log10(np.abs(hu_moments[3])),
            -1 / np.log10(np.abs(hu_moments[4])),
            -1 / np.log10(np.abs(hu_moments[5])),
        ]
    )


class ContourData:
    def __init__(self, contour: np.ndarray, index: int, source: str = '', priority: int = 0):
        self.contour = contour
        self.index = index
        self.source = source
        self.priority = priority
        moments = cv2.moments(contour)
        self.hu_moments = cv2.HuMoments(moments).flatten()
        self.normalized_hu_moments = normalize_hu_moments(self.hu_moments)
        self.area = abs(cv2.contourArea(contour))
        self._smoothness = None

    @property
    def smoothness(self):
        if self._smoothness is None:
            perimeter = cv2.arcLength(self.contour, True)
            self._smoothness = np.sqrt(self.area) / perimeter
        return self._smoothness

    def to_image(self):
        x, y, w, h = cv2.boundingRect(self.contour)
        img = np.zeros((h, w), dtype=np.uint8)
        cv2.drawContours(img, [self.contour - (x, y)], -1, 255, thickness=cv2.FILLED)
        return img

    def __str__(self):
        return f'ContourData {self.index}'

    def __repr__(self):
        return f'ContourData(index={self.index}, area={self.area}, source="{self.source}")'

    def compare(self, other: 'ContourData'):
        if self.priority != other.priority:
            return self.priority > other.priority
        return self.smoothness > other.smoothness
