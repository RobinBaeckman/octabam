#!/usr/bin/env python3
"""The machine table (modules/machines): when it installs, what it claims, and what it runs.

    .venv/bin/python3 tools/verify/verify_machines.py machines    # after make bus REMIX=machines

1. Selection: no machine, or ANALOG BD or OCTA303 alone (each with its own proven claims), gets
   no table; two machines, or one without claims of its own (POLY), get it; the registry appends
   MACHINES exactly then; every client claim on an owned site is overridden; rows are by key.
2. Under Unicorn, the table's own source linked with the four machines' sources as the platform
   links them (MT_CLIENT): each track's row (static, FLEX, then each machine's); the list's
   drawer stubs over every top row and screen row; the names by row; the main commit signing a
   track for each machine (its defaults in the Part and the shadow, its signature) and unsigning
   it for a stock row, from every starting machine; the note input: a chord on MIDI track 1's
   channel holds POLY's four keys on audio track 1 and posts it one START, the note-offs free
   them and post one release, another channel and a LADDER track's second key are left alone.
3. Installed (stage image, when out/mainos_bus.bin is the remix's): every owned site holds the
   table's write, and the FLEX kind entry and the four record-table readers point at the table.

Does not prove: the screens (each machine's UI gate does, under the port), the sound
(verify_poly_port), or the unit.
"""
import hashlib
from pathlib import Path
import runpy
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools/verify"))
import toolpath  # noqa: E402,F401
from remix import registry  # noqa: E402
import verify_hooks as VH  # noqa: E402

DECL = runpy.run_path(str(ROOT / "modules/machines/manifest.py"))
BASE_IMG = 0x40000400
MACH = ("ANALOG BD", "LADDER", "OCTA303", "POLY")       # rows 5..8, by key
fails = 0


def check(ok, what):
    global fails
    print(f"  [{'PASS' if ok else 'FAIL'}] {what}")
    fails += not ok


def selection():
    known = registry.modules()
    sel = known["MACHINES"].select
    for keys, want in (((), False), (("ANALOG BD",), False), (("OCTA303",), False),
                       (("ANALOG BD", "OCTA303"), True), (("POLY",), True), (("LADDER",), True), (MACH, True)):
        check(bool(sel(frozenset(keys))["linked"]) == want, f"{' + '.join(keys) or 'no machine'}: "
              f"{'the table' if want else 'no table'}")
    check([k for k, _m in DECL["machines"](set(MACH) | {"FILTER"})] == list(MACH), "rows by key: " + ", ".join(MACH))
    from remix import ledger
    two = [known[k] for k in ("ANALOG BD", "OCTA303", "MEMORY")]
    check(ledger.check(two) != [] and ledger.check(two + [known["MACHINES"]]) == [],
          "ANALOG BD + OCTA303: refused without MACHINES, clean with it")
    for name, want in (("analog-bassdrum", False), ("octa303", False), ("machines-pair", True), ("machines", True),
                       ("poly", True), ("octabam", False)):
        try:
            r = registry.remix(name)
        except Exception as e:                       # noqa: BLE001  (a missing remix is a FAIL, not a crash)
            check(False, f"remix {name}: {e}")
            continue
        check(("MACHINES" in r.modules) == want, f"remix {name}: MACHINES {'appended' if want else 'absent'}")
    s = sel(frozenset(MACH))
    own = {o.site for o in s["overrides"]}
    for k in ("ANALOG BD", "OCTA303"):
        m = known[k]
        claimed = {d.site for d in m.detours} | {r.addr for r in m.symbol_refs} | {p.addr for p in m.pokes}
        want = {a for a in claimed if any(a < st + n and st < a + 4 for st, n in DECL["_owned_spans"](4, True))}
        got = {o.site for o in s["overrides"] if o.module == k}
        check(got == want and want, f"{k}: its {len(want)} claims on owned sites overridden, its others kept "
              f"({len(claimed - want)})")
    check(0x400D6438 in own and all(m.machine.render or m.machine.frame for k in MACH for m in (known[k],)),
          "each machine's sound is a frame or a render; the FLEX entry is the table's")


def unicorn():
    from unicorn import m68k_const as mc
    known = registry.modules()
    keys = set(MACH) | {"MACHINES"}
    units = [(k, u) for k in MACH for u in known[k].linked]
    units += [("MACHINES", u) for u in known["MACHINES"].select(frozenset(keys))["linked"]]
    with tempfile.TemporaryDirectory(prefix="octabam-machines-") as td:
        segs, sym = VH._link_units(Path(td), keys, units)
    u = VH._uc(segs)
    u.mem_map(0x80000000, 0x100000)
    BANK, PARTX, LIST = 0x42000000, 0x42000000 + 0x8ED80, 0x460E7386
    STACK, DONE = 0x47008000, 0x4700FFF0
    FMT, DRAW = 0x4700F000, 0x4700F100
    regs = [getattr(mc, f"UC_M68K_REG_D{i}") for i in range(8)] + [getattr(mc, f"UC_M68K_REG_A{i}") for i in range(7)]
    wr = lambda a, v: u.mem_write(a, (v & 0xFFFFFFFF).to_bytes(4, "big"))     # noqa: E731
    rd = lambda a: int.from_bytes(u.mem_read(a, 4), "big")                    # noqa: E731
    for stop in (DONE, 0x400786A2, 0x400786D4, 0x400786FC, 0x400334DE, 0x40079822, 0x40010BD0):
        u.mem_write(stop, b"\x4e\x71")
    u.mem_write(FMT, bytes.fromhex("202f0004" "06800000" "1000" "4e75"))     # d0 = 4(sp) + 0x1000; rts
    u.mem_write(DRAW, b"\x4e\x75")
    sigs = {m: known[m].machine.sig.encode() + b"\x01" for m in MACH}
    rows = {"static": 0, "flex": 1, **{m: 5 + i for i, m in enumerate(MACH)}}
    drawn = []
    from unicorn import UC_HOOK_CODE
    u.hook_add(UC_HOOK_CODE, lambda uc, pc, size, _d: drawn.append(
        [int.from_bytes(uc.mem_read(uc.reg_read(mc.UC_M68K_REG_A7) + 4 + 4 * i, 4), "big") for i in range(6)]),
        begin=DRAW, end=DRAW)

    def track(t, kind, fresh=True):
        if fresh:
            u.mem_write(PARTX, bytes(0x18B2))
        wr(0x46C82456, BANK)
        u.mem_write(0x100B14CF, b"\x00")
        u.mem_write(PARTX + 0x22 + t, b"\x00" if kind == "static" else b"\x01")
        u.mem_write(PARTX + 0x3C + 30 * t, sigs.get(kind, bytes(3)))

    def run(entry, stop, r=None, stack=()):
        for x in regs:
            u.reg_write(x, 0)
        for i, v in (r or {}).items():
            u.reg_write(regs[i], v)
        u.reg_write(mc.UC_M68K_REG_SR, 0x2000)
        sp = STACK - 4 * len(stack)
        u.mem_write(sp, b"".join(v.to_bytes(4, "big") for v in stack))
        u.reg_write(mc.UC_M68K_REG_A7, sp)
        u.emu_start(entry, stop, count=200000)
        return u.reg_read(mc.UC_M68K_REG_PC), u.reg_read(regs[0]), u.reg_read(mc.UC_M68K_REG_A7) - sp

    got = {}
    for kind in rows:
        track(3, kind)
        got[kind] = run(sym["mt_type"], DONE, {0: 0 if kind == "static" else 1, 8: PARTX + 0x22 + 3}, (DONE,))[1]
    check(got == rows, f"mt_type: {got}")

    n = bad = 0
    total = 5 + len(MACH)
    for top in range(0, total - 5):
        for d2 in range(6):
            wr(LIST, top)
            wr(LIST + 16, total)
            drawn.clear()
            pc, _d0, dsp = run(sym["mt_mc_name"], 0x400786A2, {2: d2, 3: FMT, 4: 0x4444, 7: DRAW, 10: 0x30})
            row = top + d2
            want = [[0x400BA876, 0x4444, 5, 0x31, 0xFFFFFFFF, 0x1000 + row]] if row < total else []
            n += 1
            bad += pc != 0x400786A2 or dsp != 0 or drawn != want
            for kind, typ in rows.items():
                track(2, kind)
                pc = run(sym["mt_mc_box"], 0x400786D4 if typ == row else 0x400786FC, {2: d2, 8: PARTX + 0x22 + 2})[0]
                n += 1
                bad += pc != (0x400786D4 if typ == row else 0x400786FC)
    check(bad == 0, f"mt_mc_name / mt_mc_box: {n} cases, every top row of {total}")

    names = {}
    for r in (1, *range(5, total)):
        pc, d0, _ = run(sym["mt_name"], 0x400334DE if r < 5 else DONE, stack=(DONE, r))
        names[r] = bytes(u.mem_read(d0, 13)).split(b"\0")[0].decode() if pc == DONE else "stock"
    check(names == {1: "stock", **{5 + i: known[m].machine.name for i, m in enumerate(MACH)}}, f"mt_name: {names}")

    res = []
    for target in ("static", *MACH):
        for start in ("flex", *MACH):
            track(4, start)
            u.mem_write(PARTX + 0x30 + 120, bytes(6))
            pc = run(sym["mt_main_commit"], 0x40079822, {0: 0, 1: 4, 4: rows[target], 8: PARTX + 0x22 + 4, 9: BANK})[0]
            sig = bytes(u.mem_read(PARTX + 0x3C + 120, 3))
            shadow = bytes(u.mem_read(0x100A4ECE + 0x3C + 120, 3))
            pb = list(u.mem_read(PARTX + 0x30 + 120, 6))
            want_sig = sigs.get(target, bytes(3))
            want_pb = ([k.default for k in known[target].machine.knobs[:6]] if target in sigs and target != start
                       else [0] * 6)
            res.append(pc == 0x40079822 and sig == want_sig and shadow == want_sig and pb == want_pb)
    check(all(res), f"mt_main_commit: {sum(res)}/{len(res)} -- each machine's row signs the track with its "
                    "defaults (a track already on it keeps its knobs), a stock row unsigns it; the Part and its shadow")

    # the built records: a clone of stock's FLEX record P with the machine's fields, inside its buffer
    FLEX_P = 0x400D31AE
    stock = bytes(u.mem_read(FLEX_P, 0x192))
    res = []
    for i, m in enumerate(MACH):
        mm = known[m].machine
        if mm.record:
            continue
        buf = sym[f"mt_buf{i}"]
        after = bytes(u.mem_read(buf + 0x194, 64))
        try:
            p = run(sym[f"mt_rec{i}"], DONE, stack=(DONE,))[1]
        except Exception as ex:                             # a fault on the chip is a FAIL (29 Oct: the clone ran 0x38 past its buffer)
            res.append(False)
            print(f"      mt_rec{i} ({m}): {type(ex).__name__} {ex}")
            continue
        rec = bytes(u.mem_read(buf, 0x193))
        names = b"".join(k.name.encode().ljust(6, b"\0") for k in mm.knobs)
        res.append(p == buf and rec[0x16:0x16 + 72] == names and rec[0x5E:0x6A] == bytes(k.default for k in mm.knobs)
                   and rec[0x192] == 1 and rec[:4] == stock[:4] and rec[0x15A:0x18A] == stock[0x15A:0x18A]
                   and rec[9:22].split(b"\0")[0] == mm.name.encode() and rec[4:9].split(b"\0")[0] == mm.short.encode()
                   and bytes(u.mem_read(buf + 0x194, 64)) == after)
    check(res and all(res), f"mt_rec: {sum(res)}/{len(res)} built records are P in their buffer, the knobs' names and "
                            "defaults, its name and short name over stock's FLEX record, and nothing past the buffer written")

    # the note input: POLY on audio track 1 (index 0), LADDER on track 2, MIDI tracks 1 and 2 on channel 4 (CHAN 4: status nibble 3, MIDI_TRACKS.md 1)
    track(0, "POLY")
    track(1, "LADDER", fresh=False)
    u.mem_write(PARTX + 0x4E2, bytes((4,)))                 # MIDI track 1: CHAN 4: status nibble 3
    u.mem_write(PARTX + 0x4E2 + 0x24, bytes((4,)))          # MIDI track 2: the same
    u.mem_write(sym["mt_keys"], bytes(128))
    VCMD, BUF = 0x46C80354, 0x4700E000

    def send(msg):
        wr(VCMD, 0)
        wr(VCMD + 4, 0)
        u.mem_write(BUF, bytes(msg))
        pc = run(sym["mt_midi"], 0x40010BD0, stack=(DONE, len(msg), BUF))[0]
        return pc, rd(VCMD), rd(VCMD + 4), [rd(sym["mt_keys"] + 4 * i) for i in range(8)]

    chord = [0x93, 48, 100, 0x93, 55, 100, 0x93, 60, 100, 0x93, 64, 100]
    pc, v0, v1, keys = send(chord)
    check(pc == 0x40010BD0 and v0 == 0x1D and keys[:4] == [48 * 256, 55 * 256, 60 * 256, 64 * 256]
          and keys[4] == 48 * 256 and v1 == 0x1D,
          f"a four-note chord on channel 4: POLY holds {[k >> 8 for k in keys[:4]]}, one START; "
          f"LADDER (one key) holds {keys[4] >> 8} ({v0:#x}, {v1:#x})")
    pc, v0, v1, keys = send([0xB3, 1, 2, 0x95, 70, 100])
    check(v0 == 0 and keys[:4] == [48 * 256, 55 * 256, 60 * 256, 64 * 256], "a CC, and a note on another channel: no change")
    pc, v0, _v1, keys = send([0x83, 55, 0, 0x93, 60, 0])
    check(v0 == 0 and keys[:4] == [48 * 256, 0, 0, 64 * 256], f"two note-offs (0x8n, 0x9n velocity 0): two keys free, no post")
    pc, v0, v1, keys = send([0x83, 48, 0, 0x83, 64, 0])
    check(v0 == 0x40 and keys[:5] == [0] * 5 and v1 == 0x40, f"the last note-off: the release ({v0:#x}, {v1:#x})")


def installed(name):
    img_path = ROOT / "out/mainos_bus.bin"
    sel = {m.key: m for m in registry.selected(registry.remix(name))}
    if "MACHINES" not in sel or not img_path.exists():
        print(f"  [SKIP] installed: remix {name} carries no MACHINES or is not built")
        return
    img = img_path.read_bytes()
    side = img_path.with_suffix(".remix")
    parts = side.read_text().split() if side.exists() else []
    if parts != [name, hashlib.sha256(img).hexdigest()]:
        print(f"  [SKIP] installed: out/mainos_bus.bin is not remix {name}'s build; make bus REMIX={name} first")
        return
    import subprocess
    nm = subprocess.check_output(["m68k-elf-nm", str(ROOT / "out/platform/runtime/runtime.elf")], text=True)
    sym = {f[2]: int(f[0], 16) for line in nm.splitlines() if len(f := line.split()) == 3}
    rd = lambda a: int.from_bytes(img[a - BASE_IMG:a - BASE_IMG + 4], "big")   # noqa: E731
    t = sel["MACHINES"]
    ok = [rd(d.site + 2) == sym[d.symbol] for d in t.detours]
    check(all(ok), f"{sum(ok)}/{len(ok)} owned sites hold the table's routine")
    ok = [rd(r.addr) == sym[r.symbol] for r in t.symbol_refs]
    check(all(ok), f"the FLEX kind entry and the {len(ok) - 1} record-table readers point at the table")
    ok = [img[p.addr - BASE_IMG:p.addr - BASE_IMG + len(p.write)] == p.write for p in t.pokes]
    check(all(ok), f"{len(ok)} row-count, bound and clamp pokes")


def main():
    name = sys.argv[1].split("/")[-1] if len(sys.argv) > 1 else "machines"
    print("verify_machines: selection")
    selection()
    print("verify_machines: the table under Unicorn")
    unicorn()
    print(f"verify_machines: installed ({name})")
    installed(name)
    print(f"verify_machines: {'all passed' if not fails else f'{fails} failed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
