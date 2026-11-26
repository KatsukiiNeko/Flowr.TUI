"""Terminal lifecycle: raw mode, signals, non-blocking input and size.

Everything is best-effort on Windows.  On POSIX the raw-mode attributes are
saved once and restored by :meth:`restore`, which is idempotent and safe to
call from a signal handler, an exception handler and ``atexit``.
"""

from __future__ import annotations

import atexit
import os
import select
import shutil
import signal
import sys
from typing import List, Optional, Tuple

from ..render.presenter import AnsiPresenter


class Terminate(Exception):
    """Raised from signal handlers to unwind the render loop cleanly."""


class Terminal:
    def __init__(self, presenter: AnsiPresenter) -> None:
        self.presenter = presenter
        self._saved_attrs = None
        self._entered = False
        self._restored = False
        self.resize_pending = False
        self.suspend_pending = False
        self.resume_pending = False
        self._old_handlers = {}
        self._atexit_registered = False

    # -- setup / teardown --------------------------------------------------
    def enter(self) -> None:
        if self._entered:
            return
        if os.name == "nt":
            os.system("")
        else:
            import termios
            import tty

            fd = sys.stdin.fileno()
            self._saved_attrs = termios.tcgetattr(fd)
            tty.setraw(fd)
        self._entered = True
        self.presenter.enter()
        if not self._atexit_registered:
            atexit.register(self.cleanup)
            self._atexit_registered = True

    def restore(self) -> None:
        if self._entered:
            try:
                self.presenter.exit()
            finally:
                if os.name != "nt" and self._saved_attrs is not None:
                    import termios

                    try:
                        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self._saved_attrs)
                    except (OSError, ValueError):
                        pass
                self._entered = False
        self._restored = True

    def cleanup(self) -> None:
        self.restore()

    def install_signal_handlers(self) -> None:
        def terminate(_signum, _frame):
            raise Terminate()

        def resize(_signum, _frame):
            self.resize_pending = True

        def suspend(_signum, _frame):
            self.suspend_pending = True

        def resume(_signum, _frame):
            self.resume_pending = True

        for sig, handler in (
            (getattr(signal, "SIGTERM", None), terminate),
            (getattr(signal, "SIGHUP", None), terminate),
            (getattr(signal, "SIGINT", None), terminate),
            (getattr(signal, "SIGWINCH", None), resize),
            (getattr(signal, "SIGTSTP", None), suspend),
            (getattr(signal, "SIGCONT", None), resume),
        ):
            if sig is None:
                continue
            try:
                self._old_handlers[sig] = signal.getsignal(sig)
                signal.signal(sig, handler)
            except (ValueError, OSError):
                pass

    def restore_signal_handlers(self) -> None:
        for sig, handler in self._old_handlers.items():
            try:
                signal.signal(sig, handler)
            except (ValueError, OSError, TypeError):
                pass
        self._old_handlers.clear()

    def suspend(self) -> None:
        """Leave the alternate screen, stop the process, then re-enter."""
        self.restore()
        self.resume_pending = False
        try:
            os.kill(os.getpid(), signal.SIGSTOP)
        except (OSError, AttributeError):
            pass
        self.enter()

    # -- I/O ---------------------------------------------------------------
    def size(self) -> Tuple[int, int]:
        try:
            size = shutil.get_terminal_size(fallback=(80, 24))
        except OSError:
            return 80, 24
        return max(1, size.columns), max(1, size.lines)

    def read(self, timeout: float) -> bytes:
        if os.name == "nt":
            import msvcrt

            data = bytearray()
            while msvcrt.kbhit():
                data.extend(msvcrt.getwch().encode("utf-8", "ignore"))
            return bytes(data)
        try:
            ready, _, _ = select.select([sys.stdin], [], [], max(0.0, timeout))
        except (OSError, ValueError):
            return b""
        if not ready:
            return b""
        try:
            return os.read(sys.stdin.fileno(), 4096)
        except (OSError, ValueError):
            return b""
