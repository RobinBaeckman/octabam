"""The rig a machine's voice gate (verify_<name>_voice.py) stands on.

The built image booted under the port, the voice's entry and code range from
runtime.map, an instruction meter over that range, the call ABI check (d2-d7,
a2-a6, the firmware's MACSR and ACC0 come back), and the tables' staleness
check. Each voice is `void <entry>(state*, pv*, a, b)`: four longs.
"""
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import toolpath  # noqa: E402,F401
import emu_bringup as emu  # noqa: E402
from unicorn import UC_HOOK_CODE  # noqa: E402
from unicorn.m68k_const import (UC_M68K_REG_D2, UC_M68K_REG_D7,  # noqa: E402
                                UC_M68K_REG_A2, UC_M68K_REG_A6)

WRAP, KEPT = 0x47f10400, 0x47f10300     # the ABI wrapper, and where it leaves MACSR/ACC0
FW_MACSR, FW_ACC0 = 0x80, 0x12345678     # integer, saturating, a leftover sum: what a voice must not inherit


def s32(v):
    return v - (1 << 32) if v & 0x80000000 else v


def tables_current(module):
    """modules/<module>/tables.inc is what gen_tables.py makes from reference.py now."""
    r = subprocess.run([sys.executable, str(ROOT / "modules" / module / "gen_tables.py"), "--check"],
                       cwd=ROOT, capture_output=True, text=True)
    return r.returncode == 0, r.stdout.strip()


def wrapper(entry):
    """Set the firmware's EMAC state; entry(args); store MACSR and ACC0 at KEPT."""
    src = f"""
        move.l  #{FW_MACSR},%macsr
        move.l  #{FW_ACC0},%acc0
        move.l  %sp@(16),%sp@-
        move.l  %sp@(16),%sp@-
        move.l  %sp@(16),%sp@-
        move.l  %sp@(16),%sp@-
        jsr     {entry:#x}
        lea     %sp@(16),%sp
        move.l  %macsr,%d0
        move.l  %d0,{KEPT:#x}
        move.l  %acc0,%d0
        move.l  %d0,{KEPT + 4:#x}
        rts
"""
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["m68k-elf-as", "-mcpu=54455", "-o", f"{d}/w.o", "-"], input=src, text=True, check=True)
        subprocess.run(["m68k-elf-objcopy", "-O", "binary", "-j", ".text", f"{d}/w.o", f"{d}/w.bin"], check=True)
        return pathlib.Path(f"{d}/w.bin").read_bytes()


class Rig:
    def __init__(self, name, entry_sym, unit):
        built = (ROOT / "out/mainos_bus.remix").read_text().split()[0]
        if built != name:
            sys.exit(f"out/mainos_bus.bin is {built!r}, not {name!r}: make bus REMIX=test/{name} first")
        ok, detail = emu.emac_selftest()
        if not ok:
            sys.exit(f"emulator EMAC is not the chip's: {detail} (scripts/build_unicorn.sh)")
        rmap = (ROOT / "out/platform/runtime/runtime.map").read_text()
        self.entry = int(re.search(rf"(0x[0-9a-f]+)\s+{entry_sym}\b", rmap).group(1), 16)
        sec = re.search(rf"\.text\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+\S*_{unit}\.o", rmap)
        self.end = int(sec.group(1), 16) + int(sec.group(2), 16)
        r = emu.boot(str(ROOT / "out/mainos_bus.bin"))
        if not getattr(r, "uc", None):
            sys.exit(f"boot did not reach the handoff: {r.stopped}")
        self.uc = r.uc
        # the meter: one hook, installed before the voice is first translated (Unicorn
        # attaches a code hook only to code it translates after the hook exists)
        self.count, self.metering = 0, False
        self.uc.hook_add(UC_HOOK_CODE, self._tick, begin=self.entry, end=self.end - 1)
        self.uc.ctl_flush_tb()
        self.uc.mem_write(WRAP, wrapper(self.entry))

    def _tick(self, *_):
        if self.metering:
            self.count += 1

    def call(self, args, meter=False):
        """The voice once; returns the instructions it ran when metered."""
        self.count, self.metering = 0, meter
        try:
            emu._call(self.uc, self.entry, args)
        finally:
            self.metering = False
        return self.count

    def abi(self, args):
        """Call through the wrapper with every callee-saved register marked: what came back wrong."""
        uc = self.uc
        regs = list(range(UC_M68K_REG_D2, UC_M68K_REG_D7 + 1)) + list(range(UC_M68K_REG_A2, UC_M68K_REG_A6 + 1))
        seen = {}
        for i, reg in enumerate(regs):
            seen[reg] = (0x11111111 * (i + 1)) & 0xFFFFFFFF if reg != UC_M68K_REG_A6 else 0x47f0fff0
            uc.reg_write(reg, seen[reg])
        emu._call(uc, WRAP, args)
        lost = [f"reg {reg}" for reg in regs if uc.reg_read(reg) != seen[reg]]
        macsr, acc0 = (int.from_bytes(uc.mem_read(KEPT + i, 4), "big") for i in (0, 4))
        if (macsr, acc0) != (FW_MACSR, FW_ACC0):
            lost.append(f"MACSR/ACC0 {macsr:#x}/{acc0:#x}")
        return lost

    def longs(self, addr, n):
        b = bytes(self.uc.mem_read(addr, 4 * n))
        return [s32(int.from_bytes(b[i:i + 4], "big")) for i in range(0, 4 * n, 4)]

    def write_longs(self, addr, vals):
        self.uc.mem_write(addr, b"".join((v & 0xFFFFFFFF).to_bytes(4, "big") for v in vals))
