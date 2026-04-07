#!/usr/bin/env python3
"""详细调试 Get 命令响应"""

import serial
import time

PORT = "COM6"
BAUDRATE = 115200
TIMEOUT = 2.0

def main():
    print("打开串口...")
    ser = serial.Serial(
        port=PORT,
        baudrate=BAUDRATE,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_EVEN,
        stopbits=serial.STOPBITS_ONE,
        timeout=TIMEOUT,
        write_timeout=TIMEOUT,
    )
    
    ser.rts = False
    ser.dtr = False
    ser.reset_input_buffer()
    
    print("等待 4 秒...")
    time.sleep(4.0)
    ser.reset_input_buffer()
    
    print("发送 Get 命令 0x00 0xFF...")
    ser.write(b"\x00\xFF")
    
    # 逐字节读取，显示每个字节
    print("读取响应:")
    bytes_list = []
    for i in range(20):  # 最多读取20字节
        data = ser.read(1)
        if not data:
            print(f"  超时在第 {i} 字节")
            break
        b = data[0]
        bytes_list.append(b)
        if b == 0x79:
            print(f"  字节{i}: 0x{b:02X} = ACK")
        elif b == 0x1F:
            print(f"  字节{i}: 0x{b:02X} = NACK")
        else:
            print(f"  字节{i}: 0x{b:02X}")
    
    print(f"\n完整数据: {' '.join(f'{b:02X}' for b in bytes_list)}")
    print(f"共 {len(bytes_list)} 字节")
    
    ser.close()

if __name__ == "__main__":
    main()
