"""STM32 ROM UART bootloader protocol (AN3155)."""

from __future__ import annotations

import time
from typing import Callable, Optional, Protocol

ACK = 0x79
NACK = 0x1F


class SerialLike(Protocol):
    """Minimal serial interface used by the bootloader."""

    timeout: float

    def write(self, data: bytes) -> int: ...

    def read(self, size: int = 1) -> bytes: ...

    def reset_input_buffer(self) -> None: ...


class BootloaderError(Exception):
    """Protocol or chip rejected the operation."""


def _xor_checksum(data: bytes) -> int:
    c = 0
    for b in data:
        c ^= b
    return c & 0xFF


class Stm32UartBootloader:
    """AN3155 UART bootloader session (MCU must already be in ROM bootloader)."""

    def __init__(self, ser: SerialLike) -> None:
        self._ser = ser
        self.extended_erase = False
        self.version = 0

    def _wait_ack(self, info: str = "") -> None:
        b = self._ser.read(1)
        if len(b) != 1:
            raise BootloaderError(f"Timeout waiting for ACK ({info})")
        v = b[0]
        if v == ACK:
            return
        if v == NACK:
            raise BootloaderError(f"NACK {info}: got 0x1F")
        raise BootloaderError(f"Unexpected response 0x{v:02X} ({info})")

    def _send_cmd(self, cmd: int, info: str = "") -> None:
        self._ser.write(self._cmd_pair(cmd))
        try:
            self._wait_ack(info)
        except BootloaderError as e:
            if "Timeout" in str(e):
                time.sleep(0.05)
                self._ser.write(bytes([cmd ^ 0xFF]))
                self._wait_ack(info)
            else:
                raise

    def _cmd_pair(self, cmd: int) -> bytes:
        return bytes([cmd, cmd ^ 0xFF])

    def cmd_get_version(self) -> int:
        self._send_cmd(0x00, "Get (0x00)")
        data = self._ser.read(2)
        if len(data) < 2:
            raise BootloaderError("Get: short response")
        version = data[0]
        self._wait_ack("Get end")
        return version

    def sync(self, retries: int = 5, delay_s: float = 0.05) -> None:
        """Init (0x7F) then Get (0x00 0xFF) to sync with bootloader and get version."""
        last_exception: Optional[Exception] = None
        for attempt in range(retries):
            self._ser.reset_input_buffer()
            time.sleep(0.013)
            self._ser.write(b"\x7F")
            try:
                b = self._ser.read(1)
                if not b:
                    time.sleep(delay_s)
                    continue
                
                if b[0] not in (ACK, NACK):
                    time.sleep(delay_s)
                    continue
                
                time.sleep(0.003)
                self._ser.write(bytes([0x00, 0xFF]))
                
                data = bytearray()
                while True:
                    r = self._ser.read(1)
                    if not r:
                        break
                    data.append(r[0])
                    if len(data) >= 2 and data[-1] == ACK and data[-2] == ACK:
                        break
                
                if len(data) < 4:
                    raise BootloaderError(f"Sync: response too short ({len(data)} bytes)")
                
                if data[0] != ACK:
                    raise BootloaderError(f"Sync: expected ACK after Get, got 0x{data[0]:02X}")
                
                self.version = data[1]
                self.extended_erase = 0x44 in data
                
                if data[-1] != ACK:
                    raise BootloaderError(f"Sync: expected trailing ACK, got 0x{data[-1]:02X}")
                
                return
            except BootloaderError as e:
                last_exception = e
            time.sleep(delay_s)
        raise BootloaderError(f"Sync failed after {retries} attempts: {last_exception}")

    def cmd_get(self) -> int:
        """Return bootloader version."""
        self._ser.write(bytes([0x00, 0xFF]))
        ack = self._ser.read(1)
        if not ack or ack[0] != ACK:
            raise BootloaderError(f"Get: expected ACK, got {ack.hex() if ack else 'None'}")
        
        v = self._ser.read(1)
        if len(v) != 1:
            raise BootloaderError("Get: short response")
        version = v[0]
        
        self._ser.reset_input_buffer()
        return version

    def cmd_get_id_v2(self, addr: int) -> None:
        """Send address: 0x08 0x00 0x00 0x00 0x08"""
        self._ser.write(bytes([0x08, 0x00, 0x00, 0x00, 0x08]))
        self._wait_ack("Address")

    def cmd_get_id(self) -> int:
        """Return chip PID."""
        self._send_cmd(0x02, "GetID (0x02)")
        ln = self._ser.read(1)
        if len(ln) != 1:
            raise BootloaderError("GetID: missing length")
        n_minus_1 = ln[0]
        rest = self._ser.read(n_minus_1 + 1)
        if len(rest) != n_minus_1 + 1:
            raise BootloaderError("GetID: PID bytes truncated")
        self._wait_ack("GetID end")
        pid = 0
        for b in rest:
            pid = (pid << 8) | b
        return pid

    def _encode_addr(self, addr: int) -> bytes:
        b3 = (addr >> 24) & 0xFF
        b2 = (addr >> 16) & 0xFF
        b1 = (addr >> 8) & 0xFF
        b0 = addr & 0xFF
        crc = b0 ^ b1 ^ b2 ^ b3
        return bytes([b3, b2, b1, b0, crc])

    def cmd_erase_all(self) -> None:
        """Mass erase using page erase (0x44)."""
        self._ser.write(bytes([0x44]))
        time.sleep(0.00019)
        self._ser.write(bytes([0xBB]))
        self._wait_ack("Erase cmd")
        
        erase_cmd = bytes([
            0x00, 0x03,
            0x00, 0x00,
            0x00, 0x01,
            0x00, 0x02,
            0x00, 0x03,
            0x03, 0x03
        ])
        
        self._ser.write(erase_cmd)
        
        old = self._ser.timeout
        self._ser.timeout = max(old, 30.0)
        try:
            time.sleep(0.7)
            self._wait_ack("Extended Erase")
        finally:
            self._ser.timeout = old

    def cmd_write_memory(self, addr: int, data: bytes) -> None:
        if len(data) > 256 or len(data) == 0:
            raise ValueError("Write chunk must be 1..256 bytes")
        
        self._ser.write(bytes([0x31]))
        self._ser.write(bytes([0xCE]))
        self._wait_ack("Write cmd")
        
        encoded_addr = self._encode_addr(addr)
        self._ser.write(encoded_addr)
        self._wait_ack("Write address")
        
        n = (len(data) - 1) & 0xFF
        self._ser.write(bytes([n]))
        
        data_crc = n
        for b in data:
            data_crc ^= b
        
        addr_crc = encoded_addr[4] if len(encoded_addr) > 4 else (addr & 0xFF)
        print(f"[WRITE] addr=0x{addr:08X} addr_encoded={encoded_addr.hex()} n=0x{n:02X} data_len={len(data)} data_crc=0x{data_crc:02X}")
        print(f"[WRITE] data={data.hex()}")
        
        self._ser.write(data)
        self._ser.write(bytes([data_crc]))
        self._wait_ack("Write data")

    def write_memory_stream(
        self,
        base_addr: int,
        data: bytes,
        progress: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        """Write firmware image starting at base_addr (typically 0x08000000)."""
        total = len(data)
        offset = 0
        addr = base_addr
        while offset < total:
            chunk_len = min(256, total - offset)
            chunk = data[offset : offset + chunk_len]
            if chunk_len < 256:
                chunk = chunk + bytes([0xFF] * (256 - chunk_len))
            self.cmd_write_memory(addr, chunk)
            offset += chunk_len
            addr += chunk_len
            if progress:
                progress(offset, total)

    def cmd_read_memory(self, addr: int, length: int) -> bytes:
        if length > 256 or length == 0:
            raise ValueError("Read chunk must be 1..256 bytes")
        
        self._ser.write(bytes([0x11]))
        time.sleep(1.0)
        self._ser.write(bytes([0xEE]))
        self._wait_ack("Read cmd")
        
        self._ser.write(self._encode_addr(addr))
        self._wait_ack("Read address")
        
        n = (length - 1) & 0xFF
        self._ser.write(bytes([n, n ^ 0xFF]))
        time.sleep(0.002)
        self._wait_ack("Read length")
        out = self._ser.read(length)
        if len(out) != length:
            raise BootloaderError("ReadMemory: short data")
        return out

    def read_memory_stream(self, addr: int, length: int) -> bytes:
        out = bytearray()
        while length > 0:
            n = min(256, length)
            out += self.cmd_read_memory(addr, n)
            addr += n
            length -= n
        return bytes(out)

    def verify(
        self,
        base_addr: int,
        data: bytes,
        progress: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        total = len(data)
        offset = 0
        addr = base_addr
        while offset < total:
            n = min(256, total - offset)
            rd = self.cmd_read_memory(addr, n)
            if rd != data[offset : offset + n]:
                raise BootloaderError(f"Verify mismatch at 0x{addr:08X}")
            offset += n
            addr += n
            if progress:
                progress(offset, total)
