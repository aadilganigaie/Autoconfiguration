#!/usr/bin/env python3
"""Modbus TCP bridge exposing a live MuJoCo UR5e simulation on 0.0.0.0:5021.

Register map follows the official Universal Robots document 16377
(corpus_ur5e/UR_Modbus_Server_Data.pdf, holding register table):

  258      Robot mode. The document lists for CB3 and 3.1:
           Disconnected=0, Confirm_safety=1, Booting=2, Power_off=3,
           Power_on=4, Idle=5, Backdrive=6, Running=7.
           The bridge serves the constant 7 (Running).
  270-275  Joint angles in mrad (base, shoulder, elbow, wrist1-3),
           unsigned 16-bit two's complement.
  280-285  Joint angular velocities in mrad/s, same encoding.
  290-295  Joint currents (mA) and 300-305 joint temperatures (deg C)
           are NOT backed by the physics simulation; the bridge serves 0
           for them rather than inventing plausible values.
  128-255  General purpose 16 bit registers, READ/WRITE plain storage.

All registers outside 128-255 are read-only: writes to them are accepted
on the wire but do not stick, so a client read-back returns the live
(or zero) value. The CLARITY Modbus deployer surfaces such writes as
verification mismatches, which is the honest behavior for a real UR.

Ground truth for external verification is written atomically every
STATE_PERIOD_S seconds to clarity/evaluation/results/ur5e_bridge_state.json.

Usage:
    python scripts/run_ur5e_mujoco_bridge.py [--host 0.0.0.0] [--port 5021]
"""
import argparse
import asyncio
import json
import logging
import math
import os
import signal
import sys
import tempfile
import threading
import time
from pathlib import Path

import mujoco
import numpy as np
from pymodbus.datastore import (
    ModbusDeviceContext,
    ModbusSequentialDataBlock,
    ModbusServerContext,
)
from pymodbus.server import StartAsyncTcpServer

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SCENE = BASE_DIR / "third_party/mujoco_menagerie/universal_robots_ur5e/scene.xml"
DEFAULT_STATE_FILE = BASE_DIR / "clarity/evaluation/results/ur5e_bridge_state.json"

# UR document 16377 register addresses.
ROBOT_MODE_REGISTER = 258
ROBOT_MODE_RUNNING = 7  # "Running=7" per the document's robot mode list
JOINT_ANGLE_BASE = 270       # 270-275, mrad
JOINT_VELOCITY_BASE = 280    # 280-285, mrad/s
GP_REGISTER_FIRST = 128      # 128-255 "General purpose 16 bit registers", R/W
GP_REGISTER_LAST = 255

# Function codes that address the holding register block in pymodbus.
_HOLDING_FUNC_CODES = frozenset({3, 6, 16, 22, 23})

# Slow smooth motion around the home keyframe so live values visibly change.
MOTION_AMPLITUDE_RAD = 0.10
MOTION_FREQUENCY_HZ = 0.05
MOTION_PHASES_RAD = np.arange(6) * (math.pi / 3.0)
MAX_COMMANDED_JOINT_VELOCITY_RAD_S = MOTION_AMPLITUDE_RAD * 2.0 * math.pi * MOTION_FREQUENCY_HZ

STATE_PERIOD_S = 0.5
STEPS_PER_SLICE = 25  # 25 steps x 2 ms model timestep = 50 ms of sim time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("ur5e_bridge")


def to_u16(value: float) -> int:
    """Round to integer and encode as unsigned 16-bit two's complement."""
    return int(round(value)) & 0xFFFF


class Ur5eSimulation(threading.Thread):
    """Real-time MuJoCo physics loop for the Menagerie UR5e scene."""

    def __init__(self, scene_path: Path, state_file: Path) -> None:
        super().__init__(name="ur5e-physics", daemon=True)
        self._model = mujoco.MjModel.from_xml_path(str(scene_path))
        self._data = mujoco.MjData(self._model)
        mujoco.mj_resetDataKeyframe(self._model, self._data, 0)  # home keyframe
        self._home_ctrl = self._data.ctrl[:6].copy()
        self._state_file = state_file
        # Named _halt: threading.Thread reserves the _stop attribute.
        self._halt = threading.Event()
        self._lock = threading.Lock()
        self._qpos = self._data.qpos[:6].copy()
        self._qvel = self._data.qvel[:6].copy()
        self._sim_time = float(self._data.time)

    def stop(self) -> None:
        self._halt.set()

    def run(self) -> None:
        logger.info(
            "Physics loop started: timestep=%.3fs amplitude=%.3frad freq=%.3fHz "
            "max commanded joint velocity=%.4frad/s",
            self._model.opt.timestep, MOTION_AMPLITUDE_RAD, MOTION_FREQUENCY_HZ,
            MAX_COMMANDED_JOINT_VELOCITY_RAD_S,
        )
        wall_start = time.monotonic()
        sim_start = float(self._data.time)
        next_state_write = 0.0
        while not self._halt.is_set():
            for _ in range(STEPS_PER_SLICE):
                t = float(self._data.time)
                self._data.ctrl[:6] = self._home_ctrl + MOTION_AMPLITUDE_RAD * np.sin(
                    2.0 * math.pi * MOTION_FREQUENCY_HZ * t + MOTION_PHASES_RAD
                )
                mujoco.mj_step(self._model, self._data)
            with self._lock:
                self._qpos = self._data.qpos[:6].copy()
                self._qvel = self._data.qvel[:6].copy()
                self._sim_time = float(self._data.time)
            if self._sim_time >= next_state_write:
                self._write_state()
                next_state_write = self._sim_time + STATE_PERIOD_S
            # Pace the loop to wall-clock real time.
            delay = (wall_start + (float(self._data.time) - sim_start)) - time.monotonic()
            if delay > 0:
                time.sleep(delay)
        self._write_state()
        logger.info("Physics loop stopped at sim time %.2fs", self._sim_time)

    def snapshot(self) -> tuple[float, np.ndarray, np.ndarray]:
        with self._lock:
            return self._sim_time, self._qpos.copy(), self._qvel.copy()

    def register_snapshot(self) -> dict[int, int]:
        """Live values of the simulation-backed holding registers."""
        _, qpos, qvel = self.snapshot()
        regs = {ROBOT_MODE_REGISTER: ROBOT_MODE_RUNNING}
        for i in range(6):
            regs[JOINT_ANGLE_BASE + i] = to_u16(qpos[i] * 1000.0)
            regs[JOINT_VELOCITY_BASE + i] = to_u16(qvel[i] * 1000.0)
        return regs

    def _write_state(self) -> None:
        sim_time, qpos, qvel = self.snapshot()
        regs = self.register_snapshot()
        state = {
            "sim_time": sim_time,
            "wall_time": time.time(),
            "qpos": qpos.tolist(),
            "qvel": qvel.tolist(),
            "register_snapshot": {
                str(a): regs[a]
                for a in list(range(JOINT_ANGLE_BASE, JOINT_ANGLE_BASE + 6))
                + list(range(JOINT_VELOCITY_BASE, JOINT_VELOCITY_BASE + 6))
            },
            "robot_mode_register_value": ROBOT_MODE_RUNNING,
            "snapshot_period_s": STATE_PERIOD_S,
            "motion": {
                "amplitude_rad": MOTION_AMPLITUDE_RAD,
                "frequency_hz": MOTION_FREQUENCY_HZ,
                "phases_rad": MOTION_PHASES_RAD.tolist(),
                "max_commanded_joint_velocity_rad_s": MAX_COMMANDED_JOINT_VELOCITY_RAD_S,
            },
        }
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self._state_file.parent), prefix=".ur5e_state_", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(state, fh)
            os.replace(tmp_path, self._state_file)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    async def modbus_action(self, func_code, start_address, address, count,
                            registers, set_values):
        """pymodbus SimDevice action: refresh sim-backed registers on every
        access and make writes outside the general purpose range not stick."""
        if func_code not in _HOLDING_FUNC_CODES:
            return None
        for addr, value in self.register_snapshot().items():
            registers[addr - start_address] = value
        if set_values is not None:
            for i in range(count):
                addr = address + i
                if not (GP_REGISTER_FIRST <= addr <= GP_REGISTER_LAST):
                    set_values[i] = registers[addr - start_address]
        return None


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5021)
    parser.add_argument("--scene", default=str(DEFAULT_SCENE))
    parser.add_argument("--state-file", default=str(DEFAULT_STATE_FILE))
    args = parser.parse_args()

    sim = Ur5eSimulation(Path(args.scene), Path(args.state_file))
    sim.start()

    block = ModbusSequentialDataBlock(1, [0] * 65535)
    device = ModbusDeviceContext(di=block, co=block, hr=block, ir=block)
    device.simdevice.action = sim.modbus_action
    context = ModbusServerContext(devices=device, single=True)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    logger.info("UR5e MuJoCo Modbus bridge on %s:%d (state file: %s)",
                args.host, args.port, args.state_file)
    server_task = asyncio.create_task(
        StartAsyncTcpServer(context=context, address=(args.host, args.port))
    )
    stop_task = asyncio.create_task(stop.wait())
    done, _ = await asyncio.wait({server_task, stop_task},
                                 return_when=asyncio.FIRST_COMPLETED)

    if server_task in done and not stop.is_set():
        sim.stop()
        sim.join(timeout=5.0)
        exc = server_task.exception()
        if exc:
            logger.error("Modbus server terminated: %s", exc)
            raise SystemExit(1)
        return

    logger.info("Shutdown signal received")
    server_task.cancel()
    try:
        await server_task
    except (asyncio.CancelledError, Exception):
        pass
    sim.stop()
    sim.join(timeout=5.0)
    logger.info("Bridge stopped cleanly")


if __name__ == "__main__":
    asyncio.run(main())
