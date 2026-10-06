"""In-process sampling profiler that attributes CPU time to endpoints and source lines.

Runs anywhere (Cloud Run included — no eBPF, no privileges). A background thread samples
the stacks of request threads; sync endpoints in FastAPI/Starlette run in a worker thread,
so each sample can be tied to the endpoint that thread is serving. ``@metered`` also
records exact per-request CPU time with ``time.thread_time()``.
"""

from __future__ import annotations

import functools
import sys
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


def _is_ours(filename: str, root: str) -> bool:
    return filename.startswith(root) and "site-packages" not in filename and "/.venv/" not in filename


@dataclass
class EndpointStats:
    requests: int = 0
    cpu_seconds: float = 0.0


@dataclass
class SamplingProfiler:
    root: Path
    interval_s: float = 0.002
    samples: Counter = field(default_factory=Counter)  # (endpoint, file, line, function) -> count
    endpoints: dict[str, EndpointStats] = field(default_factory=dict)
    _active: dict[int, str] = field(default_factory=dict)  # thread id -> endpoint
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _thread: threading.Thread | None = None
    _stop: threading.Event = field(default_factory=threading.Event)

    def start(self) -> "SamplingProfiler":
        if self._thread is None:
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="joule-sampler", daemon=True)
            self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)
        self._thread = None

    def _run(self) -> None:
        root = str(self.root.resolve())
        me = threading.get_ident()
        while not self._stop.is_set():
            with self._lock:
                active = dict(self._active)
            if active:
                frames = sys._current_frames()
                for tid, endpoint in active.items():
                    frame = frames.get(tid)
                    if tid == me or frame is None:
                        continue
                    # innermost frame that belongs to our code (skip library internals)
                    while frame is not None and not _is_ours(frame.f_code.co_filename, root):
                        frame = frame.f_back
                    if frame is not None and "joulethief/blame" not in frame.f_code.co_filename:
                        rel = str(Path(frame.f_code.co_filename).resolve().relative_to(root))
                        self.samples[(endpoint, rel, frame.f_lineno, frame.f_code.co_name)] += 1
            time.sleep(self.interval_s)

    def metered(self, endpoint: str) -> Callable:
        """Decorator for sync handlers: per-request CPU time + thread → endpoint mapping for sampling."""

        def wrap(fn: Callable) -> Callable:
            @functools.wraps(fn)
            def inner(*args, **kwargs):
                tid = threading.get_ident()
                with self._lock:
                    self._active[tid] = endpoint
                t0 = time.thread_time()
                try:
                    return fn(*args, **kwargs)
                finally:
                    cpu = time.thread_time() - t0
                    with self._lock:
                        self._active.pop(tid, None)
                        stats = self.endpoints.setdefault(endpoint, EndpointStats())
                        stats.requests += 1
                        stats.cpu_seconds += cpu

            return inner

        return wrap

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "samples": [{"endpoint": e, "file": f, "line": ln, "function": fn, "count": c}
                            for (e, f, ln, fn), c in self.samples.most_common()],
                "endpoints": {k: {"requests": v.requests, "cpu_seconds": v.cpu_seconds} for k, v in self.endpoints.items()},
            }
