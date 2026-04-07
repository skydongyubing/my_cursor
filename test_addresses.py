#!/usr/bin/env python3
"""测试不同地址"""

import serial
import time

PORT = "COM6"
BAUDRATE = 115200
ACK = 0x79
NACK = 0x1F

def test_address(ser, addr, label=""):
    """测试单个地址"""
    print(f"\n测试地址 0x{addr:08X} ({label})...")
    
    # 发送 Read 命令
    ser.write(b"\x11\xEE")
    time.sleep(0.3)
    response = ser.read(1)
    if not response or response[0] != ACK:
        print(f"  Read 命令被拒绝!")
        return False
    
    # 发送地址
    addr_bytes = bytes([(addr >> 0) & 0xFF, (addr >> 8) & 0xFF, 
                        (addr >> 16) & 0xFF, (addr >> 24) & 0xFF])
    crc = addr_bytes[0] ^ addr_bytes[1] ^ addr_bytes[2] ^ addr_bytes[3]
    addr_cmd = addr_bytes + bytes([crc])
    print(f"  发送: {addr_cmd.hex()}")
    ser.write(addr_cmd)
    time.sleep(0.3)
    response = ser.read(1)
    
    if not response:
        print(f"  无响应")
        return False
    elif response[0] == ACK:
        print(f"  ACK - 地址有效!")
        # 读取数据
        ser.write(bytes([0, 0xFF]))  # 1字节
        time.sleep(0.3)
        response = ser.read(1)
        print(f"  长度 ACK: {response.hex() if response else '超时'}")
        data = ser.read(1)
        print(f"  数据: {data.hex() if data else '无'}")
        return True
    else:
        print(f"  NACK - 地址无效")
        return False

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
    
    # Get 命令
    print("\n发送 Get 命令...")
    ser.write(b"\x00\xFF")
    time.sleep(0.5)
    response = ser.read(20)
    print(f"收到: {response.hex()}")
    
    # Extended Erase
    print("\n发送 Extended Erase...")
    ser.write(b"\x44\xBB")
    time.sleep(0.3)
    response = ser.read(1)
    if response and response[0] == ACK:
        ser.write(b"\xFF\xFF\x00")
        print("等待擦除完成...")
        time.sleep(30)
        response = ser.read(1)
        print(f"擦除响应: {response.hex() if response else '超时'}")
    
    time.sleep(2)
    ser.reset_input_buffer()
    
    # 测试不同地址
    test_address(ser, 0x08000000, "Flash start")
    time.sleep(1)
    ser.reset_input_buffer()
    
    test_address(ser, 0x08001000, "Flash +0x1000")
    time.sleep(1)
    ser.reset_input_buffer()
    
    test_address(ser, 0x1FFF0000, "System memory")
    time.sleep(1)
    ser.reset_input_buffer()
    
    test_address(ser, 0x20000000, "SRAM")
    time.sleep(1)
    ser.reset_input_buffer()
    
    test_address(ser, 0x00000000, "Start")
    
    ser.close()
    print("\n完成!")

if __name__ == "__main__":
    main()
