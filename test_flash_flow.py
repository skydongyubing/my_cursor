#!/usr/bin/env python3
"""测试烧录流程"""

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
    
    # Step 1: Read 0x11
    print("\n1. 发送 0x11...")
    ser.write(b"\x11")
    time.sleep(1.0)
    ser.write(b"\xEE")
    response = ser.read(1)
    print(f"   收到: {response.hex() if response else '超时'}")
    
    # Step 2: 地址 0x08
    print("\n2. 发送地址 0x08 0x00 0x00 0x00 0x08...")
    ser.write(b"\x08\x00\x00\x00\x08")
    response = ser.read(1)
    print(f"   收到: {response.hex() if response else '超时'}")
    
    # Step 3: Get 0x00 0xFF
    print("\n3. 发送 0x00 0xFF...")
    ser.write(b"\x00\xFF")
    response = ser.read(10)
    print(f"   收到: {response.hex() if response else '超时'}")
    
    # Step 4: Erase 0x44
    print("\n4. 发送 0x44...")
    ser.write(b"\x44")
    time.sleep(0.00019)
    ser.write(b"\xBB")
    response = ser.read(1)
    print(f"   收到: {response.hex() if response else '超时'}")
    
    # Step 5: Erase 参数
    print("\n5. 发送擦除参数...")
    ser.write(b"\x00\x03\x00\x00\x00\x01\x00\x02\x00\x03\x03")
    time.sleep(0.7)
    response = ser.read(1)
    print(f"   收到: {response.hex() if response else '超时'}")
    
    ser.close()
    print("\n完成!")

if __name__ == "__main__":
    main()
