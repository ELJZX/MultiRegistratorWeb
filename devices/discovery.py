import math
import struct
from dataclasses import dataclass, replace

from .modbus import DeviceSpec, RegisterFunction

WORD_ORDERS = ("big", "little")


@dataclass
class Candidate:
    address: int
    function: str
    word_order: str
    value: float
    words: list

    @property
    def key(self):
        return f"{self.function}-{self.address}-{self.word_order}"


def decode_float32(words, word_order):
    if words is None or len(words) < 2:
        return None
    high, low = int(words[0]) & 0xFFFF, int(words[1]) & 0xFFFF
    if word_order == "little":
        high, low = low, high
    try:
        return struct.unpack(">f", struct.pack(">I", (high << 16) | low))[0]
    except struct.error:
        return None


def _plausible(value, min_abs, max_abs):
    if value is None or math.isnan(value) or math.isinf(value):
        return False
    return min_abs <= abs(value) <= max_abs


def discover_channels(reader, device, function, start, end, min_abs=1e-3, max_abs=1e6):
    """Probe the register space and return plausible float32 channels.

    One two-register request per address.  Every address is reported so the
    administrator can recognise the sensor by its value.
    """
    function = RegisterFunction(function).value
    if function not in (RegisterFunction.INPUT.value, RegisterFunction.HOLDING.value):
        raise ValueError("discovery supports 'input' and 'holding' registers only")
    if end <= start:
        return []

    candidates = []
    address = start
    while address < end:
        words = reader.probe(device, function, address, 2)
        if words is None or len(words) < 2:
            address += 1
            continue

        found = None
        for order in WORD_ORDERS:
            value = decode_float32(words, order)
            if _plausible(value, min_abs, max_abs):
                found = Candidate(
                    address=address,
                    function=function,
                    word_order=order,
                    value=float(value),
                    words=[int(word) & 0xFFFF for word in words[:2]],
                )
                break

        if found is not None:
            candidates.append(found)
        address += 1
    return candidates


def find_unit_ids(reader, device, start, end, function="holding", address=0):
    """Probe a range of Modbus unit IDs and return the ones that answer."""
    function = RegisterFunction(function).value
    found = []
    for unit_id in range(start, end + 1):
        spec = replace(
            device,
            unit_id=unit_id,
            timeout=min(getattr(device, "timeout", 1.0) or 1.0, 0.4),
        )
        words = reader.probe(spec, function, address, 1)
        if words:
            found.append(unit_id)
    return found
