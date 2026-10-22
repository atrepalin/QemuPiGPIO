import socket
import threading
import unittest

from qemu_pi_gpio.qtest import QTestClient


class QTestProtocolTests(unittest.TestCase):
    def test_read_and_write(self):
        import os
        import tempfile

        fd, path = tempfile.mkstemp(prefix="qtest-protocol-")
        os.close(fd)
        os.unlink(path)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(path)
        listener.listen(1)

        def server():
            conn, _ = listener.accept()
            with conn, conn.makefile("rwb") as stream:
                line = stream.readline().decode().strip()
                self.assertEqual(line, "readl 0x10")
                stream.write(b"OK 0x1234\n")
                stream.flush()
                line = stream.readline().decode().strip()
                self.assertEqual(line, "writel 0x10 0x00000002")
                stream.write(b"OK\n")
                stream.flush()

        thread = threading.Thread(target=server, daemon=True)
        thread.start()
        client = QTestClient(path)
        try:
            client.connect()
            self.assertEqual(client.readl(0x10), 0x1234)
            client.writel(0x10, 2)
            thread.join(timeout=1)
        finally:
            client.close()
            listener.close()
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass

    def test_disconnected_client_fails(self):
        client = QTestClient("/tmp/this-qtest-socket-should-not-exist")
        with self.assertRaises(OSError):
            client.connect()


if __name__ == "__main__":
    unittest.main()
