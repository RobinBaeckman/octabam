#!/usr/bin/env python3
"""LADDER's ColdFire voice, run on the emulated chip against its reference, frame by frame.

    .venv/bin/python3 tools/verify/verify_ladder_voice.py <remix>   # after make bus REMIX=test/ladder

modules/ladder/voice.s (ladder_frame) is the integer reference
(modules/ladder/reference.py Voice.step) written for the MCF54454. This boots
the built image, calls ladder_frame on a state struct in scratch RAM, and
after EVERY frame compares the 16 samples and the whole state (phases, noise,
the four ladder integrators, glide, gate, contour, DC) with Voice.step's, bit
for bit. The episodes cover each knob at 0, 64 and 127, each wave, held and
released notes, glides, and random knob sets. It also checks:

  - tables.inc is what gen_tables.py makes from reference.py now (no drift);
  - the call keeps d2-d7/a2-a6 and the firmware's MACSR and ACC0;
  - instructions per sample stay under BUDGET (the CPU cost, layer 2).

Does not prove: cycles (an instruction count is a proxy: the EMAC, divides
and cache misses cost more than one), nor that anything calls ladder_frame on
a unit (no machine row yet), nor that the emulator's EMAC matches the chip
past emu_bringup.emac_selftest's four cases.
"""
import importlib.util
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import voice_rig as V  # noqa: E402

ROOT = V.ROOT
s32 = V.s32
ST, PV, OUT = 0x47f10000, 0x47f10100, 0x47f10200     # scratch, as verify_grainer_screen.py
NONE = 0x80000000
STAGES = ("idle", "attack", "decay", "release")
BUDGET = 350        # instructions a sample; octa303's 303 is ~200 and runs 3 tracks for hours


def s32(v):
    return v - (1 << 32) if v & 0x80000000 else v


def pack(v):
    """Voice -> struct state, as voice.s's ST_ offsets lay it out."""
    w = [v.ph1, v.ph2, v.rng, *v.s, NONE if v.tgt is None else v.tgt, v.off,
         int(v.gate), v.env, STAGES.index(v.stage), v.dc]
    return b"".join((x & 0xFFFFFFFF).to_bytes(4, "big") for x in w)


def unpack(b):
    w = [int.from_bytes(b[i:i + 4], "big") for i in range(0, 52, 4)]
    return [w[0], w[1], w[2], *map(s32, w[3:7]), w[7] if w[7] == NONE else s32(w[7]),
            s32(w[8]), w[9], s32(w[10]), w[11], s32(w[12])]


def words(v):
    return unpack(pack(v))


def episodes(ref):
    """(name, pv, [note8 per frame]): each knob at its ends and middle, each wave, then random sets."""
    n = len(ref.NAMES)
    song = ([48 * 256] * 30 + [0] * 20 + [60 * 256] * 20 + [36 * 256] * 30 + [0] * 40
            + [84 * 256] * 10 + [24 * 256] * 10 + [0] * 10)
    yield "defaults", list(ref.DEFAULTS), song
    for i, name in enumerate(ref.NAMES):
        for k in (0, 64, 127):
            pv = list(ref.DEFAULTS); pv[i] = k
            yield f"{name} {k}", pv, song
    for w in range(6):
        pv = list(ref.DEFAULTS); pv[ref.SLOT["WAVE"]] = w * 22
        yield f"WAVE zone {w}", pv, song
    rnd = random.Random(7)
    for e in range(24):
        pv = [rnd.randrange(128) for _ in range(n)]
        notes = []
        while len(notes) < 160:
            notes += [rnd.choice([0, rnd.randrange(12, 108) * 256 + rnd.randrange(256)])] * rnd.randrange(1, 25)
        yield f"random {e}", pv, notes[:160]


def main(argv):
    name = (argv[1] if len(argv) > 1 else "").split("/")[-1]
    if name != "ladder":
        sys.exit("usage: verify_ladder_voice.py test/ladder")
    fails = 0
    ok, msg = V.tables_current("ladder")
    fails += not ok
    print(f"  [{'PASS' if ok else 'FAIL'}] tables.inc matches reference.py" + ("" if ok else ": " + msg))

    s = importlib.util.spec_from_file_location("ref", ROOT / "modules/ladder/reference.py")
    ref = importlib.util.module_from_spec(s); s.loader.exec_module(ref)
    rig = V.Rig("ladder", "ladder_frame", "voice")
    uc = rig.uc
    uc.mem_write(ST, pack(ref.Voice(ref.DEFAULTS))); uc.mem_write(PV, bytes(ref.DEFAULTS))
    lost = rig.abi((ST, PV, 48 * 256, OUT))
    fails += bool(lost)
    print(f"  [{'PASS' if not lost else 'FAIL'}] keeps d2-d7/a2-a6, the firmware's MACSR and ACC0"
          + ("" if not lost else ": lost " + " ".join(lost)))

    # bit-exact, every frame
    total_frames = mismatched = 0
    first = []
    per_sample = []
    for ename, pv, notes in episodes(ref):
        v = ref.Voice(pv)
        uc.mem_write(ST, pack(v)); uc.mem_write(PV, bytes(pv))
        bad = None
        for f, n8 in enumerate(notes):
            meter = f in (5, 60)
            try:
                n_ins = rig.call((ST, PV, n8, OUT), meter=meter)
            except Exception as e:                          # a fault on the chip is a FAIL, not a crash
                bad = f"frame {f}: {type(e).__name__} {e}"
                break
            if meter:
                per_sample.append((n_ins / ref.FRAMES, ename))
            want = v.step(n8)
            got = [s32(int.from_bytes(uc.mem_read(OUT + 4 * i, 4), "big")) for i in range(ref.FRAMES)]
            gs, ws = unpack(bytes(uc.mem_read(ST, 52))), words(v)
            total_frames += 1
            if got != want or gs != ws:
                k = next((i for i in range(16) if got[i] != want[i]), None)
                fields = ["ph1", "ph2", "rng", "s0", "s1", "s2", "s3", "tgt", "off", "gate", "env", "stage", "dc"]
                diff = [f"{fields[i]} {gs[i]}!={ws[i]}" for i in range(13) if gs[i] != ws[i]]
                bad = (f"frame {f} note8 {n8}: " + (f"sample {k} {got[k]}!={want[k]} " if k is not None else "")
                       + " ".join(diff[:4]))
                uc.mem_write(ST, pack(v))                  # resync, so one slip does not hide the next
                mismatched += 1
                break
        if bad:
            fails += 1
            first.append(f"{ename}: {bad}")
    ok = not first
    print(f"  [{'PASS' if ok else 'FAIL'}] ladder_frame = Voice.step, samples and state, {total_frames} frames"
          + ("" if ok else f": {len(first)} episodes differ\n      " + "\n      ".join(first[:10])))

    worst = max(per_sample, default=(float("inf"), "nothing metered"))
    ok = worst[0] <= BUDGET
    fails += not ok
    print(f"  [{'PASS' if ok else 'FAIL'}] {worst[0]:.0f} instructions a sample at most "
          f"({worst[1]}; mean {sum(p for p, _ in per_sample) / max(1, len(per_sample)):.0f}), budget {BUDGET}")
    print("PASS" if not fails else f"FAIL: {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
