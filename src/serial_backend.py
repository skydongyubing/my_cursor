"""Thread-safe serial port wrapper for UI and bootloader workers."""

from __future__ import annotations

import threading
from typing import Optional

import serial


def parity_from_string(name: str) -> str:
    n = name.strip().upper()
    if n in ("N", "NONE", ""):
        return serial.PARITY_NONE
    if n in ("E", "EVEN"):
        return serial.PARITY_EVEN
    if n in ("O", "ODD"):
        return serial.PARITY_ODD
    return serial.PARITY_NONE


def parity_to_label(p: str) -> str:
    if p == serial.PARITY_EVEN:
        return "EVEN"
    if p == serial.PARITY_ODD:
        return "ODD"
    return "NONE"


class SerialBackend:
    """Thin locked wrapper around pyserial."""

    def __init__(self) -> None:
        self._ser: Optional[serial.Serial] = None
        self._lock = threading.Lock()

    @property
    def is_open(self) -> bool:
        return self._ser is not None and self._ser.is_open

    def open(
        self,
        port: str,
        baudrate: int,
        parity: str = serial.PARITY_EVEN,
        timeout: float = 1.0,
    ) -> None:
        self.close()
        self._ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=parity,
            stopbits=serial.STOPBITS_ONE,
            timeout=timeout,
            write_timeout=timeout,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        )

    def close(self) -> None:
        with self._lock:
            if self._ser is not None:
                try:
                    if self._ser.is_open:
                        self._ser.close()
                except Exception:
                    # 设备已拔出时关闭可能抛异常，确保句柄引用仍被清理
                    pass
                finally:
                    self._ser = None

    def check_alive(self) -> bool:
        """轻量探测串口是否仍有效（设备拔出返回 False）。"""
        with self._lock:
            if self._ser is None or not self._ser.is_open:
                return False
            try:
                self._ser.in_waiting
            except (serial.SerialException, OSError):
                return False
            return True

    def reconfigure(
        self,
        baudrate: Optional[int] = None,
        parity: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        with self._lock:
            if self._ser is None or not self._ser.is_open:
                raise RuntimeError("Port not open")
            if baudrate is not None:
                self._ser.baudrate = baudrate
            if parity is not None:
                self._ser.parity = parity
            if timeout is not None:
                self._ser.timeout = timeout
                self._ser.write_timeout = timeout

    def write(self, data: bytes) -> None:
        with self._lock:
            if self._ser is None or not self._ser.is_open:
                raise RuntimeError("Port not open")
            self._ser.write(data)
            self._ser.flush()

    def read(self, size: int, timeout: Optional[float] = None) -> bytes:
        with self._lock:
            if self._ser is None or not self._ser.is_open:
                raise RuntimeError("Port not open")
            old = self._ser.timeout
            if timeout is not None:
                self._ser.timeout = timeout
            try:
                return self._ser.read(size)
            finally:
                self._ser.timeout = old

    def reset_input_buffer(self) -> None:
        with self._lock:
            if self._ser is None or not self._ser.is_open:
                raise RuntimeError("Port not open")
            self._ser.reset_input_buffer()

    def set_dtr(self, level: bool) -> None:
        with self._lock:
            if self._ser is None or not self._ser.is_open:
                raise RuntimeError("Port not open")
            self._ser.dtr = level

    def set_rts(self, level: bool) -> None:
        with self._lock:
            if self._ser is None or not self._ser.is_open:
                raise RuntimeError("Port not open")
            self._ser.rts = level

    def as_bootloader_serial(self) -> "_BootloaderSerialAdapter":
        """Adapter exposing .timeout + read/write for Stm32UartBootloader."""
        return _BootloaderSerialAdapter(self)

    def get_config(self) -> dict:
        """返回当前串口配置用于诊断。"""
        if self._ser is None or not self._ser.is_open:
            return {}
        return {
            "baudrate": self._ser.baudrate,
            "bytesize": self._ser.bytesize,
            "parity": self._ser.parity,
            "stopbits": self._ser.stopbits,
            "timeout": self._ser.timeout,
        }


class _BootloaderSerialAdapter:
    """SerialLike adapter that forwards to SerialBackend with locking."""

    def __init__(self, backend: SerialBackend) -> None:
        self._b = backend
        self._timeout: float = 1.0

    @property
    def timeout(self) -> float:
        return self._timeout

    @timeout.setter
    def timeout(self, value: float) -> None:
        self._timeout = float(value)

    def write(self, data: bytes) -> int:
        self._b.write(data)
        return len(data)

    def read(self, size: int = 1) -> bytes:
        return self._b.read(size, timeout=self._timeout)

    def reset_input_buffer(self) -> None:
        self._b.reset_input_buffer()
