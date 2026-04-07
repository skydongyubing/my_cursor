#!/usr/bin/env python3
"""测试 Write Memory 命令"""

import serial
import time

PORT = "COM6"
BAUDRATE = 115200
ACK = 0x79
NACK = 0x1F

def main():
    print("打开串口...")
    ser = serial.Serial(
        port=PORT,
        baudrate=BAUDRATE,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_EVEN,
        stopbits=serial.STOPBITS_ONE,
        timeout=5.0,
        write_timeout=5.0,
    )
    
    ser.rts = False
    ser.dtr = False
    ser.reset_input_buffer()
    
    print("等待 4 秒...")
    time.sleep(4.0)
    ser.reset_input_buffer()
    
    # Step 1: Get 命令
    print("\n1. 发送 Get 命令 0x00 0xFF...")
    ser.write(b"\x00\xFF")
    time.sleep(0.5)
    response = ser.read(20)
    print(f"   收到: {response.hex()}")
    
    # Step 2: 发送 Write Memory 命令
    print("\n2. 发送 Write 命令 0x31 0xCE...")
    ser.write(b"\x31\xCE")  # 0x31 ^ 0xFF = 0xCE
    time.sleep(0.5)
    response = ser.read(1)
    print(f"   收到: {response.hex() if response else '超时'}")
    if response and response[0] == ACK:
        print("   ACK - 继续")
    else:
        print("   NACK 或无响应!")
        ser.close()
        return
    
    # Step 3: 发送地址 0x08000000
    addr = 0x08000000
    addr_bytes = bytes([(addr >> 0) & 0xFF, (addr >> 8) & 0xFF, 
                        (addr >> 16) & 0xFF, (addr >> 24) & 0xFF])
    crc = addr_bytes[0] ^ addr_bytes[1] ^ addr_bytes[2] ^ addr_bytes[3]
    addr_cmd = addr_bytes + bytes([crc])
    print(f"\n3. 发送地址 0x{addr:08X}: {addr_cmd.hex()}")
    ser.write(addr_cmd)
    time.sleep(0.5)
    response = ser.read(1)
    print(f"   收到: {response.hex() if response else '超时'}")
    if response and response[0] == ACK:
        print("   ACK - 继续")
    else:
        print("   NACK 或无响应!")
        ser.close()
        return
    
    # Step 4: 发送数据 (8字节测试数据)
    test_data = bytes([0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77])
    n = (len(test_data) - 1) & 0xFF
    crc = 0xFF
    for b in test_data:
        crc ^= b
    data_cmd = bytes([n]) + test_data + bytes([crc])
    print(f"\n4. 发送 {len(test_data)} 字节数据: {data_cmd.hex()}")
    ser.write(data_cmd)
    time.sleep(0.5)
    response = ser.read(1)
    print(f"   收到: {response.hex() if response else '超时'}")
    if response and response[0] == ACK:
        print("   成功! Write 命令完成")
    else:
        print("   NACK 或无响应!")
    
    ser.close()

if __name__ == "__main__":
    main()
