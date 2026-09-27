from __future__ import annotations

import math
import time

HOLD = 0.7


class Job:
    """the one thing paws is busy with, shared by every screen so the bar says the same on all of them.
    when nothing says how far along it is the bar creeps up on its own and never jumps around"""

    def __init__(self):
        self.active = False
        self.label = ""
        self._fraction = None
        self._started = 0.0
        self._done_at = 0.0

    def start(self, label):
        self.active = True
        self.label = label
        self._fraction = None
        self._started = time.monotonic()
        self._done_at = 0.0

    def progress(self, fraction, label=None):
        if label:
            self.label = label
        self._fraction = max(0.0, min(1.0, fraction))

    def done(self):
        self.active = False
        self._fraction = 1.0
        self._done_at = time.monotonic()

    def shown(self):
        return self.active or time.monotonic() - self._done_at < HOLD

    def value(self):
        if not self.active:
            return 1.0
        if self._fraction is not None:
            return self._fraction
        return min(0.95, 1 - math.exp(-(time.monotonic() - self._started) / 8))
