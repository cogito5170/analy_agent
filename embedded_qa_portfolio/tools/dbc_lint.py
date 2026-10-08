"""DBC consistency checker.  [A04, A05, A16]

A small standard-library parser for the subset of DBC this project uses
(Intel byte order, classic CAN). It is not a replacement for cantools; it exists
so a broken database fails CI before any test runs, and so the database and the
firmware header cannot drift apart.

Errors
  D01  duplicate message id/name, or duplicate signal name in a message
  D02  signal extends past the message DLC
  D03  signals overlap in the same message
  D04  declared [min|max] cannot be represented by the raw bits
  D05  cyclic message without a GenMsgCycleTime
  D06  Motorola (big-endian) signal: not supported by this checker
  D07  DBC and firmware header disagree (fault bit positions, state values)

    python tools/dbc_lint.py can/bms.dbc [--header firmware/include/bms.h]
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

BO_RE = re.compile(r"^BO_\s+(\d+)\s+(\w+)\s*:\s*(\d+)\s+(\w+)")
SG_RE = re.compile(
    r"^\s*SG_\s+(\w+)\s*:\s*(\d+)\|(\d+)@([01])([+-])\s*\(([^,]+),([^)]+)\)\s*\[([^|]+)\|([^\]]+)\]")
CYCLE_RE = re.compile(r'^BA_\s+"GenMsgCycleTime"\s+BO_\s+(\d+)\s+(\d+)\s*;')
SEND_RE = re.compile(r'^BA_\s+"GenMsgSendType"\s+BO_\s+(\d+)\s+"(\w+)"\s*;')
SEND_DEFAULT_RE = re.compile(r'^BA_DEF_DEF_\s+"GenMsgSendType"\s+"(\w+)"\s*;')
VAL_RE = re.compile(r"^VAL_\s+(\d+)\s+(\w+)\s+(.*);")
CYCLIC_TYPES = {"Cyclic", "CyclicIfActive"}


@dataclass
class Signal:
    name: str
    start: int
    length: int
    intel: bool
    signed: bool
    factor: float
    offset: float
    minimum: float
    maximum: float


@dataclass
class Message:
    id: int
    name: str
    dlc: int
    sender: str
    signals: list[Signal] = field(default_factory=list)


@dataclass
class Database:
    messages: list[Message]
    cycle_ms: dict[int, int]
    send_type: dict[int, str]
    default_send_type: str
    values: dict[tuple[int, str], dict[int, str]]


def parse(text: str) -> Database:
    messages: list[Message] = []
    cycle, send, values = {}, {}, {}
    default_send = "Cyclic"
    for line in text.splitlines():
        if m := BO_RE.match(line):
            messages.append(Message(int(m[1]), m[2], int(m[3]), m[4]))
        elif (m := SG_RE.match(line)) and messages:
            messages[-1].signals.append(Signal(
                m[1], int(m[2]), int(m[3]), m[4] == "1", m[5] == "-",
                float(m[6]), float(m[7]), float(m[8]), float(m[9])))
        elif m := CYCLE_RE.match(line):
            cycle[int(m[1])] = int(m[2])
        elif m := SEND_RE.match(line):
            send[int(m[1])] = m[2]
        elif m := SEND_DEFAULT_RE.match(line):
            default_send = m[1]
        elif m := VAL_RE.match(line):
            pairs = re.findall(r'(-?\d+)\s+"([^"]*)"', m[3])
            values[(int(m[1]), m[2])] = {int(k): v for k, v in pairs}
    return Database(messages, cycle, send, default_send, values)


def check(db: Database) -> list[str]:
    errors: list[str] = []
    seen_ids, seen_names = set(), set()
    for msg in db.messages:
        where = f"{msg.name} (0x{msg.id:X})"
        if msg.id in seen_ids or msg.name in seen_names:
            errors.append(f"D01 {where}: duplicate message id or name")
        seen_ids.add(msg.id)
        seen_names.add(msg.name)

        used: dict[int, str] = {}
        names: set[str] = set()
        for sig in msg.signals:
            if sig.name in names:
                errors.append(f"D01 {where}.{sig.name}: duplicate signal name")
            names.add(sig.name)
            if not sig.intel:
                errors.append(f"D06 {where}.{sig.name}: Motorola byte order not supported")
                continue
            if sig.start + sig.length > msg.dlc * 8:
                errors.append(f"D02 {where}.{sig.name}: bits {sig.start}..{sig.start + sig.length - 1} "
                              f"exceed DLC {msg.dlc}")
            for bit in range(sig.start, sig.start + sig.length):
                if bit in used:
                    errors.append(f"D03 {where}: {sig.name} overlaps {used[bit]} at bit {bit}")
                    break
                used[bit] = sig.name
            if sig.minimum == sig.maximum == 0:
                continue  # [0|0] means "range not declared" in DBC
            if sig.signed:
                raw_lo, raw_hi = -(1 << (sig.length - 1)), (1 << (sig.length - 1)) - 1
            else:
                raw_lo, raw_hi = 0, (1 << sig.length) - 1
            phys = sorted((raw_lo * sig.factor + sig.offset, raw_hi * sig.factor + sig.offset))
            eps = abs(sig.factor) / 2
            if sig.minimum < phys[0] - eps or sig.maximum > phys[1] + eps:
                errors.append(f"D04 {where}.{sig.name}: [{sig.minimum}|{sig.maximum}] outside "
                              f"representable [{phys[0]:g}|{phys[1]:g}]")

        send_type = db.send_type.get(msg.id, db.default_send_type)
        if send_type in CYCLIC_TYPES and db.cycle_ms.get(msg.id, 0) <= 0:
            errors.append(f"D05 {where}: send type {send_type} but no GenMsgCycleTime")
    return errors


def check_header(db: Database, header: str) -> list[str]:
    """The firmware's fault bits and state values must match the database."""
    errors: list[str] = []
    bits = {name: int(shift) for name, shift in re.findall(r"BMS_FAULT_(\w+)\s*=\s*1u\s*<<\s*(\d+)", header)}
    states = {name: int(v) for name, v in re.findall(r"BMS_STATE_(\w+)\s*=\s*(\d+)", header)}

    fault = next((m for m in db.messages if m.name == "BMS_Fault"), None)
    if fault is None:
        errors.append("D07 BMS_Fault message missing")
    else:
        for sig in fault.signals:
            if sig.name == "Counter":
                continue
            c_name = re.sub(r"(?<!^)(?=[A-Z][a-z])", "_", sig.name).upper()  # SigCell -> SIG_CELL
            if c_name not in bits:
                errors.append(f"D07 BMS_Fault.{sig.name}: no BMS_FAULT_{c_name} in header")
            elif bits[c_name] != sig.start:
                errors.append(f"D07 BMS_Fault.{sig.name}: bit {sig.start} in DBC, "
                              f"{bits[c_name]} in header")

    status = next((m for m in db.messages if m.name == "BMS_Status"), None)
    table = db.values.get((status.id, "State"), {}) if status else {}
    if {v: k for k, v in table.items()} != states:
        errors.append(f"D07 BMS_Status.State values {table} do not match header {states}")
    return errors


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    db = parse(Path(args[0]).read_text())
    errors = check(db)
    if "--header" in argv:
        errors += check_header(db, Path(argv[argv.index("--header") + 1]).read_text())
    n_sig = sum(len(m.signals) for m in db.messages)
    print(f"{len(db.messages)} messages, {n_sig} signals")
    for e in errors:
        print("ERROR", e)
    print(f"{len(errors)} error(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
