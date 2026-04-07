# STM32F407 UART 烧录与 Bootloader 入口工具

基于 Python 3、PySide6 与 pyserial 的小型桌面程序：通过 **STM32 ROM UART Bootloader（AN3155）** 烧录 `.hex`，并提供 **BOOTLOADER** 按钮向 MCU 发送可配置的十六进制命令（用于在用户固件中跳转进 ROM Bootloader，或配合 DTR 复位）。

## 环境

- Python 3.10+
- 依赖见 [`requirements.txt`](requirements.txt)

## 运行

在项目根目录执行：

```powershell
pip install -r requirements.txt
python -m src.main
```

## 使用要点

1. **ROM Bootloader 烧录**：MCU 须已进入系统存储区 Bootloader（上电时 `BOOT0` 配置或用户程序跳转到 ROM）。串口参数建议 **8E1（8 数据位、偶校验、1 停止位）**，波特率常见为 **115200**（与 ST 文档一致）。
2. **BOOTLOADER 按钮**：向串口发送界面中填写的十六进制字节（例如 `55 AA 42 4C`）。需在 **用户固件** 中解析该序列并执行跳转到 ROM Bootloader（见 [`docs/firmware_jump.md`](docs/firmware_jump.md)）。可选 **DTR 低电平复位**，用于配合 USB 转串口自动复位（依硬件连接而定）。
3. **烧录流程**：连接串口 → 确认校验位为 EVEN → 选择 `.hex` 文件 → **擦除并烧录**。`.hex` 会按 HEX 里的地址分块写入；`起始地址`主要用于 `.bin`（并用于 HEX 的地址偏移自动检测）。

## 文档

- 固件跳转与硬件说明：[`docs/firmware_jump.md`](docs/firmware_jump.md)
