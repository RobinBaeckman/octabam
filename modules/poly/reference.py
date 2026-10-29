"""POLY: a four-voice polyphonic machine, Roland Juno-106 shaped, as an integer reference.

Each voice is the Juno's: one DCO (saw, pulse with width, a square sub an
octave down) through a coupling capacitor (10 Hz) into a 4-pole low-pass with resonance, and one ADSR that drives
both the filter and the voice's amplitude. After the four voices: the HPF
(four positions), a DC blocker and a soft clip (0.9 tanh). One white noise
source feeds every voice's filter, as the Juno's NOISE slider. Signal order and
ranges: Roland's JUNO-106 specifications (ENV A 1.5 ms..3 s, D and R 1.5 ms..12 s;
HPF 0/1/2/3).

Deviations, by design:
- 4 voices, not 6: the ColdFire budget (README "POLY ... feasibility").
- No chorus: the Octatrack's CHORUS effect on the track does that job, and a
  chorus here cost more than any step after the voices (29 Oct 2026). The output
  is mono, L = R; the effect makes it stereo. Not the Juno's I/II: a generic chorus.
- No LFO, KYBD, VCA GATE, ENV polarity or RANGE knob. The Octatrack's
  LFO page modulates any knob (FREQ, PWM), which is the unit's own way; the
  trig's note does RANGE's job. The filter follows the note by half (LADDER's).
- 12 knobs on the Octatrack's two pages of 6, not the Juno's sliders.

INTEGER, the arithmetic the ColdFire will run, the same as LADDER's (and its
primitives, imported from modules/ladder/reference.py): signals Q28,
coefficients Q31, every product `emul(a, b) = (a * b) >> 31`. Envelopes,
pitch and filter coefficients at frame rate (16 samples), the oscillators,
filters and the amplitude ramp per sample.

The filter: four TPT one-pole stages, each G = g/(1+g), with the resonance fed
back from the last stage's previous sample through a tanh. Cheaper than
LADDER's zero-delay solve (README: the solve was 99 of LADDER's 209
instructions a sample), at the price of a self-oscillation that sits lower than
the cutoff high up.

The input is a set of KEYS pitch tracks, one column per key (the MIDI note
while that key is held, 0 when not), read at each frame start. A key that goes
down takes a voice: a silent one first, else the quietest releasing one, else
the oldest. A key that lifts releases its voice.
"""
import importlib.util
import math
import pathlib

import numpy as np

_s = importlib.util.spec_from_file_location("ladder_ref", pathlib.Path(__file__).resolve().parent.parent / "ladder/reference.py")
L = importlib.util.module_from_spec(_s); _s.loader.exec_module(L)
emul, sat, q31, tdiv, inc_of, blep, tanh28 = L.emul, L.sat, L.q31, L.tdiv, L.inc_of, L.blep, L.tanh28
G_TAB, FC_STEPS, FC_LOW, FC_TOP = L.G_TAB, L.FC_STEPS, L.FC_LOW, L.FC_TOP
Q, Q31, ONE, M32 = L.Q, L.Q31, L.ONE, L.M32

FS, FRAMES = 44100, 16
VOICES = KEYS = 4

KNOBS = [
    ("FREQ", 64, "VCF cutoff, 20 Hz x 2^(k*10/127), stopping at 11 kHz: 64 = 660 Hz, 115 = 10.6 kHz (at C3; it follows the note by half)"),
    ("RES", 24, "VCF resonance: feedback 4.2 k/127, scaled down high up (KS) so the filter sings on its own from about 121 at every cutoff"),
    ("ENV", 48, "how far the envelope opens the cutoff, 6k/127 octaves (48: 2.3)"),
    ("A", 0, "attack, 1.5 ms x 2000^(k/127): 3 s at 127; a straight line"),
    ("D", 72, "decay, 1.5 ms x 8000^(k/127) to -60 dB: 12 s at 127"),
    ("S", 48, "sustain level, k/127"),
    ("R", 48, "release, 1.5 ms x 8000^(k/127) to -60 dB"),
    ("WAVE", 112, "the DCO's two buttons as four zones: OFF 0-31 (sub only), PULSE 32-63, SAW 64-95, P+S 96-127 (112, the default: PWM then moves the sound)"),
    ("PWM", 0, "pulse width: 0 = square (50%), 127 = 5% high"),
    ("SUB", 40, "sub oscillator level (a square an octave down), k/127"),
    ("HPF", 48, "four positions: 0 (0-31) +10 dB below 150 Hz, 1 (32-63, the default) flat, 2 (64-95) 240 Hz, 3 (96-127) 720 Hz"),
    ("NOISE", 0, "white noise into the filters, 0 .. 0.5 of full scale (127 = a saw's level): only while a voice sounds"),
]
NAMES = [k[0] for k in KNOBS]
DEFAULTS = [k[1] for k in KNOBS]
SLOT = {n: i for i, n in enumerate(NAMES)}
WAVES = ("OFF", "PULSE", "SAW", "P+S")
REF_NOTE = 48


def cutoff_hz(k):
    return 20.0 * 2 ** (k * 10 / 127)


def res_k(k):
    return 4.2 * k / 127


def env_oct(k):
    return 6.0 * k / 127


def atk_s(k):
    return 0.0015 * 2000 ** (k / 127)


def dec_s(k):
    return 0.0015 * 8000 ** (k / 127)


def wave(k):
    return k >> 5


def hpf(k):
    return k >> 5


def pw_high(k):
    return 0.5 - 0.45 * k / 127


# ---- tables (Q31 unless said) ---------------------------------------------------------
LN1000 = math.log(1000)
ATK_STEP = [min(Q31 - 1, round(Q31 * FRAMES / (atk_s(k) * FS))) for k in range(128)]
DEC_C = [q31(1 - math.exp(-FRAMES * LN1000 / (dec_s(k) * FS))) for k in range(128)]
SUS_L = [round((Q31 - 1) * k / 127) for k in range(128)]
ENV_FLOOR = round(Q31 * 1e-5)                           # -100 dB: a released voice is silent below it
CUT_I = [round(FC_STEPS * k * 10 / 127) for k in range(128)]
ENV_I = [round(FC_STEPS * env_oct(k)) for k in range(128)]
K8 = [q31(res_k(k) / 8) for k in range(128)]
# the cutoff stops at FS/4 (11 kHz), where G = 1/2: a stage's state then moves to
# 2G u + (1 - 2G) s, a mix of its input and itself, so with |u| < 1 (the tanh) no stage
# ever leaves +-1, and the loop's feedback stays under 4.2
# (above it the four stages rang past +-8 at RES 127)
FC_MAX = FC_LOW + int(FC_STEPS * math.log2(FS / 4 / 20))


def _k_crit(G):
    """Where the loop with its one-sample delay starts to oscillate: 1 / |L| at the
    frequency where L = z^-1 H1(z)^4 turns half a cycle, H1 the TPT one-pole
    G (1 + z^-1) / (1 - (1 - 2G) z^-1). 4 when the delay costs no phase (low G)."""
    w = np.linspace(1e-4, math.pi - 1e-4, 20000)
    z1 = np.exp(-1j * w)
    L = z1 * (G * (1 + z1) / (1 - (1 - 2 * G) * z1)) ** 4
    ph = np.unwrap(np.angle(L))
    i = int(np.argmax(ph <= -math.pi))
    return 1 / abs(L[i])


# the feedback, scaled per cutoff so the filter starts to sing at k = 4 (RES ~121) at every
# FREQ: without it the delay's phase made FREQ 110 sing from RES ~90
KS = [q31(min(1.0, _k_crit(G_TAB[i] / Q31) / 4)) for i in range(FC_MAX + 1)]
COMP4 = [q31((1 + 0.25 * min(res_k(k), 3.0)) * 2.0 / 4) for k in range(128)]   # < 0.875
PW = [round(pw_high(k) * 2 ** 32) for k in range(128)]
SUB_L = [q31(0.67 * k / 127) for k in range(128)]
SAW_ON, PLS_ON = (0, 0, 1, 1), (0, 1, 0, 1)


def lp_a(hz):
    return q31(1 - math.exp(-2 * math.pi * hz / FS))


HPF_A = (lp_a(150), 0, lp_a(240), lp_a(720))
SHELF = q31(10 ** (10 / 20) - 1 - 2)                    # +10 dB = x + 2.162 lp: 2 lp by shift, the rest by this
DC_A = lp_a(10)
CLIP_G = q31(0.9)
# the noise: one LCG for all four voices (Numerical Recipes' constants), its top bits
# as a Q28 sample in -1..1, times NOISE_L
NZ_A, NZ_C = 1664525, 1013904223
NOISE_L = [q31(0.5 * k / 127) for k in range(128)]


class Voice:
    def __init__(self, i):
        self.ph = (0x9E3779B9 * (i + 1)) & M32               # free-running DCOs, spread
        self.sub = 0                                       # the sub's half: 0 or 1
        self.s = [0, 0, 0, 0]
        self.y4 = 0
        self.cap = 0                                       # the coupling capacitor into the filter
        self.env, self.stage, self.g = 0, "idle", 0
        self.note, self.key, self.age = 0, None, 0


class Poly:
    def __init__(self, pv=None, seed=1):
        self.pv = list(pv or DEFAULTS)
        self.v = [Voice(i) for i in range(VOICES)]
        self.keys = [0] * KEYS
        self.clock = 0
        self.hp, self.dc = 0, 0
        self.nz = (0x2545F491 * seed) & M32

    # -- the keys -> the voices ------------------------------------------------------------
    def alloc(self):
        idle = [v for v in self.v if v.stage == "idle"]
        if idle:
            return idle[0]
        rel = [v for v in self.v if v.stage == "release"]
        if rel:
            return min(rel, key=lambda v: (v.env, self.v.index(v)))
        return min(self.v, key=lambda v: v.age)

    def take(self, keys):
        for k in range(KEYS):
            n = keys[k]
            if n == self.keys[k]:
                continue
            if self.keys[k]:
                for v in self.v:
                    if v.key == k:
                        v.key, v.stage = None, "release"
            if n:
                v = self.alloc()
                self.clock += 1
                v.key, v.note, v.age, v.stage = k, n, self.clock, "attack"     # from its current level
            self.keys[k] = n

    def step(self, keys):
        """One frame for these keys (KEYS Q8 notes, 0 = up) -> (left, right), Q28."""
        pv = self.pv
        self.take(keys)
        wv = wave(pv[SLOT["WAVE"]])
        saw_on, pls_on = SAW_ON[wv], PLS_ON[wv]
        pw, subl = PW[pv[SLOT["PWM"]]], SUB_L[pv[SLOT["SUB"]]]
        k8, comp = K8[pv[SLOT["RES"]]], COMP4[pv[SLOT["RES"]]]
        mix = [0] * FRAMES
        nzl, nzs = NOISE_L[pv[SLOT["NOISE"]]], []
        for n in range(FRAMES):                      # the noise runs whether or not a voice hears it
            self.nz = (self.nz * NZ_A + NZ_C) & M32
            nzs.append(emul((self.nz - ((self.nz >> 31) << 32)) >> 3, nzl))
        for v in self.v:
            if v.stage == "idle":
                continue
            # the envelope, once a frame
            if v.stage == "attack":
                v.env += ATK_STEP[pv[SLOT["A"]]]
                if v.env >= Q31 - 1:
                    v.env, v.stage = Q31 - 1, "decay"
            elif v.stage == "decay":
                sus = SUS_L[pv[SLOT["S"]]]
                v.env -= emul(v.env - sus, DEC_C[pv[SLOT["D"]]])
            else:
                v.env -= emul(v.env, DEC_C[pv[SLOT["R"]]])
            dg = (v.env - v.g) >> 4
            dt = inc_of(v.note)
            fi = CUT_I[pv[SLOT["FREQ"]]] + tdiv(v.note - REF_NOTE * 256, 24 * 256 // FC_STEPS) \
                + emul(ENV_I[pv[SLOT["ENV"]]], v.env)
            gi = max(0, min(FC_MAX, FC_LOW + fi))
            G, kv = G_TAB[gi], emul(k8, KS[gi])
            s = v.s
            for n in range(FRAMES):
                ph = v.ph
                x = 0
                if saw_on:
                    x += (ph >> 3) - ONE - blep(ph, dt)
                if pls_on:
                    x += (ONE if ph < pw else -ONE) + blep(ph, dt) - blep((ph - pw) & M32, dt)
                sph = (ph >> 1) | (v.sub << 31)                # the sub: the DCO's phase, an octave down
                x = x >> 1
                if subl:
                    x += emul((ONE if v.sub == 0 else -ONE) + blep(sph, dt >> 1) - blep((sph - (1 << 31)) & M32, dt >> 1), subl)
                x += nzs[n]                                    # |x| <= 1 + 0.67 + 0.5
                v.ph = (ph + dt) & M32
                if v.ph < ph:
                    v.sub ^= 1
                v.cap += emul(x - v.cap, DC_A)                 # the Juno's coupling cap: a 5% pulse is -0.9 DC
                x = x - v.cap
                u = tanh28(sat((x >> 2) - (emul(kv, v.y4) << 3)))
                for i in range(4):
                    w = emul(u - s[i], G)
                    u = w + s[i]
                    s[i] = sat(u + w)
                v.y4 = u
                v.g += dg
                mix[n] += emul(emul(u, comp), v.g)              # |u| < 1 (see FC_MAX), comp < 0.875: four voices < 3.5
            if v.stage == "release" and v.env < ENV_FLOOR:
                v.stage, v.env, v.g, v.s, v.y4, v.cap = "idle", 0, 0, [0, 0, 0, 0], 0, 0
        # after the voices: HPF, DC, the soft clip; mono
        hz = hpf(pv[SLOT["HPF"]])
        out = [0] * FRAMES
        for n in range(FRAMES):
            x = mix[n] >> 2                                  # < 0.875: the shelf (x 3.16) and the DC blocker (x 2) stay < 5.6
            if hz != 1:
                self.hp += emul(x - self.hp, HPF_A[hz])
                x = x + (self.hp << 1) + emul(self.hp, SHELF) if hz == 0 else x - self.hp
            self.dc += emul(x - self.dc, DC_A)
            x = max(-(ONE >> 1), min((ONE >> 1) - 1, x - self.dc))    # tanh(8) is 1 already: x 16 stays inside Q28
            out[n] = emul(tanh28(x << 4), CLIP_G)             # x 4 overall, a soft clip under 0.9
        return out, list(out)

    def frame(self, cv):
        """cv: FRAMES x KEYS float notes (or FRAMES notes: one key) -> two float arrays."""
        row = np.atleast_2d(np.asarray(cv, float).reshape(len(cv), -1))[0]
        keys = [round(float(n) * 256) if n > 0 else 0 for n in row] + [0] * (KEYS - len(row))
        l, r = self.step(keys[:KEYS])
        return np.array(l, float) / ONE, np.array(r, float) / ONE


def render(x, pv, changes=(), seed=1, frames=None, amp=True):
    """Key tracks x (n x KEYS, or n: one key) -> (left, right). changes: (frame, slot,
    value) at frame starts. amp is accepted for LADDER's signature; POLY has its own VCA."""
    p = Poly(pv, seed)
    frames = frames or len(x) // FRAMES
    by = {}
    for fr, sl, val in changes:
        by.setdefault(fr, []).append((sl, val))
    x = np.asarray(x, float).reshape(len(x), -1)
    xs = np.zeros((frames * FRAMES, x.shape[1])); xs[:min(len(x), len(xs))] = x[:len(xs)]
    yl, yr = np.zeros(frames * FRAMES), np.zeros(frames * FRAMES)
    for f in range(frames):
        for sl, val in by.get(f, ()):
            p.pv[sl] = val
        a, b = p.frame(xs[f * FRAMES:(f + 1) * FRAMES])
        yl[f * FRAMES:(f + 1) * FRAMES], yr[f * FRAMES:(f + 1) * FRAMES] = a, b
    return yl, yr


# ---- the gate's inputs ------------------------------------------------------------------
def chords(seq, seconds, bpm=120.0):
    """[(step, [notes], steps held)] on 16th steps -> KEYS key tracks."""
    x = np.zeros((int(seconds * FS) // FRAMES * FRAMES, KEYS))
    step = 60 / bpm / 4 * FS
    for st, ns, length in seq:
        a, b = int(st * step), int((st + length) * step)
        for k, n in enumerate(ns):
            x[a:min(b, len(x)), k] = n
    return x


def signals():
    cm7, fm7, gm = [48, 51, 55, 58], [53, 56, 60, 63], [43, 50, 55, 58]
    stabs = [(i * 4 + 2, c, 1) for i, c in enumerate([cm7, cm7, fm7, cm7, cm7, gm, cm7, fm7])]
    pad = [(0, cm7, 15.5), (16, fm7, 15.5), (32, gm, 15.5), (48, cm7, 15.5)]
    line = [(i, [n], 0.6) for i, n in enumerate([36, 48, 39, 51, 43, 55, 46, 58] * 4)]
    return {"stabs": chords(stabs, 4.2), "pad": chords(pad, 8.5), "line": chords(line, 4.2)}


def dry(x):
    """The rawest bright output for the same keys: SAW and the noise at full, filter open,
    no resonance, no envelope on the cutoff, full sustain. The gate's level baseline: the
    noise is a source, so a level it makes honestly is not a runaway."""
    pv = list(DEFAULTS)
    for k, v in (("FREQ", 127), ("RES", 0), ("ENV", 0), ("S", 127), ("SUB", 0), ("NOISE", 127)):
        pv[SLOT[k]] = v
    l, r = render(x, pv)
    return (l + r) / 2


class Engine:
    """The bench's live form: plays the key tracks in a loop. pv is shared: knob turns reach
    the next frame."""
    def __init__(self, x, pv):
        self.x, self.pos, self.p = np.asarray(x, float).reshape(len(x), -1), 0, Poly(pv)
        self.pv = self.p.pv

    def process(self, frames):
        L, R = np.empty(frames * FRAMES), np.empty(frames * FRAMES)
        for f in range(frames):
            if self.pos + FRAMES > len(self.x):
                self.pos = 0
            L[f * FRAMES:(f + 1) * FRAMES], R[f * FRAMES:(f + 1) * FRAMES] = self.p.frame(self.x[self.pos:self.pos + FRAMES])
            self.pos += FRAMES
        return L, R


def label(knob, k):
    """What the unit's screen prints for this knob value."""
    if knob == "WAVE":
        return WAVES[wave(k)]
    if knob == "HPF":
        return str(hpf(k))
    return None


if __name__ == "__main__":
    def peak_hz(y, lo, hi):
        seg = y[len(y) // 4:]
        sp = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
        f = np.fft.rfftfreq(len(seg), 1 / FS)
        m = (f >= lo) & (f <= hi)
        return f[m][np.argmax(sp[m])]

    pv = list(DEFAULTS); pv[SLOT["FREQ"]] = 127; pv[SLOT["SUB"]] = 0; pv[SLOT["S"]] = 127
    l, _ = render(chords([(0, [57], 64)], 1.0), pv)
    hz = peak_hz(l, 100, 400)
    assert abs(hz - 220) < 2, hz
    l, r = render(signals()["stabs"], DEFAULTS)
    assert np.array_equal(l, r)
    print(f"A3 -> {hz:.1f} Hz; stabs peak {abs(l).max():.2f}")
    l, _ = render(chords([(0, [48, 55, 60, 64], 4)], 3.0), DEFAULTS)
    tail = l[int(1.5 * FS):]
    assert np.abs(tail).max() < 1e-3, np.abs(tail).max()
    print("self-check ok")
