import math
import struct
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

try:
    from pymodbus.client import ModbusTcpClient
except Exception:
    ModbusTcpClient = None

MAX_REGISTERS_PER_REQUEST = 125


class RegisterFunction(str, Enum):
    HOLDING = "holding"
    INPUT = "input"
    COIL = "coil"
    DISCRETE = "discrete"

    @property
    def is_bit(self):
        return self in (RegisterFunction.COIL, RegisterFunction.DISCRETE)


class DataType(str, Enum):
    INT16 = "int16"
    UINT16 = "uint16"
    INT32 = "int32"
    UINT32 = "uint32"
    FLOAT32 = "float32"

    @property
    def word_count(self):
        if self in (DataType.INT32, DataType.UINT32, DataType.FLOAT32):
            return 2
        return 1


def register_word_count(data_type):
    return DataType(data_type).word_count


def decode_registers(words, data_type, scale=1.0, word_order="big"):
    data_type = DataType(data_type)
    if not words:
        raise ValueError("no registers to decode")

    if data_type is DataType.UINT16:
        raw = int(words[0]) & 0xFFFF
    elif data_type is DataType.INT16:
        value = int(words[0]) & 0xFFFF
        raw = value - 0x10000 if value >= 0x8000 else value
    else:
        if len(words) < 2:
            raise ValueError(f"{data_type.value} requires 2 registers")
        high, low = int(words[0]) & 0xFFFF, int(words[1]) & 0xFFFF
        if word_order == "little":
            high, low = low, high
        combined = (high << 16) | low
        if data_type is DataType.INT32:
            raw = combined - 0x100000000 if combined >= 0x80000000 else combined
        elif data_type is DataType.UINT32:
            raw = combined
        else:
            raw = struct.unpack(">f", struct.pack(">I", combined))[0]
    return raw * scale


def encode_registers(value, data_type, scale=1.0, word_order="big"):
    data_type = DataType(data_type)
    factor = float(scale) if scale else 1.0
    raw = float(value) / factor

    if data_type is DataType.FLOAT32:
        combined = struct.unpack(">I", struct.pack(">f", raw))[0]
    elif data_type in (DataType.UINT16, DataType.INT16):
        return [int(round(raw)) & 0xFFFF]
    else:
        combined = int(round(raw)) & 0xFFFFFFFF

    high = (combined >> 16) & 0xFFFF
    low = combined & 0xFFFF
    return [low, high] if word_order == "little" else [high, low]


class ModbusReadError(RuntimeError):
    pass


@dataclass
class ChannelSpec:
    name: str
    address: int
    function: str = RegisterFunction.HOLDING.value
    data_type: str = DataType.UINT16.value
    scale: float = 1.0
    unit: str = ""
    word_order: str = "big"
    writable: bool = False

    @property
    def word_count(self):
        return register_word_count(self.data_type)

    @property
    def is_bit(self):
        return RegisterFunction(self.function).is_bit


@dataclass
class DeviceSpec:
    id: str
    name: str
    host: str
    port: int = 502
    unit_id: int = 1
    poll_interval: float = 5.0
    timeout: float = 3.0
    retries: int = 1
    channels: list = field(default_factory=list)

    @property
    def channel_names(self):
        return [channel.name for channel in self.channels]


@dataclass
class ReadResult:
    values: dict
    unavailable: set = field(default_factory=set)

    @property
    def available(self):
        return {name: name not in self.unavailable for name in self.values}


@dataclass
class ReadBlock:
    function: str
    start: int
    count: int
    channels: list = field(default_factory=list)

    @property
    def end(self):
        return self.start + self.count - 1


def build_read_blocks(channels, max_registers=MAX_REGISTERS_PER_REQUEST, max_gap=8):
    blocks = []
    for function in RegisterFunction:
        group = [c for c in channels if c.function == function.value]
        if not group:
            continue
        group.sort(key=lambda c: c.address)
        current = None
        for channel in group:
            width = 1 if channel.is_bit else channel.word_count
            if current is None:
                current = ReadBlock(function.value, channel.address, width, [channel])
                continue
            gap = channel.address - (current.start + current.count)
            new_count = channel.address + width - current.start
            if 0 <= gap <= max_gap and new_count <= max_registers:
                current.count = new_count
                current.channels.append(channel)
            else:
                blocks.append(current)
                current = ReadBlock(function.value, channel.address, width, [channel])
        if current is not None:
            blocks.append(current)
    return blocks


def _default_client_factory(host, port, timeout, retries):
    if ModbusTcpClient is None:
        raise ModbusReadError("pymodbus is not installed")
    return ModbusTcpClient(host, port=port, timeout=timeout, retries=retries)


class ModbusReader:
    def __init__(self, inter_request_delay=0.0, client_factory=None):
        self.inter_request_delay = max(0.0, float(inter_request_delay))
        self._client_factory = client_factory or _default_client_factory
        self._clients = {}

    def _get_client(self, device):
        client = self._clients.get(device.id)
        if client is not None and getattr(client, "connected", False):
            return client
        if client is not None:
            self._safe_close(client)
        client = self._client_factory(device.host, device.port, device.timeout, device.retries)
        if hasattr(client, "connect") and not client.connect():
            raise ModbusReadError(f"cannot connect to {device.host}:{device.port}")
        self._clients[device.id] = client
        return client

    @staticmethod
    def _safe_close(client):
        try:
            client.close()
        except Exception:
            pass

    def close(self, device_id=None):
        if device_id is None:
            for client in self._clients.values():
                self._safe_close(client)
            self._clients.clear()
            return
        client = self._clients.pop(device_id, None)
        if client is not None:
            self._safe_close(client)

    def read(self, device):
        return self.read_full(device).values

    def read_full(self, device):
        if not device.channels:
            raise ModbusReadError(f"device {device.id} has no channels configured")

        blocks = build_read_blocks(device.channels)
        values = {}
        unavailable = set()
        client = None
        readable_blocks = 0
        last_error = None
        try:
            client = self._get_client(device)
            for index, block in enumerate(blocks):
                if index and self.inter_request_delay:
                    time.sleep(self.inter_request_delay)
                for channel in block.channels:
                    values.setdefault(channel.name, None)
                try:
                    raw = self._read_block(client, device, block)
                except ModbusReadError as exc:
                    last_error = str(exc)
                    for channel in block.channels:
                        unavailable.add(channel.name)
                    continue
                readable_blocks += 1
                for channel in block.channels:
                    offset = channel.address - block.start
                    if channel.is_bit:
                        values[channel.name] = float(1 if raw[offset] else 0)
                    else:
                        width = channel.word_count
                        words = raw[offset : offset + width]
                        try:
                            decoded = decode_registers(
                                words,
                                channel.data_type,
                                channel.scale,
                                channel.word_order,
                            )
                        except (ValueError, struct.error) as exc:
                            last_error = f"cannot decode {channel.name}: {exc}"
                            unavailable.add(channel.name)
                            values[channel.name] = None
                            continue
                        if isinstance(decoded, float) and math.isnan(decoded):
                            unavailable.add(channel.name)
                            values[channel.name] = None
                        else:
                            values[channel.name] = decoded
        except ModbusReadError:
            self.close(device.id)
            raise
        except Exception as exc:
            self.close(device.id)
            raise ModbusReadError(str(exc)) from exc

        if readable_blocks == 0:
            self.close(device.id)
            raise ModbusReadError(last_error or f"no data from {device.host}")
        return ReadResult(values=values, unavailable=unavailable)

    def probe(self, device, function, start, count):
        block = ReadBlock(RegisterFunction(function).value, start, count)
        try:
            client = self._get_client(device)
            return self._read_block(client, device, block)
        except Exception:
            return None

    def _read_block(self, client, device, block):
        function = RegisterFunction(block.function)
        try:
            if function is RegisterFunction.HOLDING:
                response = client.read_holding_registers(
                    block.start, count=block.count, device_id=device.unit_id
                )
            elif function is RegisterFunction.INPUT:
                response = client.read_input_registers(
                    block.start, count=block.count, device_id=device.unit_id
                )
            elif function is RegisterFunction.COIL:
                response = client.read_coils(
                    block.start, count=block.count, device_id=device.unit_id
                )
            else:
                response = client.read_discrete_inputs(
                    block.start, count=block.count, device_id=device.unit_id
                )
        except TypeError:
            response = self._read_block_legacy(client, device, block, function)
        if response is None or response.isError():
            raise ModbusReadError(
                f"bad response for {device.host} @{block.start}+{block.count}"
            )
        if function.is_bit:
            return list(getattr(response, "bits", []))[: block.count]
        return list(getattr(response, "registers", []))

    @staticmethod
    def _read_block_legacy(client, device, block, function):
        kwargs = {"slave": device.unit_id}
        if function is RegisterFunction.HOLDING:
            return client.read_holding_registers(block.start, count=block.count, **kwargs)
        if function is RegisterFunction.INPUT:
            return client.read_input_registers(block.start, count=block.count, **kwargs)
        if function is RegisterFunction.COIL:
            return client.read_coils(block.start, count=block.count, **kwargs)
        return client.read_discrete_inputs(block.start, count=block.count, **kwargs)
