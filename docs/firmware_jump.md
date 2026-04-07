# 固件侧：串口命令进入 ROM Bootloader

PC 工具上的 **BOOTLOADER** 按钮只会通过 UART **发送你配置的十六进制字节**。STM32 在正常运行用户程序时，**不会**因为收到任意串口数据就自动进入 ROM Bootloader；你必须在固件里完成下列之一。

## 1. 在用户固件中接收魔数并跳转

1. 使用与 PC 工具相同的 **波特率** 与 **校验位**（若 PC 使用 NONE 发送魔数，则 UART 也应为 8N1）。
2. 在接收中断或 DMA 中识别魔数（例如与 PC 中 `55 AA 42 4C` 一致）。
3. 识别后调用「跳转到系统存储区」逻辑：关闭全局中断、`SysTick`、反初始化外设与 UART，然后设置主栈指针并跳转到 **系统存储区起始地址**。

STM32F40x 系列系统存储区起始地址一般为 **`0x1FFF0000`**（以 [AN2606](https://www.st.com/resource/en/application_note/cd00167594.pdf) 与具体型号数据手册为准）。跳转前请阅读 ST 应用笔记中关于 **从用户代码跳转到 Bootloader** 的说明，保证栈指针与向量表符合要求。

典型步骤（概念性，需按你使用的 HAL/LL 与启动文件调整）：

- `__disable_irq()`；
- 反初始化已打开的 `RCC`、外设与 `SysTick`；
- 从 `0x1FFF0000` 读取 MSP，从 `0x1FFF0004` 读取 `Reset_Handler` 地址；
- `__set_MSP(msp)`，然后跳转到 `Reset_Handler`。

也可在收到命令后 **仅执行系统复位**（`NVIC_SystemReset()`），同时硬件将 **`BOOT0` 拉高**，使下次复位从系统存储区启动——这需要你的硬件电路支持。

## 2. 使用 DTR 控制复位 / BOOT0

若 USB 转串口芯片的 **DTR** 连接至 **NRST**（或经电路复位 MCU），PC 工具可在发送魔数后拉低 DTR 一段时间再释放，产生复位脉冲。是否进入 ROM Bootloader 仍取决于 **BOOT0 / BOOT1** 引脚电平与选项字节，请对照你的原理图与 [AN2606](https://www.st.com/resource/en/application_note/cd00167594.pdf)。

## 3. ROM Bootloader 接线（UART）

USART 引脚与 Bootloader 所用外设以 **芯片数据手册与 AN2606** 为准；常见开发板使用 **USART1**（例如 PA9/PA10）。PC 工具在烧录阶段需使用 **偶校验（EVEN）** 才能与 AN3155 协议一致。
