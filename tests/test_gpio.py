import socket
import threading
import unittest

from qemu_pi_gpio.gpio import BCM2837GPIO, GPIO_BASE
from qemu_pi_gpio.qtest import QTestClient


class FakeQTestServer:
    """Tiny in-memory model for protocol and register unit tests."""

    def __init__(self):
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        import os
        import tempfile

        fd, self.path = tempfile.mkstemp(prefix="qtest-test-")
        os.close(fd)
        os.unlink(self.path)
        self.listener.bind(self.path)
        self.listener.listen(1)
        self.regs = {}
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        conn, _ = self.listener.accept()
        with conn, conn.makefile("rwb") as stream:
            for raw in stream:
                cmd = raw.decode().strip().split()
                if not cmd:
                    continue
                if cmd[0] == "readl":
                    addr = int(cmd[1], 0)
                    value = self.regs.get(addr, 0)
                    stream.write(f"OK 0x{value:08x}\n".encode())
                elif cmd[0] == "writel":
                    addr, value = int(cmd[1], 0), int(cmd[2], 0)
                    self.regs[addr] = value
                    offset = addr - GPIO_BASE
                    if offset in (0x1C, 0x20):
                        lev = GPIO_BASE + 0x34 + (offset - 0x1C)
                        self.regs[lev] = self.regs.get(lev, 0) | value
                    elif offset in (0x28, 0x2C):
                        lev = GPIO_BASE + 0x34 + (offset - 0x28)
                        self.regs[lev] = self.regs.get(lev, 0) & ~value
                    stream.write(b"OK\n")
                else:
                    stream.write(b"FAIL unknown command\n")
                stream.flush()

    def close(self):
        self.listener.close()
        import os

        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass


class GPIOTests(unittest.TestCase):
    def setUp(self):
        self.server = FakeQTestServer()
        self.client = QTestClient(self.server.path)
        self.client.connect()
        self.gpio = BCM2837GPIO(self.client)

    def tearDown(self):
        self.client.close()
        self.server.close()

    def test_set_mode_preserves_neighbouring_pins(self):
        addr = GPIO_BASE + 0x00
        self.server.regs[addr] = 0b101 << 0 | 0b011 << 3
        self.gpio.set_mode(0, "output")
        self.assertEqual(self.server.regs[addr] & 0b111, 1)
        self.assertEqual((self.server.regs[addr] >> 3) & 0b111, 3)

    def test_write_requires_output_mode(self):
        with self.assertRaises(RuntimeError):
            self.gpio.write(17, 1)

    def test_write_and_read_level(self):
        self.gpio.set_mode(17, "output")
        self.gpio.write(17, 1)
        self.assertEqual(self.gpio.read(17), 1)
        self.gpio.write(17, 0)
        self.assertEqual(self.gpio.read(17), 0)

    def test_second_bank(self):
        self.gpio.set_mode(40, "output")
        self.gpio.write(40, 1)
        self.assertEqual(self.gpio.read(40), 1)

    def test_invalid_pin_and_level(self):
        with self.assertRaises(ValueError):
            self.gpio.read(54)
        self.gpio.set_mode(2, "output")
        with self.assertRaises(ValueError):
            self.gpio.write(2, 2)

    def test_function_read(self):
        addr = GPIO_BASE + 0x04
        self.server.regs[addr] = 1 << ((12 % 10) * 3)
        self.assertEqual(self.gpio.function(12), 1)
        self.assertEqual(self.gpio.mode(12), "output")


if __name__ == "__main__":
    unittest.main()
