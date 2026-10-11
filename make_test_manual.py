"""Generate a realistic device manual PDF for CLARITY pipeline testing."""
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT

OUT = "test_device_manual_TH200.pdf"

doc = SimpleDocTemplate(
    OUT,
    pagesize=A4,
    leftMargin=2.5*cm, rightMargin=2.5*cm,
    topMargin=2.5*cm, bottomMargin=2.5*cm,
)

styles = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=18, spaceAfter=10, textColor=colors.HexColor("#1a3a5c"))
H2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=13, spaceAfter=6, textColor=colors.HexColor("#1a3a5c"))
H3 = ParagraphStyle("H3", parent=styles["Heading3"], fontSize=11, spaceAfter=4, textColor=colors.HexColor("#2e6da4"))
BODY = ParagraphStyle("BODY", parent=styles["BodyText"], fontSize=10, leading=14, spaceAfter=6)
BOLD = ParagraphStyle("BOLD", parent=BODY, fontName="Helvetica-Bold")
CENTRE = ParagraphStyle("CENTRE", parent=BODY, alignment=TA_CENTER, fontSize=12)
SMALL = ParagraphStyle("SMALL", parent=BODY, fontSize=8, textColor=colors.grey)

def T(text, style=BODY): return Paragraph(text, style)
def SP(h=0.3): return Spacer(1, h*cm)
def HR(): return HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc"), spaceAfter=6)

def tbl(data, col_widths=None, header=True):
    t = Table(data, colWidths=col_widths, repeatRows=1 if header else 0)
    cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a3a5c")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f4f8")]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
    ]
    if not header:
        cmds = cmds[3:]
    t.setStyle(TableStyle(cmds))
    return t

story = []

# ── Cover Page ────────────────────────────────────────────────────────────────
story += [
    SP(3),
    T("THERMTEC INDUSTRIAL INSTRUMENTS", ParagraphStyle("cover_brand", parent=CENTRE, fontSize=10, textColor=colors.HexColor("#2e6da4"), fontName="Helvetica-Bold")),
    SP(0.5),
    T("TH200 Smart Temperature Transmitter", ParagraphStyle("cover_h", parent=CENTRE, fontSize=22, textColor=colors.HexColor("#1a3a5c"), fontName="Helvetica-Bold")),
    SP(0.3),
    T("4–20 mA / Modbus RTU / HART", ParagraphStyle("cover_sub", parent=CENTRE, fontSize=14, textColor=colors.HexColor("#2e6da4"))),
    SP(0.6),
    HR(),
    SP(0.4),
    T("Installation, Configuration &amp; Communication Manual", ParagraphStyle("cover_doc", parent=CENTRE, fontSize=12)),
    SP(0.2),
    T("Document No. TH200-MAN-003 &nbsp;|&nbsp; Revision 4.1 &nbsp;|&nbsp; June 2026", SMALL),
    SP(4),
    T("⚠  READ THIS MANUAL BEFORE INSTALLATION. Failure to follow these instructions may result in equipment damage, process upset, or personal injury.", ParagraphStyle("warn", parent=BODY, textColor=colors.HexColor("#c0392b"), fontName="Helvetica-Bold", borderPad=4)),
    PageBreak(),
]

# ── 1. Product Overview ───────────────────────────────────────────────────────
story += [
    T("1. Product Overview", H1), HR(),
    T("The TH200 is a two-wire, loop-powered smart temperature transmitter designed for demanding industrial process control applications. It accepts inputs from Type J, K, T, E, R, S, B thermocouples and 100 Ω / 1000 Ω Pt RTDs. The 4–20 mA analogue output is supplemented by a full Modbus RTU serial interface on the integrated RS-485 port, enabling digital configuration and continuous register-mapped readback without breaking the analogue loop.", BODY),
    SP(),
    T("Key features:", BOLD),
]
feats = [
    ["Feature", "Specification"],
    ["Measurement input", "TC: J, K, T, E, R, S, B &nbsp;| RTD: Pt100 / Pt1000 (2/3/4-wire)"],
    ["Analogue output",   "4–20 mA, max load 600 Ω at 24 V DC"],
    ["HART revision",     "HART 7 (optional factory option)"],
    ["Digital interface", "Modbus RTU over RS-485 (2-wire, half-duplex)"],
    ["Slave address range","1–247 (factory default: 1)"],
    ["Baud rates supported","1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200"],
    ["Default baud rate", "9600 bps"],
    ["Data format",       "8 data bits, No parity, 1 stop bit (8N1)"],
    ["Process temperature", "−40 °C to +120 °C (sensor dependent)"],
    ["Ambient temperature", "−40 °C to +85 °C"],
    ["Supply voltage",    "12–36 V DC (two-wire loop)"],
    ["Protection class",  "IP66 / NEMA 4X"],
    ["Certifications",    "ATEX Zone 1/2, IECEx, SIL 2 (IEC 61508)"],
    ["Housing material",  "316L stainless steel"],
    ["Process connection","1/2\" NPT or G1/2 thread"],
]
story += [tbl(feats, col_widths=[6*cm, 10*cm]), SP()]

story += [
    T("Ordering code: TH200 – [Input] – [Output] – [Housing] – [Options]", SMALL),
    SP(0.5), PageBreak(),
]

# ── 2. Safety ─────────────────────────────────────────────────────────────────
story += [
    T("2. Safety Instructions", H1), HR(),
    T("2.1 General", H2),
    T("Installations must comply with local regulations, IEC 60079 (hazardous areas), and applicable electrical codes. Only qualified personnel with knowledge of process instrumentation and relevant safety standards should install, operate, or maintain this equipment.", BODY),
    T("2.2 Electrical Safety", H2),
    T("Maximum loop supply: 36 V DC. Do not exceed this value. The device contains no user-serviceable parts. Return to factory or authorised service centre for repair.", BODY),
    T("2.3 Process Safety Constraints", H2),
    T("The following safety limits are enforced by the device firmware and MUST be respected in any configuration:", BODY),
]
safety = [
    ["Parameter", "Minimum", "Maximum", "Consequence if violated"],
    ["Loop current",       "3.6 mA",   "21.0 mA",  "Open/short circuit detection"],
    ["Process temperature","−40 °C",   "+120 °C",   "Overrange error (22 mA burnout)"],
    ["Supply voltage",     "12 V DC",  "36 V DC",   "Under/overvoltage protection"],
    ["Slave address",      "1",        "247",        "Address 0 is broadcast only"],
    ["Baud rate",          "1200 bps", "115200 bps","Communication fault"],
]
story += [tbl(safety, col_widths=[4.5*cm, 2.5*cm, 2.5*cm, 6.5*cm]), SP(0.5), PageBreak()]

# ── 3. Wiring ─────────────────────────────────────────────────────────────────
story += [
    T("3. Wiring and Installation", H1), HR(),
    T("3.1 Terminal Identification", H2),
]
terminals = [
    ["Terminal", "Label", "Description"],
    ["1", "+",   "Loop supply positive (4–20 mA, +V)"],
    ["2", "−",   "Loop supply negative / signal return"],
    ["3", "A",   "RS-485 A (non-inverting, +)"],
    ["4", "B",   "RS-485 B (inverting, −)"],
    ["5", "⏚",   "Functional earth (shield)"],
    ["6/7", "SEN+/SEN−", "RTD or thermocouple sensor input"],
    ["8", "SEN_REF", "RTD third wire (3-wire RTD only)"],
]
story += [tbl(terminals, col_widths=[2*cm, 2.5*cm, 11.5*cm]), SP()]
story += [
    T("3.2 RS-485 Network Wiring", H2),
    T("Use shielded twisted-pair cable (e.g. Belden 9841 or equivalent, 120 Ω characteristic impedance). Terminate the bus at both physical ends with 120 Ω resistors. Maximum bus length: 1200 m at 9600 bps. Each TH200 presents a unit load of 1/8 on the RS-485 bus, allowing up to 256 devices with standard transceivers.", BODY),
    SP(0.5), PageBreak(),
]

# ── 4. Modbus RTU Register Map ─────────────────────────────────────────────────
story += [
    T("4. Modbus RTU Communication", H1), HR(),
    T("4.1 Protocol Parameters", H2),
]
proto_params = [
    ["Parameter", "Default", "Configurable via"],
    ["Slave address",   "1",      "Local keypad or Modbus FC06 (register 40201)"],
    ["Baud rate",       "9600",   "Local keypad or Modbus FC06 (register 40202)"],
    ["Parity",          "None",   "Local keypad or Modbus FC06 (register 40203)"],
    ["Stop bits",       "1",      "Fixed"],
    ["Byte order",      "Big-endian (MSB first)", "Fixed"],
    ["Turnaround delay","≥ 5 ms", "Fixed"],
    ["Broadcast support","Yes (address 0, write-only)","—"],
]
story += [tbl(proto_params, col_widths=[4.5*cm, 3.5*cm, 8*cm]), SP()]

story += [T("4.2 Supported Function Codes", H2)]
fcs = [
    ["Code", "Name",               "Used for"],
    ["FC01", "Read Coils",         "Read status bits (alarm, diagnostics)"],
    ["FC03", "Read Holding Registers","Read process values and configuration"],
    ["FC04", "Read Input Registers","Read live measurement registers (read-only)"],
    ["FC06", "Write Single Register","Write a single configuration register"],
    ["FC16", "Write Multiple Registers","Write a block of configuration registers"],
]
story += [tbl(fcs, col_widths=[2*cm, 5*cm, 9*cm]), SP()]

story += [T("4.3 Register Map", H2)]
regs = [
    ["Register (40xxx)", "Address (hex)", "R/W", "Data type",   "Description",                          "Units / Notes"],
    ["40001", "0000", "R",  "INT16 × 10",  "Primary process value (temperature)",    "°C × 10, e.g. 256 = 25.6 °C"],
    ["40002", "0001", "R",  "INT16 × 10",  "Sensor 2 / ambient temperature",         "°C × 10"],
    ["40003", "0002", "R",  "UINT16",      "Device status word",                      "See Table 4-4"],
    ["40004", "0003", "R",  "UINT16",      "Loop current (mA × 100)",                "e.g. 1200 = 12.00 mA"],
    ["40010", "0009", "R",  "UINT32 BE",   "Primary value as IEEE 754 float (high)", "Registers 40010–40011"],
    ["40011", "000A", "R",  "UINT32 BE",   "Primary value as IEEE 754 float (low)",  "Combined with 40010"],
    ["40101", "0064", "R",  "UINT16",      "Firmware version (BCD)",                 "e.g. 0x0401 = v4.1"],
    ["40102", "0065", "R",  "UINT16",      "Hardware revision",                      "e.g. 0x0200 = rev 2.0"],
    ["40103", "0066", "R",  "UINT32 BE",   "Serial number (high word)",              "Registers 40103–40104"],
    ["40104", "0067", "R",  "UINT32 BE",   "Serial number (low word)",               "Combined with 40103"],
    ["40201", "00C8", "R/W","UINT16",      "Modbus slave address",                   "Range 1–247, default 1"],
    ["40202", "00C9", "R/W","UINT16",      "Baud rate code",                         "0=1200,1=2400,2=4800,3=9600,4=19200,5=38400,6=57600,7=115200"],
    ["40203", "00CA", "R/W","UINT16",      "Parity / stop bits",                     "0=8N1, 1=8E1, 2=8O1"],
    ["40210", "00D1", "R/W","INT16 × 10",  "Range low (4 mA setpoint)",             "°C × 10, default −400 (−40.0 °C)"],
    ["40211", "00D2", "R/W","INT16 × 10",  "Range high (20 mA setpoint)",           "°C × 10, default 1200 (+120.0 °C)"],
    ["40212", "00D3", "R/W","UINT16",      "Burnout direction",                      "0=upscale (21.0 mA), 1=downscale (3.6 mA)"],
    ["40213", "00D4", "R/W","UINT16",      "Damping time constant",                  "Seconds × 10, range 0–600"],
    ["40220", "00DB", "R/W","UINT16",      "Sensor type",                            "0=K-TC,1=J-TC,2=T-TC,3=E-TC,4=Pt100,5=Pt1000"],
    ["40221", "00DC", "R/W","UINT16",      "RTD wiring mode",                        "2=2-wire,3=3-wire,4=4-wire"],
    ["40230", "00E5", "R/W","INT16 × 100", "User calibration offset",               "°C × 100, default 0"],
    ["40231", "00E6", "R/W","INT16 × 1000","User calibration gain",                 "× 1000, default 1000"],
    ["40240", "00EF", "R/W","UINT16",      "High temperature alarm setpoint",        "°C × 10"],
    ["40241", "00F0", "R/W","UINT16",      "Low temperature alarm setpoint",         "°C × 10"],
    ["40242", "00F1", "R/W","UINT16",      "Alarm hysteresis",                       "°C × 10, default 20 (2.0 °C)"],
    ["40300", "012B", "R/W","UINT16",      "Factory reset",                          "Write 0xA5A5 to restore defaults"],
]
story += [tbl(regs, col_widths=[2.2*cm, 2.2*cm, 1.2*cm, 2.5*cm, 5.5*cm, 4.4*cm]), SP(0.5)]

story += [
    T("4.4 Status Word Bit Map (Register 40003)", H2),
]
status_bits = [
    ["Bit", "Name",               "Description"],
    ["0",   "PV_VALID",           "1 = process value is valid"],
    ["1",   "SENSOR_FAULT",       "1 = sensor open/short circuit detected"],
    ["2",   "OVERRANGE",          "1 = input above high range limit"],
    ["3",   "UNDERRANGE",         "1 = input below low range limit"],
    ["4",   "HIGH_ALARM",         "1 = high temperature alarm active"],
    ["5",   "LOW_ALARM",          "1 = low temperature alarm active"],
    ["6",   "LOOP_FAULT",         "1 = loop current < 3.5 mA or > 21.5 mA"],
    ["7",   "NV_WRITE_ERROR",     "1 = non-volatile memory write failure"],
    ["8",   "CAL_ACTIVE",         "1 = calibration mode active"],
    ["9–15","RESERVED",           "Always 0"],
]
story += [tbl(status_bits, col_widths=[1.5*cm, 4*cm, 10.5*cm]), SP(0.5), PageBreak()]

# ── 5. Configuration ──────────────────────────────────────────────────────────
story += [
    T("5. Device Configuration", H1), HR(),
    T("5.1 Setting Slave Address via Modbus", H2),
    T("To change the slave address, write the new address (1–247) to register 40201 using FC06. The change takes effect immediately and is stored in non-volatile memory. Broadcast address 0 cannot be set as the slave address.", BODY),
    SP(0.2),
    T("Example FC06 PDU (set slave address to 3):", BOLD),
    T("TX: 01 06 00 C8 00 03 [CRC]   →   RX: 01 06 00 C8 00 03 [CRC]", ParagraphStyle("code", parent=BODY, fontName="Courier", fontSize=9, backColor=colors.HexColor("#f4f4f4"), borderPad=4)),
    SP(0.3),
    T("5.2 Setting Baud Rate", H2),
    T("Write a baud rate code (0–7) to register 40202. The device will apply the new baud rate after a 500 ms delay. Ensure the host adapts immediately. Both ends must match.", BODY),
    SP(0.2),
    T("Example: set 19200 bps (code 4):", BOLD),
    T("TX: 01 06 00 C9 00 04 [CRC]", ParagraphStyle("code", parent=BODY, fontName="Courier", fontSize=9, backColor=colors.HexColor("#f4f4f4"), borderPad=4)),
    SP(0.3),
    T("5.3 Sensor Configuration", H2),
    T("Write the sensor type code to register 40220. For RTD sensors, also write the wiring mode to register 40221. The device will automatically recalculate linearisation tables.", BODY),
    SP(0.3),
    T("5.4 Scaling the 4–20 mA Output", H2),
    T("Registers 40210 (low range, 4 mA) and 40211 (high range, 20 mA) define the analogue output scaling. Values are in °C × 10. For example, to set range −40 to +120 °C:", BODY),
    T("40210 = 0xFF70 (−400 = −40.0 °C)   40211 = 0x04B0 (1200 = +120.0 °C)", ParagraphStyle("code", parent=BODY, fontName="Courier", fontSize=9, backColor=colors.HexColor("#f4f4f4"), borderPad=4)),
    SP(0.5), PageBreak(),
]

# ── 6. OPC-UA Companion (optional) ───────────────────────────────────────────
story += [
    T("6. OPC-UA Companion Interface (optional)", H1), HR(),
    T("The TH200-UA factory option adds an embedded OPC-UA server (IEC 62541). The server is accessible at the default endpoint:", BODY),
    T("opc.tcp://&lt;device-ip&gt;:4840/TH200", ParagraphStyle("code", parent=BODY, fontName="Courier", fontSize=10, backColor=colors.HexColor("#f4f4f4"), borderPad=4)),
    SP(0.3),
    T("6.1 NodeId Map", H2),
]
nodes = [
    ["NodeId (ns=2)",           "Browse Name",       "Data Type", "Access", "Description"],
    ["i=1001",  "ProcessValue",      "Float",   "RO",  "Temperature in °C"],
    ["i=1002",  "LoopCurrent",       "Float",   "RO",  "4–20 mA loop current"],
    ["i=1003",  "DeviceStatus",      "UInt16",  "RO",  "Status word (see §4.4)"],
    ["i=2001",  "SlaveAddress",      "UInt16",  "RW",  "Modbus slave address"],
    ["i=2002",  "BaudRate",          "UInt32",  "RW",  "Baud rate in bps"],
    ["i=2010",  "RangeLow",          "Float",   "RW",  "4 mA setpoint (°C)"],
    ["i=2011",  "RangeHigh",         "Float",   "RW",  "20 mA setpoint (°C)"],
    ["i=2020",  "SensorType",        "String",  "RW",  "e.g. 'Pt100', 'K-TC'"],
    ["i=9001",  "Manufacturer",      "String",  "RO",  "'THERMTEC INDUSTRIAL'"],
    ["i=9002",  "ModelNumber",       "String",  "RO",  "'TH200'"],
    ["i=9003",  "SerialNumber",      "String",  "RO",  "Device serial number"],
    ["i=9004",  "FirmwareVersion",   "String",  "RO",  "e.g. '4.1.0'"],
]
story += [tbl(nodes, col_widths=[2.2*cm, 3.5*cm, 2.2*cm, 1.5*cm, 6.6*cm]), SP(0.5), PageBreak()]

# ── 7. Troubleshooting ────────────────────────────────────────────────────────
story += [
    T("7. Troubleshooting", H1), HR(),
]
ts = [
    ["Symptom",                     "Likely cause",                   "Remedy"],
    ["No response to Modbus queries","Wrong slave address or baud rate","Check address/baud via keypad; use address 0 broadcast to discover"],
    ["Output stuck at 21 mA",        "Sensor open circuit (burnout up)","Check sensor wiring; verify register 40003 bit 1"],
    ["Output stuck at 3.6 mA",       "Sensor short (burnout down)",    "Check sensor wiring; verify register 40003 bit 1"],
    ["CRC errors",                   "Termination missing",            "Add 120 Ω at both bus ends"],
    ["OVERRANGE / UNDERRANGE alarm", "Range limits too narrow",        "Adjust registers 40210/40211"],
    ["OPC-UA connection refused",    "Non-UA variant ordered",         "Confirm order code includes -UA suffix"],
    ["Calibration drift",            "Ambient temperature extremes",   "Apply user offset via register 40230"],
]
story += [tbl(ts, col_widths=[4.5*cm, 5*cm, 6.5*cm]), SP(0.5)]

# ── 8. Specifications Summary ─────────────────────────────────────────────────
story += [
    T("8. Complete Electrical Specifications", H1), HR(),
]
specs = [
    ["Parameter",                "Value",                     "Condition"],
    ["Supply voltage",           "12–36 V DC",                "Two-wire loop"],
    ["Quiescent current",        "< 3.6 mA",                  "4 mA output, 24 V supply"],
    ["Output current range",     "3.6–21.0 mA",               "Including NAMUR NE43 levels"],
    ["Load resistance",          "0–600 Ω",                   "At 24 V DC supply"],
    ["Accuracy",                 "±0.1 °C",                   "Pt100, 0–100 °C, 23 °C ambient"],
    ["Long-term stability",      "< 0.1 °C / year",           "Typical"],
    ["Response time (T63)",      "≤ 5 s",                     "Damping = 0"],
    ["EMC immunity",             "EN 61326-1, Class A",        "—"],
    ["Safety integrity",         "SIL 2 (IEC 61508)",         "Hardware fault tolerance 0"],
    ["MTBF",                     "> 50 years",                 "Siemens SN 29500, 40 °C"],
    ["RS-485 unit load",         "1/8",                       "Up to 256 devices"],
    ["RS-485 max. bus length",   "1200 m",                    "At 9600 bps, 120 Ω terminated"],
    ["Power consumption",        "< 0.5 W",                   "Typical at 24 V, 12 mA"],
]
story += [tbl(specs, col_widths=[5.5*cm, 4.5*cm, 6*cm]), SP(0.5)]

# ── Footer note ───────────────────────────────────────────────────────────────
story += [
    HR(),
    T("© 2026 THERMTEC Industrial Instruments GmbH. All rights reserved. TH200-MAN-003 Rev 4.1.", SMALL),
    T("Specifications subject to change without notice. Visit www.thermtec.example.com for the latest documentation.", SMALL),
]

doc.build(story)
print(f"Generated: {OUT}")
