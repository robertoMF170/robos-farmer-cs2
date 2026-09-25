import threading
import time

import serial
import serial.tools.list_ports


class ArduinoLink:
    def __init__(self, port):
        self.port_name = port
        self.ser = None
        self.lock = threading.Lock()

    def connect(self):
        self.ser = serial.Serial(self.port_name, 115200, timeout=8)
        time.sleep(2.5)
        self.ser.reset_input_buffer()
        for _ in range(3):
            self.ser.write(b"PING\n")
            self.ser.flush()
            line = self.ser.readline().decode(errors="ignore").strip()
            if line == "PONG":
                return
            time.sleep(0.5)
        self.close()
        raise ConnectionError("Arduino não respondeu ao handshake")

    @staticmethod
    def find():
        for p in serial.tools.list_ports.comports():
            desc = (p.description or "").lower()
            vid = getattr(p, "vid", None)
            if vid == 0x2341 or "leonardo" in desc or "arduino" in desc:
                link = ArduinoLink(p.device)
                try:
                    link.connect()
                    return link
                except Exception:
                    try:
                        link.close()
                    except Exception:
                        pass
        return None

    def key(self, k, hold_s):
        with self.lock:
            self._ensure()
            self._send(f"K {k} {int(hold_s * 1000)}")

    def move(self, dx, dy):
        with self.lock:
            self._ensure()
            self._send(f"M {int(dx)} {int(dy)}")

    def _send(self, cmd):
        self.ser.write((cmd + "\n").encode())
        self.ser.flush()
        line = self.ser.readline().decode(errors="ignore").strip()
        if line != "OK":
            raise ConnectionError(f"Arduino respondeu: {line!r}")

    def _ensure(self):
        if self.ser is None or not self.ser.is_open:
            self.connect()

    def close(self):
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
        except Exception:
            pass
        self.ser = None
