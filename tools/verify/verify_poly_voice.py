#!/usr/bin/env python3
"""POLY's ColdFire voice, run on the emulated chip against its reference, frame by frame.

    .venv/bin/python3 tools/verify/verify_poly_voice.py test/poly   # after make bus REMIX=test/poly

modules/poly/voice.s (poly_frame) is the integer reference (modules/poly/reference.py
Poly.step: the keys to the voices, the noise, four voices, the HPF, the soft clip)
written for the MCF54454. This boots the built image, calls poly_frame on a state
struct in scratch RAM, and after EVERY frame compares the 16 L and 16 R samples and
the whole state (keys, the allocator's clock, every voice, the HPF, the DC blocker,
the noise generator) with the reference's, bit for bit. Episodes: each knob
at 0, 64 and 127 on chord stabs, the defaults on stabs, a pad and a line, key changes
that make the allocator choose (a silent voice, the quietest releasing one), and
random knob sets with knobs moving between frames. Also: tables.inc is current, the
call keeps d2-d7/a2-a6 and the firmware's EMAC state, and instructions a sample stay
under BUDGET with all four voices sounding.

Does not prove: cycles (instructions are a proxy), how notes reach a machine on a
unit (keys here are an array; no machine row calls poly_frame yet), nor the oldest-
voice steal: with four keys and four voices a key that goes down always finds a
silent or releasing voice, so that branch never runs (it is there for more keys).
"""
import importlib.util
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import voice_rig as V  # noqa: E402

ST, PV, KEYS_AT, OUT = 0x47f11000, 0x47f11800, 0x47f11810, 0x47f11900
BUDGET = 600        # instructions a sample, four voices sounding: three octa303 voices,
                    # which have run on a unit for hours (modules/octa303 proof_note)
STAGES = ("idle", "attack", "decay", "release")
VFIELDS = ("ph", "sub", "s0", "s1", "s2", "s3", "y4", "cap", "env", "stage", "g", "note", "key", "age")
HEAD = ("k0", "k1", "k2", "k3", "clock", "hp", "dc", "nz")


def load_ref():
    s = importlib.util.spec_from_file_location("pref", V.ROOT / "modules/poly/reference.py")
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return m


def voice_words(v):
    return [v.ph, v.sub, *v.s, v.y4, v.cap, v.env, STAGES.index(v.stage), v.g, v.note,
            -1 if v.key is None else v.key, v.age]


def state_words(p):
    w = [*p.keys, p.clock, p.hp, p.dc, p.nz]
    for v in p.v:
        w += voice_words(v)
    return [V.s32(x & 0xFFFFFFFF) for x in w]


def describe(go, wo, gs, ws):
    k = next((i for i in range(32) if go[i] != wo[i]), None)
    s = f"{'L' if k < 16 else 'R'}[{k % 16}] {go[k]}!={wo[k]} " if k is not None else ""
    s += " ".join(f"{HEAD[i]} {gs[i]}!={ws[i]}" for i in range(len(HEAD)) if gs[i] != ws[i])
    for n in range(4):
        a = len(HEAD) + 14 * n
        g, w = gs[a:a + 14], ws[a:a + 14]
        if g != w:
            s += f" voice{n}: " + " ".join(f"{VFIELDS[q]} {g[q]}!={w[q]}" for q in range(14) if g[q] != w[q])
    return s


def frames_of(ref, x):
    """Key tracks (samples x KEYS, float notes) -> one Q8 key list a frame, as Poly.frame reads them."""
    out = []
    for f in range(len(x) // ref.FRAMES):
        row = x[f * ref.FRAMES]
        out.append([round(float(n) * 256) if n > 0 else 0 for n in row])
    return out


def episodes(ref):
    rnd = random.Random(13)
    sig = {k: frames_of(ref, v) for k, v in ref.signals().items()}
    stabs = sig["stabs"][:300]
    yield "defaults stabs", list(ref.DEFAULTS), sig["stabs"], ()
    yield "defaults pad", list(ref.DEFAULTS), sig["pad"][:700], ()
    yield "defaults line", list(ref.DEFAULTS), sig["line"][:400], ()
    pv = list(ref.DEFAULTS)
    for k, v in (("WAVE", 127), ("SUB", 127), ("HPF", 0), ("NOISE", 127), ("S", 127), ("RES", 100), ("FREQ", 90)):
        pv[ref.SLOT[k]] = v
    yield "all four sounding, every path", pv, [[48 * 256, 55 * 256, 60 * 256, 63 * 256 + 37]] * 120, ()
    for i, name in enumerate(ref.NAMES):
        for k in (0, 64, 127):
            pv = list(ref.DEFAULTS); pv[i] = k
            yield f"{name} {k}", pv, stabs, ()
    # the allocator: keys changing while others ring out (R long), fast re-presses, one key moving
    q = 256
    seq = ([[48 * q, 0, 0, 0]] * 10 + [[50 * q, 0, 0, 0]] * 10 + [[50 * q, 53 * q, 0, 0]] * 10
           + [[0, 53 * q, 57 * q, 0]] * 10 + [[60 * q, 53 * q, 57 * q, 64 * q]] * 10 + [[0, 0, 0, 0]] * 5
           + [[62 * q, 0, 0, 67 * q]] * 10 + [[62 * q, 65 * q, 69 * q, 67 * q]] * 5 + [[0, 0, 0, 0]] * 60)
    pv = list(ref.DEFAULTS); pv[ref.SLOT["R"]] = 110
    yield "allocator: re-presses under long releases", pv, seq, ()
    pv = list(ref.DEFAULTS); pv[ref.SLOT["R"]] = 0
    yield "allocator: short releases go silent", pv, seq, ()
    for e in range(14):
        pv = [rnd.randrange(128) for _ in ref.NAMES]
        keys, cur = [], [0, 0, 0, 0]
        while len(keys) < 300:
            k = rnd.randrange(4)
            cur = list(cur); cur[k] = 0 if rnd.random() < 0.4 else rnd.randrange(24, 96) * q + rnd.randrange(q)
            keys += [cur] * rnd.randrange(1, 20)
        moves = [(f, rnd.randrange(12), rnd.randrange(128)) for f in sorted(rnd.sample(range(1, 300), 12))]
        yield f"random {e} (knobs moving)", pv, keys[:300], moves


def main(argv):
    if (argv[1] if len(argv) > 1 else "").split("/")[-1] != "poly":
        sys.exit("usage: verify_poly_voice.py test/poly")
    ref = load_ref()
    fails = 0
    ok, msg = V.tables_current("poly")
    fails += not ok
    print(f"  [{'PASS' if ok else 'FAIL'}] tables.inc matches reference.py" + ("" if ok else ": " + msg))

    rig = V.Rig("poly", "poly_frame", "voice")
    p = ref.Poly(ref.DEFAULTS)
    rig.write_longs(ST, state_words(p)); rig.uc.mem_write(PV, bytes(ref.DEFAULTS))
    rig.write_longs(KEYS_AT, [48 * 256, 0, 0, 0])
    lost = rig.abi((ST, PV, KEYS_AT, OUT))
    fails += bool(lost)
    print(f"  [{'PASS' if not lost else 'FAIL'}] keeps d2-d7/a2-a6, the firmware's MACSR and ACC0"
          + ("" if not lost else ": lost " + " ".join(lost)))

    bad, frames, per = [], 0, []
    nst = len(state_words(p))
    for name, pv, keys, moves in episodes(ref):
        p = ref.Poly(pv)
        rig.write_longs(ST, state_words(p))
        mv = {}
        for f, s, v in moves:
            mv.setdefault(f, []).append((s, v))
        for f, kk in enumerate(keys):
            for s, v in mv.get(f, ()):
                p.pv[s] = v
            rig.uc.mem_write(PV, bytes(p.pv))
            rig.write_longs(KEYS_AT, kk)
            live = sum(v.stage != "idle" for v in p.v)
            try:
                n_ins = rig.call((ST, PV, KEYS_AT, OUT), meter=live >= 3 or f in (20, 150))
            except Exception as ex:                          # a fault on the chip is a FAIL, not a crash
                bad.append(f"{name}: frame {f}: {type(ex).__name__} {ex}"); break
            L, R = p.step(kk)
            if n_ins:
                per.append((n_ins / ref.FRAMES, sum(v.stage != "idle" for v in p.v), name))
            want_out, got_out = list(L) + list(R), rig.longs(OUT, 32)
            want_st, got_st = state_words(p), rig.longs(ST, nst)
            frames += 1
            if got_out != want_out or got_st != want_st:
                bad.append(f"{name}: frame {f}: " + describe(got_out, want_out, got_st, want_st)); break
    fails += bool(bad)
    print(f"  [{'PASS' if not bad else 'FAIL'}] poly_frame = the reference, samples and state, {frames} frames"
          + ("" if not bad else f": {len(bad)} episodes differ\n      " + "\n      ".join(bad[:10])))

    worst = max(per, default=(float("inf"), 0, "nothing metered"))
    full = [x for x in per if x[1] >= 4]
    ok = worst[0] <= BUDGET and bool(full)                      # the budget is only proven with every voice on
    fails += not ok
    print(f"  [{'PASS' if ok else 'FAIL'}] {worst[0]:.0f} instructions a sample at most "
          f"({worst[2]}, {worst[1]} voices; {len(full)} metered frames with 4), budget {BUDGET}")
    print("PASS" if not fails else f"FAIL: {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
