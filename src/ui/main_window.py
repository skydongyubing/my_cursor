"""Main Qt window: serial, BOOTLOADER command, AN3155 flash."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import List, Optional

import serial
import serial.tools.list_ports
from PySide6.QtCore import QObject, QSettings, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.serial_backend import SerialBackend, parity_from_string, parity_to_label
from src.stm32_uart_bootloader import BootloaderError, Stm32UartBootloader
from src.intel_hex import HexSegment, parse_intel_hex


def _parse_hex_bytes(text: str) -> bytes:
    """Parse '55 AA 01' or '55AA01' into bytes."""
    s = re.sub(r"[^0-9a-fA-F]", "", text)
    if len(s) % 2 != 0:
        raise ValueError("十六进制长度必须为偶数个字符")
    return bytes(int(s[i : i + 2], 16) for i in range(0, len(s), 2))


def _parse_hex_addr(text: str) -> int:
    t = text.strip()
    if t.startswith("0x") or t.startswith("0X"):
        return int(t, 16)
    return int(t, 16) if re.match(r"^[0-9a-fA-F]+$", t) else int(t, 0)


class FlashWorker(QObject):
    finished = Signal()
    success = Signal()
    failed = Signal(str)
    log_line = Signal(str)
    progress = Signal(int, int)

    def __init__(self, backend: SerialBackend, firmware_path: str, base_addr: int, verify: bool) -> None:
        super().__init__()
        self._backend = backend
        self._firmware_path = firmware_path
        self._base_addr = base_addr
        self._verify = verify

    @Slot()
    def run(self) -> None:
        try:
            p = Path(self._firmware_path)
            if not p.is_file():
                raise BootloaderError("固件文件不存在")

            adapter = self._backend.as_bootloader_serial()
            adapter.timeout = 5.0
            bl = Stm32UartBootloader(adapter)
            bl._ser.timeout = 5.0

            cfg = self._backend.get_config()
            self.log_line.emit(f"配置: baud={cfg.get('baudrate')} bits={cfg.get('bytesize')} parity={cfg.get('parity')} stop={cfg.get('stopbits')}")
            self._backend.reset_input_buffer()

            self.log_line.emit("开始烧录流程...")
            time.sleep(4.0)
            self._backend.reset_input_buffer()
            
            ser = self._backend._ser
            
            def expect_ack(ser, timeout_s=1.0) -> bytes:
                old = ser.timeout
                ser.timeout = timeout_s
                try:
                    b = ser.read(1)
                finally:
                    ser.timeout = old
                if not b:
                    raise BootloaderError("等待 ACK 超时")
                if b[0] != 0x79:
                    raise BootloaderError(f"期望 ACK (0x79)，收到 0x{b[0]:02X}")
                return b

            self.log_line.emit("1. 发送 Read 命令 0x11...")
            ser.write(bytes([0x11]))
            time.sleep(1.0)
            ser.write(bytes([0xEE]))
            ack = expect_ack(ser)
            self.log_line.emit(f"   收到: {ack.hex()}")

            self.log_line.emit("2. 发送地址 0x08...")
            ser.write(bytes([0x08, 0x00, 0x00, 0x00, 0x08]))
            ack = expect_ack(ser)
            self.log_line.emit(f"   收到: {ack.hex()}")
            
            self.log_line.emit("3. 发送 Get 命令 0x00 0xFF...")
            ser.write(bytes([0x00, 0xFF]))
            resp = ser.read(2)
            self.log_line.emit(f"   收到: {resp.hex() if resp else 'None'}")
            if not resp or resp[0] != 0x79:
                raise BootloaderError(f"Get 命令期望 ACK (0x79)，收到 {resp.hex() if resp else 'None'}")

            self.log_line.emit("4. 发送 Erase 命令 0x44...")
            ser.write(bytes([0x44]))
            time.sleep(0.00019)
            ser.write(bytes([0xBB]))
            ack = expect_ack(ser)
            self.log_line.emit(f"   收到: {ack.hex()}")
            
            self.log_line.emit("5. 发送擦除参数...")
            ser.write(bytes([0x00, 0x03, 0x00, 0x00, 0x00, 0x01, 0x00, 0x02, 0x00, 0x03, 0x03]))
            time.sleep(0.7)
            ack = expect_ack(ser)
            self.log_line.emit(f"   收到: {ack.hex()}")
            
            self.log_line.emit("擦除完成...")

            self.log_line.emit("开始写入 Flash...")

            firmware_ext = p.suffix.lower()
            is_hex = firmware_ext == ".hex"

            def prog(cur: int, total: int) -> None:
                self.progress.emit(cur, total)

            if is_hex:
                self.log_line.emit(f"解析 Intel HEX: {p.name}")
                segments = parse_intel_hex(self._firmware_path)

                min_addr = min(s.address for s in segments)
                max_addr = max(s.address + len(s.data) - 1 for s in segments)
                flash_base_guess = 0x08000000
                shift = 0
                if max_addr < flash_base_guess:
                    shift = self._base_addr - 0x00000000
                if shift != 0:
                    self.log_line.emit(f"HEX 地址偏移检测: 全部小于 0x{flash_base_guess:08X}，应用 shift=0x{shift:08X}")

                shifted: List[HexSegment] = []
                for s in segments:
                    shifted.append(HexSegment(address=(s.address + shift), data=s.data))
                
                chunks: List[tuple[int, bytes]] = []
                total = 0
                skipped = 0
                for s in shifted:
                    for off in range(0, len(s.data), 256):
                        chunk = s.data[off : off + 256]
                        addr = s.address + off
                        if chunk == bytes([0x00] * len(chunk)):
                            skipped += 1
                            continue
                        chunks.append((addr, chunk))
                        total += len(chunk)
                if skipped > 0:
                    self.log_line.emit(f"跳过 {skipped} 块全 0x00 数据")

                self.log_line.emit(f"共 {len(chunks)} 块写入数据，总字节数 {total}")
                written = 0
                for i, (addr, chunk) in enumerate(chunks):
                    bl.cmd_write_memory(addr, chunk)
                    written += len(chunk)
                    prog(written, total)

                self.log_line.emit(f"HEX 写入完成：总写入 {written} 字节")
                if self._verify:
                    self.log_line.emit("校验读取（按块读回对比）...")
                    verified = 0
                    for addr, chunk in chunks:
                        rd = bl.cmd_read_memory(addr, len(chunk))
                        if rd != chunk:
                            raise BootloaderError(f"校验失败：0x{addr:08X} 起始地址数据不一致")
                        verified += len(chunk)
                        prog(verified, total)
                    self.log_line.emit("校验通过")
            else:
                firmware = p.read_bytes()
                self.log_line.emit(f"读取 BIN: {p.name} ({len(firmware)} 字节)")
                bl.write_memory_stream(self._base_addr, firmware, progress=prog)
                self.log_line.emit(f"已写入 {len(firmware)} 字节 @ 0x{self._base_addr:08X}")
                if self._verify:
                    self.log_line.emit("校验读取...")
                    bl.verify(self._base_addr, firmware, progress=prog)
                    self.log_line.emit("校验通过")
            self.log_line.emit("完成")
            self.success.emit()
        except BootloaderError as e:
            self.failed.emit(str(e))
        except OSError as e:
            self.failed.emit(str(e))
        except Exception as e:
            self.failed.emit(f"{type(e).__name__}: {e}")
        finally:
            self.finished.emit()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("STM32F407 UART 烧录")
        self.resize(720, 560)
        self._backend = SerialBackend()
        self._flash_thread: Optional[QThread] = None
        self._flash_worker: Optional[FlashWorker] = None
        self._settings = QSettings("STM32UartProgrammer", "MainWindow")

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        conn_box = QGroupBox("串口")
        conn_form = QFormLayout(conn_box)
        self._port_combo = QComboBox()
        self._baud_combo = QComboBox()
        for b in (115200, 9600, 57600, 38400):
            self._baud_combo.addItem(str(b), b)
        self._baud_combo.setCurrentText("115200")
        self._parity_combo = QComboBox()
        self._parity_combo.addItem("EVEN (官方 CubeProgrammer)", "EVEN")
        self._parity_combo.addItem("NONE", "NONE")
        self._parity_combo.addItem("ODD", "ODD")
        self._btn_refresh = QPushButton("刷新端口")
        self._btn_connect = QPushButton("连接")
        self._btn_disconnect = QPushButton("断开")
        self._btn_disconnect.setEnabled(False)
        self._btn_read_info = QPushButton("读取 Bootloader")
        self._btn_read_info.setEnabled(False)
        row_port = QHBoxLayout()
        row_port.addWidget(self._port_combo, 1)
        row_port.addWidget(self._btn_refresh)
        conn_form.addRow("端口", row_port)
        conn_form.addRow("波特率", self._baud_combo)
        conn_form.addRow("校验位", self._parity_combo)
        row_btns = QHBoxLayout()
        row_btns.addWidget(self._btn_connect)
        row_btns.addWidget(self._btn_disconnect)
        row_btns.addWidget(self._btn_read_info)
        conn_form.addRow("", row_btns)
        layout.addWidget(conn_box)

        boot_box = QGroupBox("进入 Bootloader")
        boot_form = QFormLayout(boot_box)
        self._boot_hex = QLineEdit()
        self._boot_hex.setPlaceholderText("例如: 55 AA 01 00（发送到用户程序；需在 MCU 固件中处理）")
        self._boot_hex.setText(self._settings.value("boot_hex", "55 AA AA 55 01 00 01 77 77 CC", str))
        self._dtr_after = QCheckBox("发送后 DTR 低电平复位（毫秒）")
        self._dtr_after.setChecked(self._settings.value("dtr_after", False, bool))
        self._dtr_ms = QSpinBox()
        self._dtr_ms.setRange(1, 2000)
        self._dtr_ms.setValue(int(self._settings.value("dtr_ms", 100, int)))
        row_dtr = QHBoxLayout()
        row_dtr.addWidget(self._dtr_after)
        row_dtr.addWidget(self._dtr_ms)
        row_dtr.addWidget(QLabel("ms"))
        self._btn_boot = QPushButton("BOOTLOADER")
        self._btn_boot.setToolTip("向串口发送上方十六进制字节；可选 DTR 脉冲复位 MCU。")
        boot_form.addRow("命令 (HEX)", self._boot_hex)
        boot_form.addRow("", row_dtr)
        boot_form.addRow("", self._btn_boot)
        layout.addWidget(boot_box)

        flash_box = QGroupBox("烧录 (.hex)")
        flash_form = QFormLayout(flash_box)
        self._file_edit = QLineEdit()
        self._file_edit.setText(self._settings.value("last_hex", "", str))
        self._btn_browse = QPushButton("浏览…")
        self._verify_check = QCheckBox("写入后校验")
        self._verify_check.setChecked(self._settings.value("verify", True, bool))
        row_file = QHBoxLayout()
        row_file.addWidget(self._file_edit, 1)
        row_file.addWidget(self._btn_browse)
        flash_form.addRow("固件文件", row_file)
        flash_form.addRow("", self._verify_check)
        self._btn_flash = QPushButton("擦除并烧录")
        self._btn_flash.setToolTip("要求 MCU 已进入 ROM UART Bootloader；校验位通常为 EVEN。")
        flash_form.addRow("", self._btn_flash)
        layout.addWidget(flash_box)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        layout.addWidget(self._progress)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(5000)
        layout.addWidget(self._log, 1)

        self._btn_refresh.clicked.connect(self._refresh_ports)
        self._btn_connect.clicked.connect(self._connect)
        self._btn_disconnect.clicked.connect(self._disconnect)
        self._btn_read_info.clicked.connect(self._read_bootloader_info)
        self._btn_boot.clicked.connect(self._send_bootloader_cmd)
        self._btn_browse.clicked.connect(self._browse_bin)
        self._btn_flash.clicked.connect(self._start_flash)

        self._refresh_ports()
        self._restore_port_selection()

    def _restore_port_selection(self) -> None:
        last = self._settings.value("last_port", "", str)
        if last:
            i = self._port_combo.findText(last)
            if i >= 0:
                self._port_combo.setCurrentIndex(i)
        last_file = self._settings.value("last_hex", "", str)
        if last_file and Path(last_file).is_file():
            self._file_edit.setText(last_file)
            self._analyze_and_log(last_file)

    def _save_settings(self) -> None:
        self._settings.setValue("boot_hex", self._boot_hex.text())
        self._settings.setValue("dtr_after", self._dtr_after.isChecked())
        self._settings.setValue("dtr_ms", self._dtr_ms.value())
        self._settings.setValue("last_hex", self._file_edit.text())
        self._settings.setValue("verify", self._verify_check.isChecked())
        self._settings.setValue("last_port", self._port_combo.currentText())
        self._settings.setValue("baud", self._baud_combo.currentText())
        self._settings.setValue("parity", self._parity_combo.currentData())

    @Slot()
    def _refresh_ports(self) -> None:
        current = self._port_combo.currentText()
        self._port_combo.clear()
        ports: List[str] = []
        for p in serial.tools.list_ports.comports():
            ports.append(p.device)
        for d in sorted(ports):
            self._port_combo.addItem(d)
        if current:
            i = self._port_combo.findText(current)
            if i >= 0:
                self._port_combo.setCurrentIndex(i)

    def _current_parity(self) -> str:
        label = self._parity_combo.currentData()
        return parity_from_string(label if isinstance(label, str) else "EVEN")

    def _append_log(self, text: str) -> None:
        self._log.appendPlainText(text)

    @Slot()
    def _connect(self) -> None:
        port = self._port_combo.currentText().strip()
        if not port:
            QMessageBox.warning(self, "串口", "请选择串口")
            return
        try:
            baud = int(self._baud_combo.currentText())
        except ValueError:
            baud = 115200
        try:
            self._backend.open(port, baud, parity=self._current_parity(), timeout=1.0)
        except serial.SerialException as e:
            QMessageBox.critical(self, "串口", str(e))
            return
        # Align with CubeProgrammer activation: set RTS/DTR low right after open.
        # Some boards wire these lines into BOOT/RESET timing.
        try:
            self._backend.set_rts(False)
            self._backend.set_dtr(False)
            self._backend.reset_input_buffer()
            time.sleep(0.5)  # 等待 MCU 稳定
        except Exception:
            pass
        self._append_log(f"已连接 {port} @ {baud} {parity_to_label(self._current_parity())}")
        self._btn_connect.setEnabled(False)
        self._btn_disconnect.setEnabled(True)
        self._btn_read_info.setEnabled(True)
        self._save_settings()

    @Slot()
    def _disconnect(self) -> None:
        try:
            self._backend.set_rts(True)
            self._backend.set_dtr(True)
        except Exception:
            pass
        self._backend.close()
        self._append_log("已断开")
        self._btn_connect.setEnabled(True)
        self._btn_disconnect.setEnabled(False)
        self._btn_read_info.setEnabled(False)

    @Slot()
    def _read_bootloader_info(self) -> None:
        if not self._backend.is_open:
            QMessageBox.warning(self, "串口", "请先连接串口")
            return
        try:
            from src.stm32_uart_bootloader import Stm32UartBootloader
            bl = Stm32UartBootloader(self._backend.as_bootloader_serial())
            bl.sync()
            pid = bl.cmd_get_id()
            self._append_log(f"Bootloader 版本: 0x{bl.version:02X}")
            self._append_log(f"芯片 PID: 0x{pid:04X}")
            self._append_log(f"扩展擦除: {'是' if bl.extended_erase else '否'}")
        except Exception as e:
            QMessageBox.critical(self, "Bootloader", f"读取失败: {e}")

    @Slot()
    def _send_bootloader_cmd(self) -> None:
        if not self._backend.is_open:
            QMessageBox.warning(self, "串口", "请先连接串口")
            return
        try:
            payload = _parse_hex_bytes(self._boot_hex.text())
        except ValueError as e:
            QMessageBox.warning(self, "命令", str(e))
            return
        self._save_settings()
        try:
            self._backend.reset_input_buffer()
            self._backend.write(payload)
            self._append_log(f"进入bootloader模式: {payload.hex(' ')}")
            time.sleep(0.1)
            resp = self._backend.read(7)
            expected = bytes([0x55, 0xAA, 0xAA, 0x55, 0x02, 0x00, 0x01])
            if resp == expected:
                self._append_log(f"进入bootloader模式成功: {resp.hex(' ')}")
            else:
                self._append_log(f"进入bootloader模式失败: {resp.hex(' ')}")
                QMessageBox.warning(self, "Bootloader", f"进入bootloader模式失败\n期望: {expected.hex(' ')}\n收到: {resp.hex(' ')}")
        except OSError as e:
            QMessageBox.critical(self, "串口", str(e))

    @Slot()
    def _browse_bin(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择固件", "", "Intel HEX (*.hex);;Binary (*.bin);;All (*.*)")
        if path:
            self._file_edit.setText(path)
            self._analyze_and_log(path)

    def _analyze_and_log(self, path: str) -> None:
        p = Path(path)
        suffix = p.suffix.lower()
        try:
            if suffix == ".hex":
                from src.intel_hex import parse_intel_hex
                segments = parse_intel_hex(path)
                for s in segments:
                    end_addr = s.address + len(s.data) - 1
                    chunks = (len(s.data) + 255) // 256
                    self._append_log(f"[HEX 解析] 起始: 0x{s.address:08X}, 结束: 0x{end_addr:08X}, 长度: {len(s.data)} 字节, 分块: {chunks}")
                    self._append_log(f"[HEX 解析] 起始地址已自动设置为: 0x{s.address:08X}")
                if len(segments) > 1:
                    total = sum(len(s.data) for s in segments)
                    self._append_log(f"[HEX 解析] 共 {len(segments)} 段, 总计 {total} 字节")
            else:
                data = p.read_bytes()
                chunks = (len(data) + 255) // 256
                base = 0x08000000
                end_addr = base + len(data) - 1
                self._append_log(f"[BIN 解析] 起始: 0x{base:08X}, 结束: 0x{end_addr:08X}, 长度: {len(data)} 字节, 分块: {chunks}")
        except Exception as e:
            self._append_log(f"[解析失败] {e}")

    def closeEvent(self, event) -> None:
        self._save_settings()
        if self._flash_thread and self._flash_thread.isRunning():
            self._flash_thread.quit()
            self._flash_thread.wait(3000)
        self._backend.close()
        super().closeEvent(event)

    @Slot()
    def _start_flash(self) -> None:
        if not self._backend.is_open:
            QMessageBox.warning(self, "串口", "请先连接串口")
            return
        path = self._file_edit.text().strip()
        if not path:
            QMessageBox.warning(self, "烧录", "请选择 .hex 文件（或 .bin 兼容）")
            return
        p = Path(path)
        if not p.is_file():
            QMessageBox.warning(self, "烧录", "文件不存在")
            return

        firmware_ext = p.suffix.lower()
        base = 0x08000000

        if self._parity_combo.currentData() != "EVEN":
            r = QMessageBox.question(
                self,
                "校验位",
                "STM32 ROM UART Bootloader 通常需要 EVEN 校验位。\n当前不是 EVEN，是否继续？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if r != QMessageBox.Yes:
                return

        self._save_settings()
        self._btn_flash.setEnabled(False)
        self._btn_boot.setEnabled(False)
        self._progress.setValue(0)

        self._flash_thread = QThread()
        self._flash_worker = FlashWorker(self._backend, str(p), base, self._verify_check.isChecked())
        self._flash_worker.moveToThread(self._flash_thread)
        self._flash_thread.started.connect(self._flash_worker.run)
        self._flash_worker.finished.connect(self._flash_thread.quit)
        self._flash_worker.finished.connect(self._flash_worker.deleteLater)
        self._flash_thread.finished.connect(self._on_flash_thread_finished)
        self._flash_worker.log_line.connect(self._append_log)
        self._flash_worker.progress.connect(self._on_flash_progress)
        self._flash_worker.failed.connect(self._on_flash_failed)
        self._flash_worker.success.connect(self._on_flash_success)

        self._flash_thread.start()

    @Slot()
    def _on_flash_thread_finished(self) -> None:
        self._flash_thread = None
        self._flash_worker = None
        self._btn_flash.setEnabled(True)
        self._btn_boot.setEnabled(True)

    @Slot(str)
    def _on_flash_failed(self, msg: str) -> None:
        self._append_log(f"错误: {msg}")
        QMessageBox.critical(self, "烧录失败", msg)

    @Slot()
    def _on_flash_success(self) -> None:
        QMessageBox.information(self, "烧录成功", "烧录成功，请重启设备")

    @Slot(int, int)
    def _on_flash_progress(self, cur: int, total: int) -> None:
        if total <= 0:
            return
        self._progress.setValue(int(cur * 100 / total))
