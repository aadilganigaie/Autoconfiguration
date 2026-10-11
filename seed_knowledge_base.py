#!/usr/bin/env python3
"""
Seed the CLARITY knowledge base with synthetic device manual text.

This bypasses PDF parsing and directly injects text chunks into Qdrant,
allowing the benchmark to run without real PDF manuals on disk.
"""
import logging
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from clarity.config import DEFAULT_CONFIG
from clarity.ingestion.chunker import Chunk
from clarity.retrieval.embedder import Embedder
from clarity.retrieval.vector_store import VectorStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Synthetic manual content keyed by (device_name, protocol)
# ---------------------------------------------------------------------------

_MANUALS = {
    ("Temperature Sensor TH200", "modbus"): [
        """\
TEMPERATURE SENSOR TH200 — MODBUS RTU INTERFACE MANUAL

1. OVERVIEW
The TH200 is a Pt100 resistance temperature detector (RTD) transmitter with
a Modbus RTU serial interface. It converts the Pt100 resistance reading into
a digital value accessible over RS-485.

2. MODBUS CONFIGURATION
Default settings:
  Device ID (slave address): 1
  Baud rate: 19200 bps
  Data bits: 8
  Parity: None (N)
  Stop bits: 1 (8N1 format)
  Function code: 03 (Read Holding Registers)

3. REGISTER MAP
  Holding Register 1: Temperature value, INT16, units = 0.1°C
    Range: -500 to +8500 (represents -50.0°C to +850.0°C)
    Example: register value 235 → 23.5°C

  Holding Register 2: Status flags, UINT16
    Bit 0: Sensor open-circuit fault
    Bit 1: Sensor short-circuit fault
    Bit 2: Over-range
    Bit 3: Under-range

4. READ EXAMPLE
Request (hex): 01 03 00 01 00 01 D5 CA
  Slave=0x01, FC=0x03, Start register=0x0001, Count=0x0001
Response: 01 03 02 00 EB B8 FA
  Data: 0x00EB = 235 decimal → 23.5°C

5. ELECTRICAL CONNECTIONS
  Terminal A+: RS-485 positive
  Terminal B-: RS-485 negative
  Terminal SH: Shield / GND
  Supply: 10–30 V DC, 50 mA max

6. SAFETY NOTES
Maximum ambient temperature: 85°C.
Do not exceed register address 0x002F (47 decimal).
Polling interval: minimum 100 ms to avoid bus contention.
""",
        """\
TH200 ADVANCED PARAMETER TABLE

Parameter Name         : Register Address : Data Type : Unit   : R/W
Temperature            : 1                : INT16     : 0.1°C  : R
Status Flags           : 2                : UINT16    : -      : R
Device Address         : 100              : UINT16    : -      : R/W
Baud Rate Code         : 101              : UINT16    : -      : R/W
  Baud Code Values: 3=9600, 4=19200, 5=38400
Temperature Offset     : 102              : INT16     : 0.01°C : R/W
Temperature Scale      : 103              : UINT16    : -      : R/W
  Scale Values: 0=Celsius, 1=Fahrenheit

TH200 COMMUNICATION TIMING
  Response delay: ≤ 5 ms after last stop bit
  Bus turnaround delay: ≥ 3.5 character times
  Broadcast address: 0 (no response sent)

FIRMWARE VERSION REGISTER
  Register 200: Firmware major version (UINT16)
  Register 201: Firmware minor version (UINT16)
""",
    ],

    ("Pressure Sensor PS500", "opcua"): [
        """\
PRESSURE SENSOR PS500 — OPC-UA SERVER MANUAL

1. PRODUCT DESCRIPTION
The PS500 is a 4-20 mA pressure transducer with an integrated OPC-UA server
(IEC 62541). It measures gauge pressure from 0 to 10 bar with 0.1% FS accuracy.

2. OPC-UA CONNECTION
  Endpoint URL: opc.tcp://<device-ip>:4840
  Security: None (open, for commissioning) or Basic256Sha256 for production
  Namespace 0: OPC-UA standard types
  Namespace 2 (ns=2): PS500 device objects

3. NODE DIRECTORY
  Node ns=2;i=1001
    BrowseName: PressureValue
    DisplayName: Pressure (bar)
    DataType: Float
    AccessLevel: ReadOnly
    Description: Current gauge pressure in bar units. Valid range 0.0–10.5.

  Node ns=2;i=1002
    BrowseName: StatusCode
    DisplayName: Device Status
    DataType: UInt16
    AccessLevel: ReadOnly
    Description: 0=OK, 1=Overrange, 2=Underrange, 4=SensorFault

  Node ns=2;i=1003
    BrowseName: ZeroAdjust
    DisplayName: Zero Calibration Offset
    DataType: Float
    AccessLevel: ReadWrite
    Description: Calibration offset applied to pressure reading (bar).

  Node ns=2;i=1004
    BrowseName: SampleRate
    DisplayName: OPC-UA Publish Rate
    DataType: UInt32
    AccessLevel: ReadWrite
    Description: Publishing interval in milliseconds. Default: 100 ms.

4. SUBSCRIPTION EXAMPLE
  CreateSubscription: PublishingInterval=100ms, LifetimeCount=30
  CreateMonitoredItem: NodeId=ns=2;i=1001, SamplingInterval=100ms
  PublishResponse: Value.Value=Float, Value.SourceTimestamp=UTC

5. CERTIFICATES
  Server certificate: /opt/ps500/certs/server_cert.der
  Trusted clients folder: /opt/ps500/certs/trusted/
""",
        """\
PS500 TECHNICAL SPECIFICATIONS

Measurement range      : 0 to 10 bar gauge
Overrange              : 10.5 bar (1.5× rated pressure burst)
Accuracy               : ±0.1% FS at 25°C
Temperature drift      : ±0.05% FS / 10°C
Supply voltage         : 24 V DC ±10%
Output signal          : 4–20 mA (HART optional), OPC-UA over Ethernet

OPC-UA SERVER DETAILS
  OPC-UA version       : 1.04
  Transport            : TCP binary (uatcp-uasc-uabinary)
  Max sessions         : 5
  NodeId ns=2;i=1001  : PressureValue  (Float, ReadOnly)
  NodeId ns=2;i=1002  : StatusCode     (UInt16, ReadOnly)
  NodeId ns=2;i=1003  : ZeroAdjust     (Float, ReadWrite)
  NodeId ns=2;i=1004  : SampleRate     (UInt32, ReadWrite)

NETWORK CONFIGURATION
  Default IP           : 192.168.1.100
  Subnet mask          : 255.255.255.0
  Port                 : 4840
  DHCP                 : Enabled by default

ALARM LIMITS (WritableNodes)
  NodeId ns=2;i=2001  : HighHighLimit  (Float, default 9.5 bar)
  NodeId ns=2;i=2002  : HighLimit      (Float, default 8.0 bar)
  NodeId ns=2;i=2003  : LowLimit       (Float, default 0.5 bar)
""",
    ],

    ("Motor Drive VFD300", "profibus"): [
        """\
MOTOR DRIVE VFD300 — PROFIBUS DP INTERFACE MANUAL

1. PRODUCT OVERVIEW
The VFD300 is a Siemens SINAMICS G120 variable frequency drive (VFD) with
an integrated Profibus DP communications board (CB 15F). It supports
cyclic and acyclic data exchange per IEC 61158.

2. PROFIBUS CONFIGURATION
  Station address (slave address): 5
  Baud rate: 1.5 Mbit/s (auto-detected)
  Vendor name: Siemens
  Model: SINAMICS G120
  GSD file: SIEM8004.GSD (compatible with G120 firmware V4.7+)

3. CYCLIC DATA (PPO Type 3 — 6 words)
  PZD1 Control Word (Master → Slave, UINT16)
    Bit 0: ON/OFF1  — 1 = Run command
    Bit 1: OFF2     — 0 = Coast stop
    Bit 2: OFF3     — 0 = Ramp stop
    Bit 3: Enable   — 1 = Enable operation
    Bit 10: Setpoint enable
  PZD2 Speed Setpoint (Master → Slave, INT16)
    Range: -16384 to +16384 → corresponds to -100% to +100% of max frequency
  PZD3 Status Word (Slave → Master, UINT16)
    Bit 0: Ready to switch on
    Bit 1: Ready
    Bit 2: Operation enabled
    Bit 10: Setpoint reached
  PZD4 Actual Speed (Slave → Master, INT16, same scaling as setpoint)

4. ACYCLIC DATA (DP-V1)
  Slot 0, Index 1: Drive operating hours (UINT32, hours)
  Slot 0, Index 2: DC link voltage (UINT16, 0.1 V)
  Slot 0, Index 3: Output current (UINT16, 0.1 A)
  Slot 0, Index 4: Motor temperature (INT16, 0.1°C)

5. STATION ADDRESS SETTING
  DIP switch on CB 15F front panel sets the station address.
  Address 5 = DIP switches: OFF ON OFF ON OFF (bits 4–0).
  Valid range: 1–125. Address 126 = factory reset.

6. FAULT CODES
  F001: Overcurrent
  F002: Overvoltage DC link
  F011: Motor overtemperature
  F052: Profibus communication timeout (watchdog = 100 ms)
""",
        """\
VFD300 PARAMETER REFERENCE (Profibus-relevant)

P0918 : Profibus station address    : Default 5     : Writable at standstill
P0922 : PKW word length             : Default 4     : R
P0927 : Parameter modification      : Default 15    : R/W (bitmask)
P2030 : Profibus baud rate setting  : Default 0 (auto-detect 1.5 Mbit/s)
P2040 : Drive response monitoring   : Default 100 ms (watchdog)
P2044 : Profibus telegram selection : Default 1 (Standard telegram 1)

SAFETY INTERLOCK
  Hardware enable input DI0 must be active (24 V) before drive will run.
  Emergency stop (STO) via terminals X13:1/X13:2.

COMMISSIONING SEQUENCE
  1. Set P0918 = 5 (station address).
  2. Connect Profibus cable (9-pin D-Sub, pins 3=B, 8=A, 5=GND).
  3. Terminate bus at first and last station (SW1 = ON).
  4. Power cycle the drive.
  5. In PLC, configure DP slave with GSD file SIEM8004.GSD.
  6. Map PZD1 (control word) and PZD2 (setpoint) in PLC output.
  7. Verify P2040 watchdog does not trip during polling.
""",
    ],

    ("CANopen Encoder ENC100", "fieldbus"): [
        """\
CANOPEN INCREMENTAL ENCODER ENC100 — FIELDBUS MANUAL

1. DEVICE DESCRIPTION
The ENC100 is an optical incremental encoder with a CANopen interface
conforming to CiA DS301 (application layer) and DS406 (encoder profile).

2. CANOPEN NETWORK CONFIGURATION
  Node ID: 10 (decimal), set via DIP switch or LSS service
  Vendor ID: 0x00000123
  Product code: 0x00000456
  Revision number: 0x00010001
  Serial number: device-unique (read from object 0x1018 sub-index 4)
  Bit rate: 250 kbit/s default (configurable: 125, 250, 500, 1000 kbit/s)

3. OBJECT DICTIONARY (key objects)
  Object 0x1000: Device type (UINT32) = 0x00060196 (encoder profile)
  Object 0x1001: Error register (UINT8) — R
  Object 0x1017: Producer heartbeat time (UINT16), default 100 ms
  Object 0x1018: Identity object
    Sub 1 (Vendor ID): 0x00000123
    Sub 2 (Product code): 0x00000456
    Sub 3 (Revision number): 0x00010001
    Sub 4 (Serial number): device-specific
  Object 0x6004: Position value (INT32), unit: pulses — R, mapped to TPDO1
  Object 0x6005: Linear position value (INT32), unit: mm×10 — R
  Object 0x6503: Number of distinguishable steps per revolution (UINT32)
    Default: 4096
  Object 0x6504: Number of revolutions (UINT32)
    Default: 1 (single-turn encoder)

4. PDO CONFIGURATION
  TPDO1 (transmit PDO 1):
    COB-ID: 0x180 + NodeID = 0x18A (node 10)
    Transmission type: 1 (synchronous, every SYNC)
    Mapped: Object 0x6004 (position, INT32) — 4 bytes

5. NMT STATE MACHINE
  Power-on → Initialisation → Pre-Operational
  Start_Remote_Node (command 0x01) → Operational
  In Operational state, TPDO1 broadcasts position at each SYNC.

6. LSS (Layer Setting Services)
  Used to set node ID and bit rate when DIP switches are unavailable.
  LSS master sends "Switch mode global" (0x04 04) to enter LSS mode.
""",
        """\
ENC100 WIRING AND ELECTRICAL DATA

Supply voltage         : 10–30 V DC
Current consumption    : 90 mA typical at 24 V
CAN interface          : ISO 11898-2 (high-speed CAN)
  CAN_H terminal       : Pin 7 (9-pin D-Sub CiA303-1)
  CAN_L terminal       : Pin 2
  GND                  : Pin 3

RESOLUTION AND ACCURACY
  Pulses/revolution    : 4096 (12-bit single-turn)
  Accuracy             : ±0.1° mechanical
  Max shaft speed      : 6000 RPM
  Output signal        : CANopen TPDO1, position INT32 in pulses

NODE ID DIP SWITCH ASSIGNMENT
  Switches S1–S7 (binary, S1 = LSB):
    Node ID 10 = 0001010 → S2=ON, S4=ON, rest OFF

BUS TERMINATION
  Install 120 Ω termination resistor at both cable ends.
  Internal terminator: jumper JP1 = closed (factory default for standalone use).
  For network use: open JP1, use external 120 Ω at each bus end.

DIAGNOSTIC LEDS
  Green (RUN): blinking = Pre-Operational, solid = Operational
  Red (ERR): off = no error, single flash = warning, solid = bus-off
""",
    ],

    # XYZ legacy device intentionally has NO seed data so rerank scores stay
    # below the abstention threshold — triggering the correct abstention path.
}


def make_chunk(text: str, source: str, page: int, section: str, idx: int) -> Chunk:
    stem = source.replace(" ", "_").replace("/", "_")
    return Chunk(
        chunk_id=f"{stem}_p{page}_{idx}_{uuid.uuid4().hex[:6]}",
        text=text.strip(),
        source_path=f"synthetic://{source}",
        page_num=page,
        section_title=section,
        chunk_type="text",
        token_count=max(1, len(text) // 4),
    )


def main():
    config = DEFAULT_CONFIG
    embedder = Embedder(config.embedding_model)
    vector_store = VectorStore(config)

    total = 0
    for (device, protocol), pages in _MANUALS.items():
        logger.info(f"Seeding: {device} ({protocol})")
        chunks = []
        for i, text in enumerate(pages):
            chunks.append(make_chunk(text, f"{device}_{protocol}", i + 1, "Manual", i))

        texts = [c.text for c in chunks]
        embeddings = embedder.embed_texts(texts)
        vector_store.upsert_chunks(chunks, embeddings)
        total += len(chunks)
        logger.info(f"  -> {len(chunks)} chunks inserted.")

    logger.info(f"Seeding complete. Total chunks: {total}")


if __name__ == "__main__":
    main()
