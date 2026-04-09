from collections import deque
from statistics import median

class MedianFilter:
    def __init__(self, window_size=5):
        self.values = deque(maxlen=window_size)

    def update(self, value):
        if value is None or value <= 0:
            return None
        self.values.append(value)
        return median(self.values)

class MovingAverageFilter:
    def __init__(self, window_size=5):
        self.values = deque(maxlen=window_size)

    def update(self, value):
        if value is None:
            return None
        self.values.append(value)
        return sum(self.values) / len(self.values)

class OffsetCompensator:
    def __init__(self, offset=0.0):
        self.offset = offset

    def update(self, value):
        if value is None:
            return None
        return value - self.offset
