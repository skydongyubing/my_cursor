"""Intel HEX parser used for STM32 UART bootloader flashing.

It parses records and returns contiguous byte segments as (address, data).
The parser supports:
- Data Record (00)
- End Of File Record (01)
- Extended Segment Address Record (02)
- Extended Linear Address Record (04)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class HexSegment:
    address: int
    data: bytes


def _parse_hex_byte(s: str) -> int:
    return int(s, 16)


def _validate_checksum(ll: int, addr: int, rectype: int, data: bytes, checksum: int) -> None:
    # Intel HEX checksum: two's complement of the least significant byte of the sum
    # of (ll + addr_hi + addr_lo + rectype + data_bytes).
    total = ll + ((addr >> 8) & 0xFF) + (addr & 0xFF) + rectype + sum(data)
    calc = ((~total + 1) & 0xFF)
    if calc != checksum:
        raise ValueError(f"Intel HEX checksum mismatch: got 0x{checksum:02X}, expected 0x{calc:02X}")


def parse_intel_hex(path: str) -> List[HexSegment]:
    p = Path(path)
    text = p.read_text(encoding="utf-8", errors="ignore")
    if not text.strip():
        raise ValueError("HEX 文件为空")

    # Build a sparse address->byte map then convert into contiguous segments.
    memory: Dict[int, int] = {}
    upper = 0

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if not line.startswith(":"):
            raise ValueError("Invalid Intel HEX line (missing ':')")

        # Minimum: :LLAAAATTCC
        if len(line) < 11:
            raise ValueError("Invalid Intel HEX line length")

        ll = _parse_hex_byte(line[1:3])
        addr = int(line[3:7], 16)
        rectype = _parse_hex_byte(line[7:9])
        data_start = 9
        data_end = data_start + ll * 2
        data_hex = line[data_start:data_end]
        data = bytes.fromhex(data_hex) if ll else b""
        checksum = _parse_hex_byte(line[data_end : data_end + 2])

        _validate_checksum(ll, addr, rectype, data, checksum)

        if rectype == 0x00:
            base = upper + addr
            for i, b in enumerate(data):
                a = base + i
                if a in memory and memory[a] != b:
                    raise ValueError(f"HEX overlapping data at address 0x{a:08X}")
                memory[a] = b
        elif rectype == 0x01:
            break
        elif rectype == 0x02:
            # Extended Segment Address: upper 16 bits of (segment << 4)
            if ll != 2:
                raise ValueError("Invalid Extended Segment Address record length")
            upper = int.from_bytes(data, byteorder="big") << 4
        elif rectype == 0x04:
            # Extended Linear Address: upper 16 bits of (linear << 16)
            if ll != 2:
                raise ValueError("Invalid Extended Linear Address record length")
            upper = int.from_bytes(data, byteorder="big") << 16
        else:
            # Types 03, 05, 06... are not needed for flashing in most STM32 cases.
            # We treat them as non-fatal.
            continue

    if not memory:
        raise ValueError("HEX 文件未包含任何数据记录")

    addresses = sorted(memory.keys())
    segments: List[HexSegment] = []
    seg_start = addresses[0]
    buf = bytearray()
    last = addresses[0] - 1

    for a in addresses:
        if a != last + 1:
            if buf:
                segments.append(HexSegment(address=seg_start, data=bytes(buf)))
            seg_start = a
            buf = bytearray()
        buf.append(memory[a])
        last = a

    if buf:
        segments.append(HexSegment(address=seg_start, data=bytes(buf)))

    return segments


