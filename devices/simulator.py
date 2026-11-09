import socketserver
import struct
import threading


def pack_bits(values):
    values = list(values)
    packed = bytearray((len(values) + 7) // 8)
    for index, bit in enumerate(values):
        if bit:
            packed[index // 8] |= 1 << (index % 8)
    return bytes(packed)


class _ModbusServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address):
        super().__init__(address, _ModbusRequestHandler)
        self.holding = {}
        self.input = {}
        self.coils = {}
        self.discrete = {}
        self.lock = threading.RLock()
        self.connections = 0


class _ModbusRequestHandler(socketserver.BaseRequestHandler):
    def _recv_exact(self, size):
        data = b""
        while len(data) < size:
            chunk = self.request.recv(size - len(data))
            if not chunk:
                return None
            data += chunk
        return data

    def handle(self):
        server = self.server
        with server.lock:
            server.connections += 1
        try:
            while True:
                header = self._recv_exact(7)
                if header is None:
                    break
                transaction_id, _protocol, length, unit = struct.unpack(">HHHB", header)
                pdu = self._recv_exact(max(1, length - 1))
                if pdu is None:
                    break
                response = self._process(server, pdu)
                self.request.sendall(
                    struct.pack(">HHHB", transaction_id, 0, len(response) + 1, unit) + response
                )
        except OSError:
            pass
        finally:
            with server.lock:
                server.connections -= 1

    @staticmethod
    def _exception(function, code):
        return struct.pack(">BB", function | 0x80, code)

    def _process(self, server, pdu):
        function = pdu[0]
        with server.lock:
            if function in (3, 4):
                address, count = struct.unpack(">HH", pdu[1:5])
                if not 1 <= count <= 125:
                    return self._exception(function, 0x03)
                memory = server.holding if function == 3 else server.input
                registers = [memory.get(address + i, 0) & 0xFFFF for i in range(count)]
                payload = b"".join(struct.pack(">H", value) for value in registers)
                return struct.pack(">BB", function, count * 2) + payload

            if function in (1, 2):
                address, count = struct.unpack(">HH", pdu[1:5])
                if not 1 <= count <= 2000:
                    return self._exception(function, 0x03)
                memory = server.coils if function == 1 else server.discrete
                bits = [bool(memory.get(address + i, 0)) for i in range(count)]
                packed = pack_bits(bits)
                return struct.pack(">BB", function, len(packed)) + packed

            if function == 5:
                address, value = struct.unpack(">HH", pdu[1:5])
                server.coils[address] = value == 0xFF00
                return pdu[:5]

            if function == 6:
                address, value = struct.unpack(">HH", pdu[1:5])
                server.holding[address] = value
                return pdu[:5]

            if function == 15:
                address, count, byte_count = struct.unpack(">HHB", pdu[1:6])
                payload = pdu[6 : 6 + byte_count]
                for i in range(count):
                    server.coils[address + i] = bool(payload[i // 8] & (1 << (i % 8)))
                return struct.pack(">BHH", function, address, count)

            if function == 16:
                address, count, byte_count = struct.unpack(">HHB", pdu[1:6])
                payload = pdu[6 : 6 + byte_count]
                for i in range(count):
                    server.holding[address + i] = struct.unpack(
                        ">H", payload[i * 2 : i * 2 + 2]
                    )[0]
                return struct.pack(">BHH", function, address, count)

        return self._exception(function, 0x01)


class ModbusSimulator:
    def __init__(self, host="0.0.0.0", port=5020):
        self._server = _ModbusServer((host, port))
        self._thread = None

    @property
    def address(self):
        return self._server.server_address

    @property
    def connections(self):
        with self._server.lock:
            return self._server.connections

    def _write(self, memory, address, values):
        sequence = values if isinstance(values, (list, tuple)) else [values]
        with self._server.lock:
            for offset, value in enumerate(sequence):
                memory[address + offset] = int(value) & 0xFFFF

    def set_holding(self, address, values):
        self._write(self._server.holding, address, values)

    def set_input(self, address, values):
        self._write(self._server.input, address, values)

    def set_coil(self, address, value):
        with self._server.lock:
            self._server.coils[address] = bool(value)

    def set_discrete(self, address, value):
        with self._server.lock:
            self._server.discrete[address] = bool(value)

    def get_holding(self, address):
        with self._server.lock:
            return self._server.holding.get(address, 0)

    def start(self):
        if self._thread is not None:
            return self
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        if self._thread is None:
            return
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)
        self._thread = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *_exc):
        self.stop()


class TemperatureSource:
    def __init__(self, base=25.0, amplitude=5.0, step=0.4, rng=None):
        import random

        self.base = float(base)
        self.amplitude = abs(float(amplitude))
        self.step = abs(float(step))
        self._rng = rng or random.Random()
        self._value = self.base

    def next(self):
        low = self.base - self.amplitude
        high = self.base + self.amplitude
        self._value += self._rng.uniform(-self.step, self.step)
        self._value = min(high, max(low, self._value))
        return round(self._value, 2)
