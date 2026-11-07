# -*- coding: utf-8 -*-
"""Bit-level serialization primitives for the DFM-style UE net bitstream.

1:1 port of the Rust reference (5_6327665327379324421(2).rs).
Bit order is LSB-first inside each byte (UE FBitWriter convention):
the first serialized bit is bit 0 of the first byte.
"""
from __future__ import annotations

MAX_NETWORK_STRING_UNITS = 4096


class BitError(Exception):
    """Raised when a read runs past the declared bitstream length."""


def bit(data: bytes, position: int) -> int:
    idx = position >> 3
    if idx >= len(data):
        return 0
    return (data[idx] >> (position & 7)) & 1


def read_bits_at(data: bytes, position: int, count: int) -> int:
    if count == 0:
        return 0
    byte = position >> 3
    if byte >= len(data):
        return 0
    shift = position & 7
    end = min(byte + count + shift + 7 // 8, len(data))
    value = int.from_bytes(data[byte:end], "little")
    return (value >> shift) & ((1 << count) - 1)


def slice_bits(data: bytes, position: int, count: int) -> bytes:
    if count == 0:
        return b""
    end_bit = position + count
    end_byte = (end_bit + 7) >> 3
    out_len = (count + 7) >> 3
    if (position >> 3) >= len(data):
        return bytes(out_len)
    if (position & 7) == 0:
        start = position >> 3
        stop = min(end_byte, len(data))
        if start >= stop:
            return bytes(out_len)
        out = bytearray(data[start:stop])
        out += bytes(out_len - len(out))
        if count & 7:
            out[-1] &= (1 << (count & 7)) - 1
        return bytes(out)
    start = position >> 3
    stop = min(end_byte, len(data))
    val = int.from_bytes(data[start:stop], "little") >> (position & 7)
    val &= (1 << count) - 1
    return val.to_bytes(out_len, "little")


def termination_data_bits(data: bytes) -> int:
    for idx in range(len(data) - 1, -1, -1):
        b = data[idx]
        if b:
            return idx * 8 + b.bit_length() - 1
    return 0


class BitReader:
    """LSB-first bit reader over a byte buffer with an explicit bit count.

    Performance: bits()/bit() are the single hottest path in the entire radar
    pipeline (every MRA frame item + every RepLayout value passes through
    bits()). The naive path re-allocated a bytes slice + ran int.from_bytes on
    every call. We keep a cached little-endian int window ("_win") covering the
    current position; reads that fit the window are pure int shifts. The window
    reloads only when position crosses its boundary (every ~8 bytes of reading),
    so the per-call cost drops to an int shift + mask.

    The public contract (position semantics, BitError on overrun) is unchanged;
    read_vals stay bit-exact.
    """

    __slots__ = ("data", "bit_count", "position", "_win", "_win_base", "_win_bits")

    def __init__(self, data: bytes, bit_count: int):
        self.data = data
        self.bit_count = bit_count
        self.position = 0
        self._win = 0
        self._win_base = -1
        self._win_bits = 0

    def remaining(self) -> int:
        return max(self.bit_count - self.position, 0)

    def ensure(self, count: int) -> None:
        end = self.position + count
        if end > self.bit_count:
            raise BitError(
                f"need {count} bits with {self.remaining()} remaining"
            )
        if end > 0:
            last_byte = (end - 1) >> 3
            if last_byte >= len(self.data):
                raise BitError(
                    f"bit reader past buffer: need byte {last_byte}, len {len(self.data)}"
                )
        return None

    def _reload(self, byte: int) -> None:
        data = self.data
        stop = byte + 12
        if stop > len(data):
            stop = len(data)
        self._win = int.from_bytes(data[byte:stop], "little")
        self._win_base = byte << 3
        self._win_bits = (stop - byte) << 3
        return None

    def bit(self) -> int:
        p = self.position
        if p >= self.bit_count:
            raise BitError(f"need 1 bits with {self.remaining()} remaining")
        base = self._win_base
        if base < 0 or not (base <= p < base + self._win_bits):
            self._reload(p >> 3)
            base = self._win_base
        v = (self._win >> (p - base)) & 1
        self.position = p + 1
        return v

    def bits(self, count: int) -> int:
        if count > 64:
            raise BitError(f"need {count} bits (max 64)")
        p = self.position
        end = p + count
        if end > self.bit_count:
            raise BitError(f"need {count} bits with {self.remaining()} remaining")
        base = self._win_base
        if base < 0 or p < base or end > base + self._win_bits:
            self._reload(p >> 3)
            base = self._win_base
        v = 0 if count == 0 else ((self._win >> (p - base)) & ((1 << count) - 1))
        self.position = end
        return v

    def uint8(self) -> int:
        return self.bits(8)

    def uint16(self) -> int:
        return self.bits(16)

    def uint32(self) -> int:
        return self.bits(32)

    def uint64(self) -> int:
        return self.bits(64)

    def int32(self) -> int:
        v = self.uint32()
        if v & 2147483648:
            v -= 4294967296
        return v

    def float32(self) -> float:
        import struct

        return struct.unpack("<f", self.uint32().to_bytes(4, "little"))[0]

    def raw_bytes(self, count: int) -> bytes:
        self.ensure(count * 8)
        chunks = []
        left = count
        while left:
            take = 8 if left >= 8 else left
            chunks.append(self.bits(take * 8).to_bytes(take, "little"))
            left -= take
        return b"".join(chunks)

    def packed_int(self, variant: str = "dfm") -> int:
        value = 0
        shift = 0
        for _ in range(5):
            encoded = self.uint8()
            if variant == "dfm":
                value |= (encoded >> 1) << shift
                if (encoded & 1) == 0:
                    return value
            else:
                value |= (encoded & 127) << shift
                if (encoded & 128) == 0:
                    return value
            shift += 7
        raise BitError("SerializeIntPacked exceeds 32 bits")

    def serialize_int(self, maximum: int) -> int:
        if maximum > 0 and (maximum & (maximum - 1)) == 0:
            k = maximum.bit_length() - 1
            if k:
                return self.bits(k)
            return 0
        value = 0
        mask = 1
        while value + mask < maximum:
            if self.bit():
                value |= mask
            mask <<= 1
        return value

    def fstring(self) -> str:
        length = self.int32()
        units = abs(length)
        if units > MAX_NETWORK_STRING_UNITS:
            raise BitError(f"invalid FString length {length}")
        if length >= 0:
            self.ensure(units * 8)
            raw = self.raw_bytes(units) if units else b""
            if raw.endswith(b"\x00"):
                raw = raw[:-1]
            return raw.decode("utf-8", "replace")
        self.ensure(units * 16)
        raw = self.raw_bytes(units * 2) if units else b""
        if units and raw.endswith(b"\x00\x00"):
            raw = raw[:-2]
        return raw.decode("utf-16-le", "replace")

    def package_map_object_ref(self, variant: str = "dfm"):
        network_guid = self.packed_int(variant)
        if network_guid != 1:
            return {
                "network_guid": network_guid,
                "inline_export": False,
                "flags": None,
                "outer": None,
                "path": None,
                "checksum": None,
            }
        flags = self.uint8()
        ref = {
            "network_guid": network_guid,
            "inline_export": True,
            "flags": flags,
            "outer": None,
            "path": None,
            "checksum": None,
        }
        if flags & 1:
            ref["outer"] = self.package_map_object_ref(variant)
            ref["path"] = self.fstring()
            if flags & 4:
                ref["checksum"] = self.uint32()
        return ref

    def take(self, count: int) -> bytes:
        if count > self.remaining():
            raise BitError(f"invalid bit slice {count}/{self.remaining()}")
        out = slice_bits(self.data, self.position, count)
        self.position += count
        return out


class BitWriter:
    def __init__(self):
        self._data = bytearray()
        self.bit_count = 0

    def bytes(self) -> bytes:
        return bytes(self._data)

    def bit(self, value: int) -> None:
        if (self.bit_count & 7) == 0:
            self._data.append(0)
        if value & 1:
            self._data[self.bit_count >> 3] |= 1 << (self.bit_count & 7)
        self.bit_count += 1
        return None

    def bits(self, value: int, count: int) -> None:
        for i in range(count):
            self.bit((value >> i) & 1)
        return None

    def uint8(self, value: int) -> None:
        self.bits(value, 8)
        return None

    def uint16(self, value: int) -> None:
        self.bits(value, 16)
        return None

    def uint32(self, value: int) -> None:
        self.bits(value, 32)
        return None

    def uint64(self, value: int) -> None:
        self.bits(value, 64)
        return None

    def int32(self, value: int) -> None:
        self.uint32(value & 4294967295)
        return None

    def packed_int(self, value: int, variant: str = "dfm") -> None:
        if variant == "dfm":
            while True:
                encoded = (value & 127) << 1 | (1 if value >= 128 else 0)
                self.uint8(encoded)
                value >>= 7
                if value == 0:
                    return None
        while True:
            encoded = (value & 127) | (128 if value >= 128 else 0)
            self.uint8(encoded)
            value >>= 7
            if value == 0:
                return None

    def serialize_int(self, value: int, maximum: int) -> None:
        if value >= maximum:
            raise BitError(f"SerializeInt value {value} >= maximum {maximum}")
        current = 0
        mask = 1
        while current + mask < maximum:
            set_bit = (value & mask) != 0
            self.bit(1 if set_bit else 0)
            if set_bit:
                current |= mask
            mask <<= 1
        return None

    def fstring(self, value: str) -> None:
        try:
            raw = value.encode("utf-8")
            self.int32(len(raw) + 1)
            for b in raw:
                self.uint8(b)
            self.uint8(0)
        except UnicodeEncodeError:
            raw16 = value.encode("utf-16-le")
            units = [
                raw16[i] | (raw16[i + 1] << 8)
                for i in range(0, len(raw16), 2)
            ]
            self.int32(-(len(units) + 1))
            for unit in units:
                self.uint16(unit)
            self.uint16(0)
        return None

    def append(self, data: bytes, count: int) -> None:
        if count <= 0:
            return None
        avail = len(data) << 3
        eff = count if count <= avail else avail
        nbytes = (eff + 7) >> 3
        src_val = int.from_bytes(data[:nbytes], "little")
        if eff < nbytes << 3:
            src_val &= (1 << eff) - 1
        p = self.bit_count
        byte_i = p >> 3
        shift = p & 7
        out_len = (p + count + 7) >> 3
        buf = self._data
        if len(buf) < out_len:
            buf.extend(bytes(out_len - len(buf)))
        if shift == 0:
            if eff:
                buf[byte_i : byte_i + nbytes] = src_val.to_bytes(nbytes, "little")
        else:
            win = out_len - byte_i
            old = int.from_bytes(bytes(buf[byte_i:out_len]), "little")
            merged = (old | (src_val << shift)).to_bytes(win, "little")
            buf[byte_i:out_len] = merged
        self.bit_count = p + count
        return None

    def terminated_bytes(self) -> bytes:
        out = BitWriter()
        out._data = bytearray(self._data)
        out.bit_count = self.bit_count
        out.bit(1)
        return out.bytes()
