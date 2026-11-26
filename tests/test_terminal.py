"""POSIX pseudo-terminal lifecycle checks."""

from __future__ import annotations

import fcntl
import os
import pty
import select
import signal
import struct
import subprocess
import sys
import termios
import time
import unittest


@unittest.skipUnless(os.name == "posix", "requires POSIX pty/termios")
class TerminalLifecycleTests(unittest.TestCase):
    def run_terminal(self, action):
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
        original = termios.tcgetattr(slave)
        env = dict(os.environ, TERM="xterm-256color", LANG="C.UTF-8")
        code = (
            "from bouquet.config.settings import Settings; "
            "from bouquet.tui.app import App; "
            "app = App(Settings(), config_enabled=False, ascii_mode=True, color=False); "
            "app._draw = lambda: (_ for _ in ()).throw(RuntimeError('test crash')); app.run()"
        )
        command = [sys.executable, "-c", code] if action == "crash" else [
            sys.executable, "-m", "bouquet", "--no-config", "--ascii", "--no-color"
        ]
        process = subprocess.Popen(command, stdin=slave, stdout=slave, stderr=slave,
                                   env=env, close_fds=True)
        output = bytearray()
        try:
            time.sleep(0.25)
            if action == "q":
                os.write(master, b"q")
            elif action == "ctrl-c":
                os.write(master, b"\x03")
            elif action == "crash":
                # Trigger the injected draw failure after terminal entry.
                os.write(master, b"?")
            else:
                process.send_signal(action)
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                ready, _, _ = select.select([master], [], [], 0.1)
                if ready:
                    try:
                        chunk = os.read(master, 65536)
                    except OSError:
                        chunk = b""
                    if chunk:
                        output.extend(chunk)
                if process.poll() is not None:
                    break
            if process.poll() is None:
                process.kill()
            process.wait(timeout=2)
            while True:
                ready, _, _ = select.select([master], [], [], 0.1)
                if not ready:
                    break
                try:
                    chunk = os.read(master, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                output.extend(chunk)
            self.assertEqual(termios.tcgetattr(slave), original)
            raw = bytes(output)
            self.assertIn(b"\x1b[?25h", raw)
            self.assertIn(b"\x1b[?1049l", raw)
            self.assertEqual(process.returncode, 1 if action == "crash" else 0)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)
            os.close(slave)

    def test_quit_and_ctrl_c_restore_terminal(self):
        for action in ("q", "ctrl-c"):
            with self.subTest(action=action):
                self.run_terminal(action)

    def test_termination_signals_restore_terminal(self):
        for action in (signal.SIGTERM, signal.SIGHUP):
            with self.subTest(signal=action):
                self.run_terminal(action)

    def test_uncaught_exception_restores_terminal(self):
        self.run_terminal("crash")


if __name__ == "__main__":
    unittest.main()
