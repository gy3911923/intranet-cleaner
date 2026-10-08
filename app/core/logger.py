# -*- coding: utf-8 -*-
"""线程安全日志：UI 滚屏 + 落盘。"""
import threading
import time


class Logger:
    def __init__(self, logfile=None, max_lines=2000):
        self._lock = threading.Lock()
        self._cbs = []
        self._lines = []
        self._max = max_lines
        self.logfile = logfile

    def subscribe(self, cb):
        with self._lock:
            for line in self._lines:
                try:
                    cb(line)
                except Exception:
                    pass
            self._cbs.append(cb)

    def log(self, msg):
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        with self._lock:
            self._lines.append(line)
            if len(self._lines) > self._max:
                self._lines = self._lines[-self._max:]
            cbs = list(self._cbs)
        for cb in cbs:
            try:
                cb(line)
            except Exception:
                pass
        if self.logfile:
            try:
                with open(self.logfile, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except OSError:
                pass
        return line
