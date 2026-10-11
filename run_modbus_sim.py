#!/usr/bin/env python3
"""Minimal Modbus TCP simulator for CLARITY deployment verification.

Serves 65536 holding registers on localhost:5020 (pymodbus >= 3.9 API).
"""
import asyncio
import logging

from pymodbus.datastore import (
    ModbusDeviceContext,
    ModbusSequentialDataBlock,
    ModbusServerContext,
)
from pymodbus.server import StartAsyncTcpServer

logging.basicConfig(level=logging.INFO)


async def main():
    block = ModbusSequentialDataBlock(1, [0] * 65535)
    device = ModbusDeviceContext(di=block, co=block, hr=block, ir=block)
    context = ModbusServerContext(devices=device, single=True)
    logging.info("CLARITY Modbus simulator on 0.0.0.0:5020")
    await StartAsyncTcpServer(context=context, address=("0.0.0.0", 5020))


if __name__ == "__main__":
    asyncio.run(main())
