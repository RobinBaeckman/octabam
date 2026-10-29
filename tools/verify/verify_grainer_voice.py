#!/usr/bin/env python3
"""GRAINER's ColdFire voice, run on the emulated chip against its reference, frame by frame.

    .venv/bin/python3 tools/verify/verify_grainer_voice.py <remix>   # after make bus REMIX=test/grainer

modules/grainer/voice.s (grainer_frame) is the integer reference
(modules/grainer/reference.py Engine: schedule, then the grains) written for
the MCF54454. This boots the built image, puts a sample in scratch RAM, calls
grainer_frame on a state struct there, and after EVERY frame compares the 16
L and 16 R samples and the whole state (clock, scan, noise, every grain slot)
with the reference's, bit for bit. Episodes: each knob at 0, 64 and 127, each
mode, two tempos, a short sample (wraps often) and a long one, and random knob
sets with knobs moving between frames. Also: tables.inc is current, the call
keeps d2-d7/a2-a6 and the firmware's EMAC state, and instructions a sample
stay under BUDGET with every grain sounding.

Does not prove: cycles (instructions are a proxy), how the unit holds a Flex
sample (here one long per sample; the unit's RAM is chained 6144-byte blocks,
docs/firmware/RECORDER.md, so the read needs a block lookup there), nor that
anything calls grainer_frame on a unit (no machine row yet).
"""
import pathlib
import random
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import voice_rig as V  # noqa: E402

ST, PV, OUT, SMP = 0x47f11000, 0x47f11400, 0x47f11500, 0x47f20000
BUDGET = 600        # instructions a sample, every grain sounding: three octa303 voices,
                    # which have run on a unit for hours (modules/octa303 proof_note)
FIELDS = ("on", "start", "end", "curi", "curf", "rate", "gl", "gr", "a", "d", "stepa", "stepd")


def load_ref():
    import importlib.util
    s = importlib.util.spec_from_file_location("gref", V.ROOT / "modules/grainer/reference.py")
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return m


def head_words(e):
    return [e.t, e.head >> 16, e.head & 0xFFFF, e.next_at, e.rng.s, e.n, e.spb, 0]


def slot_words(e, g):
    if g is None:
        return [0] * 12
    p = g.base + g.rate * (e.t - g.start)
    return [1, g.start, g.end, (p >> 16) % e.n, p & 0xFFFF, g.rate, g.gl, g.gr, g.a, g.d,
            (1 << 31) // g.a, (1 << 31) // g.d]


def state_words(e):
    w = head_words(e)
    for g in e.slots:
        w += slot_words(e, g)
    return [V.s32(v & 0xFFFFFFFF) for v in w]


def episodes(ref):
    rnd = random.Random(11)
    t = np.arange(88200)
    long_ = 0.4 * np.sin(2 * np.pi * 220 * t / 44100) + 0.2 * np.random.default_rng(3).standard_normal(len(t))
    short = long_[:3000]
    yield "defaults", long_, list(ref.DEFAULTS), 120.0, 400, ()
    pv = list(ref.DEFAULTS)                                      # every grain sounding: OSC, full overlap, AMNT 8
    pv[ref.SLOT["MODE"]], pv[ref.SLOT["DENS"]], pv[ref.SLOT["AMNT"]], pv[ref.SLOT["SIZE"]] = 110, 0, 127, 40
    yield "every grain sounding", long_, pv, 120.0, 400, ()
    for i, name in enumerate(ref.NAMES):
        for k in (0, 64, 127):
            pv = list(ref.DEFAULTS); pv[i] = k
            yield f"{name} {k}", long_, pv, 120.0, 250, ()
    for m in (0, 60, 110):
        for dens in (0, 40, 127):
            pv = list(ref.DEFAULTS); pv[ref.SLOT["MODE"]] = m; pv[ref.SLOT["DENS"]] = dens
            pv[ref.SLOT["SIZE"]] = 20
            yield f"MODE {m} DENS {dens}", long_, pv, 97.3, 300, ()
    pv = list(ref.DEFAULTS); pv[ref.SLOT["SPRD"]] = 127; pv[ref.SLOT["SCAN"]] = 0; pv[ref.SLOT["TUNE"]] = 127
    yield "short sample, wrapping", short, pv, 120.0, 300, ()
    for e in range(16):
        pv = [rnd.randrange(128) for _ in ref.NAMES]
        pv[ref.SLOT["SIZE"]] = rnd.randrange(0, 70)              # grains that also end inside the episode
        moves = [(f, rnd.randrange(12), rnd.randrange(128)) for f in sorted(rnd.sample(range(1, 300), 12))]
        yield f"random {e} (knobs moving)", (short if e % 4 == 0 else long_), pv, rnd.choice((90.0, 120.0, 133.0)), 300, moves


def main(argv):
    if (argv[1] if len(argv) > 1 else "").split("/")[-1] != "grainer":
        sys.exit("usage: verify_grainer_voice.py test/grainer")
    ref = load_ref()
    fails = 0
    ok, msg = V.tables_current("grainer")
    fails += not ok
    print(f"  [{'PASS' if ok else 'FAIL'}] tables.inc matches reference.py" + ("" if ok else ": " + msg))

    rig = V.Rig("grainer", "grainer_frame", "voice")
    x = np.zeros(4000); x[::7] = 0.3
    e = ref.Engine(x, ref.DEFAULTS)
    rig.write_longs(SMP, [int(v) for v in e.x]); rig.write_longs(ST, state_words(e))
    rig.uc.mem_write(PV, bytes(ref.DEFAULTS))
    lost = rig.abi((ST, PV, SMP, OUT))
    fails += bool(lost)
    print(f"  [{'PASS' if not lost else 'FAIL'}] keeps d2-d7/a2-a6, the firmware's MACSR and ACC0"
          + ("" if not lost else ": lost " + " ".join(lost)))

    bad, frames, per = [], 0, []
    for name, x, pv, bpm, nfr, moves in episodes(ref):
        e = ref.Engine(x, pv, seed=7, bpm=bpm)
        rig.write_longs(SMP, [int(v) for v in e.x])
        rig.write_longs(ST, state_words(e))
        rig.uc.mem_write(PV, bytes(e.pv))
        mv = dict(((f, s), v) for f, s, v in moves)
        for f in range(nfr):
            for (mf, s), v in mv.items():
                if mf == f:
                    e.pv[s] = v
            rig.uc.mem_write(PV, bytes(e.pv))
            live = sum(g is not None for g in e.slots)
            try:
                n_ins = rig.call((ST, PV, SMP, OUT), meter=live >= 7 or f in (50, 200))
            except Exception as ex:                          # a fault on the chip is a FAIL, not a crash
                bad.append(f"{name}: frame {f}: {type(ex).__name__} {ex}"); break
            if n_ins:
                per.append((n_ins / ref.FRAMES, live, name))
            t0 = e.t
            e.schedule()
            L, R = e.render_grains(t0, ref.FRAMES)
            want_out, got_out = [int(v) for v in L] + [int(v) for v in R], rig.longs(OUT, 32)
            want_st, got_st = state_words(e), rig.longs(ST, len(state_words(e)))
            frames += 1
            if got_out != want_out or not same_state(got_st, want_st):
                bad.append(f"{name}: frame {f}: " + describe(got_out, want_out, got_st, want_st)); break
    fails += bool(bad)
    print(f"  [{'PASS' if not bad else 'FAIL'}] grainer_frame = the reference, samples and state, {frames} frames"
          + ("" if not bad else f": {len(bad)} episodes differ\n      " + "\n      ".join(bad[:10])))

    worst = max(per, default=(float("inf"), 0, "nothing metered"))
    full = [p for p in per if p[1] >= 8]
    ok = worst[0] <= BUDGET and bool(full)                      # the budget is only proven where the voice is full
    fails += not ok
    print(f"  [{'PASS' if ok else 'FAIL'}] {worst[0]:.0f} instructions a sample at most "
          f"({worst[2]}, {worst[1]} grains; {len(full)} metered frames with 8+ grains), budget {BUDGET}")
    print("PASS" if not fails else f"FAIL: {fails}")
    return 1 if fails else 0


def same_state(got, want):
    if got[:8] != want[:8]:
        return False
    for i in range(8, len(want), 12):
        w, g = want[i:i + 12], got[i:i + 12]
        if w[0] != g[0] or (w[0] and w != g):
            return False
    return True


def describe(go, wo, gs, ws):
    k = next((i for i in range(32) if go[i] != wo[i]), None)
    s = f"{'L' if k < 16 else 'R'}[{k % 16}] {go[k]}!={wo[k]} " if k is not None else ""
    head = ("t", "headi", "headf", "next", "rng", "n", "spb", "pad")
    s += " ".join(f"{head[i]} {gs[i]}!={ws[i]}" for i in range(8) if gs[i] != ws[i])
    for j, i in enumerate(range(8, len(ws), 12)):
        w, g = ws[i:i + 12], gs[i:i + 12]
        if w[0] != g[0] or (w[0] and w != g):
            s += f" slot{j}: " + " ".join(f"{FIELDS[q]} {g[q]}!={w[q]}" for q in range(12) if g[q] != w[q])
            break
    return s


if __name__ == "__main__":
    sys.exit(main(sys.argv))
