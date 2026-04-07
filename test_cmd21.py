#!/usr/bin/env python3
"""测试命令 0x21"""

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
    
    # Sync + Get
    print("\n1. Sync + Get...")
    ser.write(b"\x00\xFF")
    time.sleep(0.5)
    response = ser.read(20)
    print(f"   收到: {response.hex()}")
    
    # Extended Erase
    print("\n2. Extended Erase...")
    ser.write(b"\x44\xBB")
    time.sleep(0.3)
    response = ser.read(1)
    if response and response[0] == ACK:
        ser.write(b"\xFF\xFF\x00")
        print("   等待擦除完成...")
        time.sleep(30)
        response = ser.read(1)
        print(f"   擦除响应: {response.hex() if response else '超时'}")
    
    time.sleep(2)
    
    # Re-sync
    print("\n3. Re-sync...")
    ser.reset_input_buffer()
    ser.write(b"\x00\xFF")
    time.sleep(0.5)
    response = ser.read(20)
    print(f"   收到: {response.hex()}")
    
    # 测试命令 0x21
    print("\n4. 尝试命令 0x21 (checksum 0xDE)...")
    ser.write(b"\x21\xDE")
    time.sleep(0.5)
    response = ser.read(1)
    print(f"   响应: {response.hex() if response else '超时'}")
    
    if response and response[0] == ACK:
        # 发送地址
        addr = 0x08000000
        addr_bytes = bytes([(addr >> 0) & 0xFF, (addr >> 8) & 0xFF, 
                            (addr >> 16) & 0xFF, (addr >> 24) & 0xFF])
        crc = addr_bytes[0] ^ addr_bytes[1] ^ addr_bytes[2] ^ addr_bytes[3]
        addr_cmd = addr_bytes + bytes([crc])
        print(f"\n5. 发送地址: {addr_cmd.hex()}")
        ser.write(addr_cmd)
        time.sleep(0.5)
        response = ser.read(1)
        print(f"   地址响应: {response.hex() if response else '超时'}")
        
        if response and response[0] == ACK:
            print("   成功!")
            # 发送长度
            ser.write(bytes([0, 0xFF]))  # 1字节
            time.sleep(0.5)
            response = ser.read(1)
            print(f"   长度响应: {response.hex() if response else '超时'}")
            if response and response[0] == ACK:
                data = ser.read(1)
                print(f"   数据: {data.hex() if data else '无'}")
    
    ser.close()
    print("\n完成!")

if __name__ == "__main__":
    main()
