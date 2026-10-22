"""Minimal synchronous client for QEMU's line-oriented QTest protocol."""

from __future__ import annotations

import socket
import threading
from typing import Optional


class QTestError(RuntimeError):
    """Raised when QTest is disconnected or returns an unexpected response."""


class QTestClient:
    def __init__(self, path: str, timeout: float = 2.0):
        self.path = path
        self.timeout = timeout
        self._sock: Optional[socket.socket] = None
        self._reader = None
        self._lock = threading.Lock()

    @property
    def connected(self) -> bool:
        return self._sock is not None

    def connect(self) -> None:
        if self.connected:
            return
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect(self.path)
            reader = sock.makefile("r", encoding="ascii", newline="\n")
            self._sock = sock
            self._reader = reader
        except OSError:
            sock.close()
            raise

    def close(self) -> None:
        # Do not call this while holding _lock from command(); close is safe from UI.
        with self._lock:
            if self._reader is not None:
                try:
                    self._reader.close()
                except OSError:
                    pass
            if self._sock is not None:
                try:
                    self._sock.close()
                except OSError:
                    pass
            self._reader = None
            self._sock = None

    def command(self, command: str) -> str:
        with self._lock:
            if self._sock is None or self._reader is None:
                raise QTestError("Not connected to QTest socket")
            try:
                self._sock.sendall((command + "\n").encode("ascii"))
                line = self._reader.readline()
            except (OSError, UnicodeError) as exc:
                raise QTestError(f"QTest command failed: {exc}") from exc
            if not line:
                raise QTestError("QTest socket closed by QEMU")
            response = line.strip()
            if response.startswith("FAIL"):
                raise QTestError(f"QEMU rejected {command!r}: {response}")
            if not response.startswith("OK"):
                raise QTestError(
                    f"Unexpected QTest response to {command!r}: {response!r}"
                )
            return response

    def readl(self, address: int) -> int:
        response = self.command(f"readl 0x{address:x}")
        fields = response.split()
        if len(fields) < 2:
            raise QTestError(f"Missing value in QTest response: {response!r}")
        try:
            return int(fields[1], 0)
        except ValueError as exc:
            raise QTestError(f"Invalid value in QTest response: {response!r}") from exc

    def writel(self, address: int, value: int) -> None:
        if not 0 <= value <= 0xFFFFFFFF:
            raise ValueError("32-bit register value must be between 0 and 0xffffffff")
        self.command(f"writel 0x{address:x} 0x{value:08x}")
