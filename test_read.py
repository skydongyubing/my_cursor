#!/usr/bin/env python3
"""测试 Read Memory 命令"""

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
    print("\n1. 发送 Get 命令...")
    ser.write(b"\x00\xFF")
    time.sleep(0.5)
    response = ser.read(20)
    print(f"   收到: {response.hex()}")
    
    # Step 2: Extended Erase
    print("\n2. 发送 Extended Erase 命令 0x44 0xBB...")
    ser.write(b"\x44\xBB")
    time.sleep(0.5)
    response = ser.read(1)
    print(f"   收到: {response.hex() if response else '超时'}")
    if response and response[0] == ACK:
        print("   ACK - 发送擦除参数 0xFF 0xFF 0x00")
        ser.write(b"\xFF\xFF\x00")
        print("   等待擦除完成 (30秒)...")
        time.sleep(30)
        response = ser.read(1)
        print(f"   擦除响应: {response.hex() if response else '超时'}")
    
    ser.reset_input_buffer()
    time.sleep(2)
    
    # Step 3: 尝试读取
    print("\n3. 发送 Read 命令 0x11 0xEE...")
    ser.write(b"\x11\xEE")
    time.sleep(0.5)
    response = ser.read(1)
    print(f"   收到: {response.hex() if response else '超时'}")
    
    if not response or response[0] != ACK:
        print("   Read 命令被拒绝!")
        ser.close()
        return
    
    # 发送地址 0x08000000
    addr = 0x08000000
    addr_bytes = bytes([(addr >> 0) & 0xFF, (addr >> 8) & 0xFF, 
                        (addr >> 16) & 0xFF, (addr >> 24) & 0xFF])
    crc = addr_bytes[0] ^ addr_bytes[1] ^ addr_bytes[2] ^ addr_bytes[3]
    addr_cmd = addr_bytes + bytes([crc])
    print(f"\n4. 发送地址 0x{addr:08X}: {addr_cmd.hex()}")
    ser.write(addr_cmd)
    time.sleep(0.5)
    response = ser.read(1)
    print(f"   收到: {response.hex() if response else '超时'}")
    
    if not response or response[0] != ACK:
        print("   地址被拒绝!")
        ser.close()
        return
    
    # 发送读取长度 (8字节)
    n = 7  # N-1 = 8-1 = 7
    ser.write(bytes([n, n ^ 0xFF]))
    time.sleep(0.5)
    response = ser.read(1)
    print(f"   收到: {response.hex() if response else '超时'}")
    
    if not response or response[0] != ACK:
        print("   长度被拒绝!")
        ser.close()
        return
    
    # 读取数据
    data = ser.read(8)
    print(f"\n5. 读取的数据: {data.hex()}")
    
    ser.close()
    print("\n完成!")

if __name__ == "__main__":
    main()
