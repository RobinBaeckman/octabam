#!/usr/bin/env python3
"""GRAINER's grain strip, run on the emulated ColdFire.

    .venv/bin/python3 tools/verify/verify_grainer_screen.py [remix]   # after make bus

(Its formatters are tools/verify/verify_machine_labels.py's.) The strip: execution starts at the detour site 0x4004c69c (so the jmp the
build planted is exercised too) over a screen buffer the test lays out, and
stops at the stock code it returns to. Three cases: the box showing (rows 39
and 47 lit) draws exactly the columns the engine wrote; a screen without
those rows is left untouched; without the 'GRNV' magic nothing is drawn.
Does not prove: the 5-tick redraw, or that the real SRC page lights those
rows (the bench screenshots show that; nothing here boots the page).
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import toolpath  # noqa: E402,F401
import emu_bringup as emu  # noqa: E402

BUF = 0x47f00800          # scratch, as tools/build/stock_labels.py
SITE, BACK = 0x4004c69c, 0x4004c6a4      # the detour and the stock code after it (manifest.py)
SURF_BUF = 0x400bf116                    # the LCD surface's buffer pointer (view.s)
FAKE = 0x47f10000                        # a 128-column screen buffer the test owns


def strip(uc, view, edges, magic):
    """Run the hook over a fake screen; return column words 0..63 before and after."""
    import random
    rnd = random.Random(7)
    cols = [rnd.getrandbits(32) & ~0x8080 for _ in range(128)]
    if edges:
        cols = [c | 0x8080 if 10 <= x <= 57 else c for x, c in enumerate(cols)]
    uc.mem_write(FAKE, b"".join(c.to_bytes(4, "big") + b"\0" * 4 for c in cols))
    old = uc.mem_read(SURF_BUF, 4)
    uc.mem_write(SURF_BUF, FAKE.to_bytes(4, "big"))
    blk = [rnd.getrandbits(15) & 0x7f00 for _ in range(46)]
    uc.mem_write(view, (b"GRNV" if magic else b"\0" * 4) + b"".join(w.to_bytes(2, "big") for w in blk))
    from unicorn.m68k_const import UC_M68K_REG_A7
    uc.reg_write(UC_M68K_REG_A7, emu.CALL_SP)
    emu._run_until(uc, SITE, BACK)
    after = [int.from_bytes(uc.mem_read(FAKE + 8 * x, 4), "big") for x in range(128)]
    uc.mem_write(SURF_BUF, bytes(old))
    want = list(cols)
    if edges and magic:
        want[10] |= 0x7f00
        for i, w in enumerate(blk):
            want[11 + i] = (cols[11 + i] | 0x7f00) & ~w
    return want, after



def main(argv):
    remix = argv[1] if len(argv) > 1 else "test/grainer"
    built = (ROOT / "out/mainos_bus.remix").read_text().split()[0]
    if built != remix.split("/")[-1]:
        sys.exit(f"out/mainos_bus.bin is {built!r}, not {remix!r}: make bus REMIX={remix} first")
    rmap = (ROOT / "out/platform/runtime/runtime.map").read_text()
    r = emu.boot(str(ROOT / "out/mainos_bus.bin"))
    if not getattr(r, "uc", None):
        sys.exit(f"boot did not reach the handoff: {r.stopped}")
    fails = 0
    view = int(re.search(r"(0x[0-9a-f]+)\s+grainer_view = ", rmap).group(1), 16)
    for name, edges, magic in (("draws the engine's columns into the showing box", True, True),
                               ("leaves a screen without the box untouched", False, True),
                               ("draws nothing before the engine's first frame", True, False)):
        want, got = strip(r.uc, view, edges, magic)
        bad = [x for x in range(128) if want[x] != got[x]]
        fails += bool(bad)
        print(f"  [{'PASS' if not bad else 'FAIL'}] strip {name}"
              + ("" if not bad else f": columns {bad[:8]} e.g. {got[bad[0]]:#010x} != {want[bad[0]]:#010x}"))
    print("PASS" if not fails else f"FAIL: {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
