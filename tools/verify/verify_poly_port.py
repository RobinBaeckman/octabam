#!/usr/bin/env python3
"""POLY end to end under the port: a project's pattern plays POLY, a chord included, through the
firmware, and the stream the track hands the DSP is POLY's reference, bit for bit.

  OT_PROJECT=<project dir> python3 tools/verify/verify_poly_port.py <remix>    (stage image)

The fixture (ab_fixture.prepare, then): audio track 1 is FLEX signed POLY ('PO' 1 at Part' +
0x3c) with POLY's defaults in its PLAYBACK and SETUP bytes, no FX, no LFO; MIDI track 1 sends on
channel 1 and its pattern 1 has two trigs, step 1 C3 with NOT2 +4 and NOT3 +7 (C E G) and step 3 G3.
Nothing else plays.  The image boots under the port with the sequencer on its internal clock.

What is compared: the FLEX record the packer sends core B for track 1 (recloop.track_audio, the
DSP's input for the track, before AMP and the chain) against modules/poly/reference.py stepped
with the keys the table holds.  In that path: the stock sequencer and MIDI track (the trigs, the
chord's three note-ons, the note-offs at LEN), the MIDI send primitive and notes.s (the keys),
mt_render (the ring, the frame call, the 24-bit packing), poly_frame.  Not in it: AMP, the FX,
the mixer, the DSP -- the gate checks only that the chain output and main out are not silent.

The keys are not timestamped by the port, so the gate takes the MIDI events in the order the
UART capture has them and finds, frame by frame, how many of them the table had taken before the
frame's call: the frames must then match exactly, every sample, from the first key to the end.
A wrong voice, a lost note of the chord or a wrong packing cannot be fitted that way.
"""
import copy
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools/hw"), str(ROOT / "tools/harness"), str(ROOT / "tools/verify")]
import ot_project as otp  # noqa: E402
import blockdump as bd  # noqa: E402
import recloop as rl  # noqa: E402
from ab_fixture import prepare  # noqa: E402
import importlib.util  # noqa: E402

FRAMES = 900
CHANNEL = 0                                         # MIDI track 1's CHAN 1
STEPS = {0: (48, (68, 71)), 2: (55, ())}            # step: (NOTE, NOT2..), offsets around 64
S24 = 0x7FFFFF


def load_ref():
    s = importlib.util.spec_from_file_location("pref", ROOT / "modules/poly/reference.py")
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def fixture(project, dest, ref):
    fix = prepare(project, dest)
    for bank in fix.glob("bank*.work"):
        def mutate(d):
            for pi in range(8):
                base = otp.PART_BASE + pi * otp.PART_STRIDE + 9
                d[base + 0x22] = 1
                d[base + 60:base + 63] = b"PO\x01"
                d[base + 0x30:base + 0x36] = bytes(ref.DEFAULTS[:6])
                d[base + 0x1E0:base + 0x1E6] = bytes(ref.DEFAULTS[6:])
                for t in range(8):
                    at = base + 0x3E2 + 32 * t       # MIDI page 1 (midi_fixture's template)
                    d[at:at + 32] = bytes.fromhex(
                        "3c 64 06 40 40 40 20 20 20 00 00 00 40 00 00 05 "
                        "00 06 40 00 7f 00 00 40 00 00 00 00 00 00 00 00")
                    d[at + 6:at + 12] = bytes(6)    # no MIDI LFO
                    setup = base + 0x4E2 + 36 * t
                    d[setup] = CHANNEL + 1 if t == 0 else 0
                    for field, value in ((3, 0), (5, 0), (12, 0), (13, 3), (15, 2), (16, 0), (18, 0), (19, 0)):
                        d[setup + field] = value
            for p in range(16):
                end = 0x16 + (p + 1) * 0x8EEC
                d[end - 11:end - 6] = bytes((16, 2, 64, 2, 0))
                for t in range(8):
                    at = 0x492E + p * 0x8EEC + t * 0x8B9
                    assert d[at:at + 4] == b"MTRA"
                    d[at + 9:at + 33] = bytes(24)
                    d[at + 0x39:at + 0x839] = b"\xff" * 2048
                    d[at + 0x31:at + 0x33] = bytes((16, 2))
                    if p == 0 and t == 0:
                        d[at + 9:at + 17] = sum(1 << s for s in STEPS).to_bytes(8, "big")
                        for s, (note, more) in STEPS.items():
                            lock = at + 0x39 + s * 32
                            d[lock:lock + 2] = bytes((note, 100))
                            d[lock + 3:lock + 3 + len(more)] = bytes(more)
        otp._bank_write(fix, int(bank.stem[4:]), mutate, guard=False)
    return fix


def midi_events(raw):
    """(on, note) for channel CHANNEL's note messages, running status kept, in order."""
    out, status, data = [], None, []
    for b in raw:
        if b >= 0xF8:
            continue
        if b & 0x80:
            status, data = (b if b < 0xF0 else None), []
            continue
        if status is None:
            continue
        data.append(b)
        if len(data) == (1 if status & 0xF0 in (0xC0, 0xD0) else 2):
            if status & 0x0F == CHANNEL and status & 0xF0 in (0x80, 0x90):
                out.append((status & 0xF0 == 0x90 and data[1] > 0, data[0]))
            data = []
    return out


def apply(keys, ev):
    """The table's keys (notes.s): on takes the first free slot, off clears the note's slot."""
    on, note = ev
    k = note << 8
    if on:
        if 0 in keys:
            keys[keys.index(0)] = k
    elif k in keys:
        keys[keys.index(k)] = 0


def zero_poly(ref, pv):
    """The reference as the table starts it: every state word zero (a voice's key 0, not None)."""
    p = ref.Poly(pv, seed=0)
    for v in p.v:
        v.ph, v.key = 0, 0
    return p


def q24(x):
    return max(-S24, min(S24, x >> 5))


def fit(ref, pv, actual, events):
    """Frame by frame, how many events the table had taken: the first count whose frame matches.
    Backtracks over the counts that also match.  -> (frames matched, the event count each frame)."""
    first = next((i for i, x in enumerate(actual) if x), None)
    if first is None:
        return None, "the track's stream is silent"
    best = (0, None)
    for lead in range(16):                          # where the ring's frame starts in the stream
        start = first - lead
        if start < 0 or any(actual[:start]):
            continue
        nfr = (len(actual) - start) // 16
        stack = [(0, 0, zero_poly(ref, pv), [0, 0, 0, 0], [])]
        while stack:
            f, used, p, keys, path = stack.pop()
            if f > best[0]:
                best = (f, (start, path))
            if f == nfr:
                return f, (start, path)
            want = actual[start + 16 * f:start + 16 * (f + 1)]
            options = []
            for j in range(used, min(len(events), used + 4) + 1):
                q, kk = copy.deepcopy(p), list(keys)
                for ev in events[used:j]:
                    apply(kk, ev)
                left, _ = q.step(kk)
                if [q24(x) for x in left] == want:
                    options.append((j, q, kk))
            for j, q, kk in reversed(options):      # fewest events first
                stack.append((f + 1, j, q, kk, path + [j]))
            if len(stack) > 64:
                del stack[:-64]
    return best[0], best[1]


def main():
    remix = sys.argv[1] if len(sys.argv) > 1 else "poly"
    project = os.environ.get("OT_PROJECT")
    if not project:
        print("[SKIP] POLY port: set OT_PROJECT to a project fixture")
        return 0
    ref = load_ref()
    out = ROOT / "out" / "poly" / "port-gate"
    out.mkdir(parents=True, exist_ok=True)
    fix = fixture(project, out / "project", ref)
    card = out / "card.img"
    subprocess.run([sys.executable, str(ROOT / "tools/emu/ot_emu/stage_card.py"), str(fix), "OCTABAM", "RIG",
                    "--tree", str(out / "tree"), "--out", str(card)], check=True, cwd=ROOT)
    image = out / "image.bin"
    shutil.copy2(ROOT / "out/mainos_bus.bin", image)
    syms = {l.split()[-1]: int(l.split()[0], 16) for l in subprocess.check_output(
        ["m68k-elf-nm", str(ROOT / "out/platform/runtime/runtime.elf")], text=True).splitlines() if len(l.split()) == 3}
    if "mt_render" not in syms or "poly_frame" not in syms:
        print(f"  [FAIL] remix {remix}: the image has no machine table with POLY (mt_render, poly_frame)")
        return 1
    dump, midi = out / "blocks.bin", out / "out.midi"
    spans = f"{syms['mt_vtracks']:#x},176={out / 'vtrack.bin'};{syms['mt_keys']:#x},16={out / 'keys.bin'}"
    cmd = [str(ROOT / "out/emu/ot_emu"), "--image", str(image), "--card", str(card), "--set", "OCTABAM",
           "--project", "RIG", "--load-ms", "20000", "--sequencer", "--internal-clock", "--bank", "0",
           "--frames", str(FRAMES), "--dsp", "--main-level", "64", "--audio-out", str(out / "audio"),
           "--block-dump", str(dump), "--midi-out", str(midi), "--mem-dump", spans]
    with open(out / "port.log", "w") as log:
        log.write(" ".join(cmd) + "\n")
        log.flush()
        subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, check=True, timeout=1800)
    text = (out / "port.log").read_text()
    fails = 0

    def check(ok, what, why=""):
        nonlocal fails
        fails += not ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {what}" + ("" if ok or not why else f": {why}"), flush=True)

    check(re.search(rf"frames run : {FRAMES} .*run ended REACHED", text) is not None, "the run reached its frames",
          text[-600:])
    vt = (out / "vtrack.bin").read_bytes()
    check(int.from_bytes(vt[:4], "big") > 0, "track 1 is on a frame machine (the table's T_MACH)", vt[:4].hex())
    check(list(vt[36:48]) == ref.DEFAULTS, "the voice read the track's twelve knobs",
          f"{list(vt[36:48])} != {ref.DEFAULTS}")
    events = midi_events(midi.read_bytes())
    ons = [n for on, n in events if on]
    check(sorted(ons[:3]) == [48, 52, 55] and ons[3:4] == [55], "the MIDI track sent the chord C E G, then G",
          str(events))
    c = bd.classes(bd.read(dump))
    left, right = rl.track_audio(c, 1), rl.track_audio(c, 1, True)
    check(left == right and len(left) > 16 * 200, "track 1's stream: mono, L = R", f"{len(left)} samples")
    nfr, how = fit(ref, list(ref.DEFAULTS), left, events)
    total = (len(left) - (how[0] if how else 0)) // 16
    check(how is not None and nfr == total and nfr > 0,
          f"the stream is POLY's reference bit for bit: {nfr} of {total} frames"
          + (f", keys taken at frames {[i for i in range(1, len(how[1])) if how[1][i] != how[1][i-1]] if how else ''}"),
          str(how)[:300])
    sounding = max(map(abs, left)) if left else 0
    check(sounding > 1000, f"the voice sounds: peak {sounding} of {S24}")
    chain = rl.readback_audio(c, 1)
    check(max(map(abs, chain), default=0) > 100, "the chain output after AMP is not silent (not compared)")
    (out / "result.json").write_text(json.dumps({"frames": nfr, "events": events, "path": how[1] if how else None},
                                               indent=1) + "\n")
    print(f"  [{'ok' if not fails else 'FAIL'}] POLY end to end: {fails} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
