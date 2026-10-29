#!/usr/bin/env python3
"""A machine's screen text, called on the emulated ColdFire against its reference.

    .venv/bin/python3 tools/verify/verify_machine_labels.py <remix>   # after make bus

The remix's machine module (test/<name>: modules/<name>/reference.py) links
display formatters named <name>_fmt_<knob>. Each runs under the port on the
built image for all 128 values, and what it prints must equal
reference.label(KNOB, value): the text the screen promises and the mapping the
sound uses live in one file. A knob the reference labels with no formatter
linked fails too. Does not prove: that the firmware calls these on a unit (the
bench writes them into the page it draws; a real build adds the machine type),
nor that the text fits every widget (five characters run on hardware,
PARAM_PAGES.md section 7).
"""
import importlib.util
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import toolpath  # noqa: E402,F401
import emu_bringup as emu  # noqa: E402

BUF = 0x47f00800          # scratch, as tools/build/stock_labels.py


def main(argv):
    name = (argv[1] if len(argv) > 1 else "").split("/")[-1]
    ref_path = ROOT / "modules" / name / "reference.py"
    if not ref_path.exists():
        sys.exit(f"usage: verify_machine_labels.py <remix>: no modules/{name}/reference.py")
    built = (ROOT / "out/mainos_bus.remix").read_text().split()[0]
    if built != name:
        sys.exit(f"out/mainos_bus.bin is {built!r}, not {name!r}: make bus REMIX=test/{name} first")
    s = importlib.util.spec_from_file_location("ref", ref_path)
    ref = importlib.util.module_from_spec(s); s.loader.exec_module(ref)
    rmap = (ROOT / "out/platform/runtime/runtime.map").read_text()
    fmts = {k.upper(): int(a, 16) for a, k in re.findall(rf"(0x[0-9a-f]+)\s+{name}_fmt_(\w+)", rmap)}
    r = emu.boot(str(ROOT / "out/mainos_bus.bin"))
    if not getattr(r, "uc", None):
        sys.exit(f"boot did not reach the handoff: {r.stopped}")
    fails = 0
    for knob in ref.NAMES:
        want = [ref.label(knob, k) for k in range(128)]
        if knob not in fmts:
            if any(w is not None for w in want):
                print(f"  [FAIL] {knob}: reference.label names it, no {name}_fmt_{knob.lower()} linked"); fails += 1
            continue
        bad = []
        for k in range(128):
            r.uc.mem_write(BUF, b"\0" * 32)
            emu._call(r.uc, fmts[knob], (BUF, k))
            got = emu._cstr(r.uc, BUF, 16)
            if got != want[k]:
                bad.append(f"{k}:{got!r}!={want[k]!r}")
        fails += bool(bad)
        print(f"  [{'PASS' if not bad else 'FAIL'}] {knob} prints reference.label for 0..127"
              + ("" if not bad else ": " + " ".join(bad[:8])))
    print("PASS" if not fails else f"FAIL: {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
