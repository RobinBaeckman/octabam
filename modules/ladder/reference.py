"""LADDER: a monophonic subtractive machine, Minimoog Model D shaped, as a float reference.

Two oscillators and noise into a 4-pole transistor-ladder low-pass with its own
contour (attack, decay, sustain), glide between held notes. The amplitude is the
Octatrack's AMP page, after the machine, as OCTA303 does; `render` stands in for
it with a 1 ms / 30 ms gate so the bench and the gate hear notes, not a drone.

INTEGER, the arithmetic the ColdFire will run (the MCF54454 has no FPU): signals
are Q28 (1.0 = 2^28), coefficients Q31, and every product is one EMAC fractional
multiply, `emul(a, b) = (a * b) >> 31`; the tables are built here once from the
documented mappings. 16-sample frames: the contour, glide and filter
coefficients at frame rate, the oscillators and the ladder per sample (OCTA303
runs its 303 voice the same way at ~200 instructions a sample,
modules/octa303/README.md). The ColdFire voice must equal this model sample for
sample (gate layer 1); the bench and the gate hear this model.

The input is a pitch track, one value per sample: the MIDI note while the gate
is held, 0 when it is not. On the unit the note comes from the trig and the
chromatic keys; here it lets the gate's renders and the specs drive notes the
way they drive a sample.

Knob names: the Model D's front panel, cut to 4 letters. The filter: Zavalishin's
zero-delay ladder (The Art of VA Filter Design, ch. 5) with a tanh on the
feedback sum, the cheap form of the transistor ladder's saturation.
"""
import math

import numpy as np

FS, FRAMES = 44100, 16

KNOBS = [
    ("TUNE", 64, "pitch, -24..+24 semitones, 64 = the played note"),
    ("CUT", 48, "filter cutoff, 20 Hz x 2^(k*10/127): 0 = 20 Hz, 48 = 275 Hz (the default), 64 = 660 Hz, 127 = 20 kHz (at C3; it follows the note by half)"),
    ("EMPH", 40, "emphasis (resonance): 0 none, 110 and up the filter sings on its own, over the oscillators"),
    ("CONT", 80, "amount of contour: how far the filter contour opens the cutoff, 5k/127 octaves (80: 3.1)"),
    ("DEC", 64, "contour decay, 2 ms x 5000^(k/127): 0.15 s at 64 (the default), 10 s at 127; also the release"),
    ("GLID", 0, "glide between held notes: 0 off, else a 1 ms x 2000^(k/127) time constant"),
    ("WAVE", 53, "both oscillators' waveform, six zones of 0..127: TRI 0-21, SHRK 22-42, SAW 43-63 (53, the default), SQR 64-85, WIDE 86-106, NARR 107-127"),
    ("DET", 76, "oscillator 2's tune, 1200 cents x ((k-64)/63)^3: 64 unison, 76 = +8 cents (the default thickness), 127 = +1 octave, 0 = -1258 cents"),
    ("MIX", 64, "oscillator 1 against 2: 0 only 1, 64 equal, 127 only 2"),
    ("NOIS", 0, "white noise into the filter, level (k/127)^2"),
    ("ATK", 0, "contour attack, 1 ms x 10000^(k/127)"),
    ("SUS", 0, "contour sustain level, k/127 of the contour amount"),
]
NAMES = [k[0] for k in KNOBS]
DEFAULTS = [k[1] for k in KNOBS]
SLOT = {n: i for i, n in enumerate(NAMES)}
WAVES = ("TRI", "SHRK", "SAW", "SQR", "WIDE", "NARR")
DRIVE, MAKEUP = 0.25, 1.6                     # into the ladder: low enough that full emphasis sings over the oscillators
DC_A = 1 - math.exp(-2 * math.pi * 10 / FS)
REF_NOTE = 48                                 # C3: where CUT means what its doc says


def semis(k):
    return max(-24, min(24, round((k - 64) * 24 / 63)))


def cutoff_hz(k):
    return 20.0 * 2 ** (k * 10 / 127)


def emph_k(k):
    return 4.6 * k / 127                      # ladder feedback; self-oscillation from k = 4 (EMPH 110)


def cont_oct(k):
    return 5.0 * k / 127


def dec_s(k):
    return 0.002 * 5000 ** (k / 127)


def atk_s(k):
    return 0.001 * 10000 ** (k / 127)


def glide_s(k):
    return 0.0 if k == 0 else 0.001 * 2000 ** (k / 127)


def wave(k):
    return min(5, k * 6 // 128)


def det_cents(k):
    return 1200 * ((k - 64) / 63) ** 3


# ---- the integer engine -----------------------------------------------------------
Q, Q31 = 28, 1 << 31
ONE = 1 << Q
M32 = 0xFFFFFFFF


def emul(a, b):
    """The EMAC's fractional multiply, truncated: (a * b) >> 31, both signed 32-bit."""
    assert -Q31 <= a < Q31 and -Q31 <= b < Q31, (a, b)
    return (a * b) >> 31


def sat(x):
    """A 32-bit store of a Q28 signal (+-8): the model asserts it never has to clip."""
    assert -Q31 <= x < Q31, x
    return x


def q31(v):
    return max(-Q31, min(Q31 - 1, round(v * Q31)))


def frame_coef(seconds):
    """Per-frame step toward the target for a one-pole with this time constant."""
    return 1.0 if seconds <= 0 else 1 - math.exp(-FRAMES / (seconds * FS))


# pitch: Q8 semitones over MIDI 0 (8.18 Hz); INC[r] is one octave's phase increments at
# 1/256 semitone, shifted up by the octave (0.39 cents: DET's 1-cent spec holds)
INC = [round(2 ** 32 * 440 * 2 ** ((r / 256 - 69) / 12) / FS) for r in range(3072)]
INC_MAX = int(0.45 * 2 ** 32)                     # the oscillators stop rising at 0.45 FS
DET_Q8 = [round(det_cents(k) * 256 / 100) for k in range(128)]
GLIDE_C = [0 if k == 0 else q31(frame_coef(glide_s(k))) for k in range(128)]
# the contour: Q31 0..1 (ONE31 = full); attack is a straight line, decay/release a one-pole
ATK_STEP = [min(Q31 - 1, round(Q31 * FRAMES / (atk_s(k) * FS))) for k in range(128)]
DEC_C = [q31(frame_coef(dec_s(k))) for k in range(128)]
SUS_L = [round((Q31 - 1) * k / 127) for k in range(128)]
# the cutoff: an index in 1/128 octave over 20 Hz, G = g/(1+g), g = tan(pi fc / FS), Q31;
# the table starts 3 octaves lower (key tracking takes CUT 0 to 7 Hz on a low note)
FC_STEPS, FC_LOW = 128, 3 * 128
FC_TOP = int(FC_STEPS * math.log2(0.45 * FS / 20))


def _G(i):
    g = math.tan(math.pi * 20 * 2 ** (i / FC_STEPS) / FS)
    return q31(g / (1 + g))


G_TAB = [_G(i - FC_LOW) for i in range(FC_LOW + FC_TOP + 1)]
CUT_I = [round(FC_STEPS * k * 10 / 127) for k in range(128)]
CONT_I = [round(FC_STEPS * cont_oct(k)) for k in range(128)]           # times the contour (Q31)
K8 = [q31(emph_k(k) / 8) for k in range(128)]                          # k / 8: k reaches 4.6
COMP4 = [q31((1 + 0.25 * min(emph_k(k), 3.0)) * 1.6 / 4) for k in range(128)]   # makeup / 4
MIX15 = [round(32768 * k / 127) for k in range(128)]
NZ = [q31((k / 127) ** 2) for k in range(128)]
DC_A31 = q31(1 - math.exp(-2 * math.pi * 10 / FS))
THIRD = 715827883                                                      # 2^31 / 3, rounded
PW = (1 << 31, round(0.3 * 2 ** 32), round(0.1 * 2 ** 32))               # SQR, WIDE, NARR
# tanh, Q28 in and out, over +-8 in 1/64 steps, interpolated
TANH_STEP = ONE >> 6
TANH = [round(math.tanh((i - 512) / 64) * ONE) for i in range(1025)]


def inc_of(p8):
    o, r = divmod(max(0, p8), 3072)
    return min(INC_MAX, INC[r] << o)


def blep(t, dt):
    """PolyBLEP correction, Q28, t = phase, dt = inc (u32 cycle fractions)."""
    if t < dt:
        q = (1 << 15) - min(1 << 15, t // ((dt >> 15) or 1))     # 1 - t/dt, Q15
        return -((q * q) >> (30 - Q))
    r = (1 << 32) - t
    if r < dt:
        q = (1 << 15) - min(1 << 15, r // ((dt >> 15) or 1))
        return (q * q) >> (30 - Q)
    return 0


def osc(ph, dt, w):
    """One oscillator's sample, Q28, at phase ph (u32)."""
    if w == 0:                                              # TRI
        return (ph >> 2) - ONE if ph < 1 << 31 else 3 * ONE - (ph >> 2)
    if w == 1:                                              # SHRK: (8/3)p - 1 for 3/4 (ph/6 as one multiply), then down
        return emul(ph >> 1, THIRD) - ONE if ph < 3 << 30 else ONE - ((ph - (3 << 30)) >> 1)
    if w == 2:                                              # SAW
        return (ph >> 3) - ONE - blep(ph, dt)
    pw = PW[w - 3]
    y = ONE if ph < pw else -ONE
    return y + blep(ph, dt) - blep((ph - pw) & M32, dt)


def tanh28(x):
    i = (x >> 22) + 512                                     # 1/64 steps over -8..8
    if i < 0:
        return TANH[0]
    if i >= 1024:
        return TANH[1024]
    return TANH[i] + emul(TANH[i + 1] - TANH[i], (x & ((1 << 22) - 1)) << 9)


def tdiv(a, b):
    """divs.l: truncates toward 0 (Python's // floors)."""
    return -((-a) // b) if a < 0 else a // b


class Voice:
    def __init__(self, pv=None, seed=1):
        self.pv = list(pv or DEFAULTS)
        self.ph1, self.ph2 = 0, round(0.37 * 2 ** 32)
        self.rng = seed & M32
        self.s = [0, 0, 0, 0]                               # the ladder's four integrators, Q28
        self.tgt, self.off = None, 0                        # the held note (Q8 semitones), the glide's distance to it (Q24)
        self.gate = False
        self.env, self.stage = 0, "idle"                    # Q31
        self.dc = 0

    def frame_int(self, cv):
        """16 samples, Q28 ints, for the pitch track cv (16 values: a note, or 0)."""
        return self.step(round(float(cv[0]) * 256) if cv[0] > 0 else 0)

    def step(self, note8):
        """One frame for a held note (Q8 semitones), or 0: the ColdFire voice's entry
        (modules/ladder/voice.s ladder_frame), sample for sample."""
        pv = self.pv
        held = note8 > 0
        if held:
            tgt = note8
            if not self.gate:
                self.stage = "attack"
            if self.tgt is None or pv[SLOT["GLID"]] == 0:
                self.off = 0
            else:                                   # a one-pole on the distance: in Q24 its tail stalls at 0.03 cents (Q8 stalled 8 cents out)
                self.off = max(-Q31, min(Q31 - 1, self.off + ((self.tgt - tgt) << 16)))
                self.off -= emul(self.off, GLIDE_C[pv[SLOT["GLID"]]])
            self.tgt = tgt
        elif self.gate:
            self.stage = "release"
        self.gate = held
        if self.stage == "attack":
            self.env += ATK_STEP[pv[SLOT["ATK"]]]
            if self.env >= Q31 - 1:
                self.env, self.stage = Q31 - 1, "decay"
        elif self.stage == "decay":
            sus = SUS_L[pv[SLOT["SUS"]]]
            self.env = sus + (self.env - sus) - emul(self.env - sus, DEC_C[pv[SLOT["DEC"]]])
        elif self.stage == "release":
            self.env -= emul(self.env, DEC_C[pv[SLOT["DEC"]]])
        p8 = (self.tgt + (self.off >> 16) if self.tgt is not None else REF_NOTE * 256) + 256 * semis(pv[SLOT["TUNE"]])
        dt1, dt2 = inc_of(p8), inc_of(p8 + DET_Q8[pv[SLOT["DET"]]])
        fi = CUT_I[pv[SLOT["CUT"]]] + tdiv(p8 - REF_NOTE * 256, 24 * 256 // FC_STEPS) \
            + emul(CONT_I[pv[SLOT["CONT"]]], self.env)
        G = G_TAB[max(0, min(FC_LOW + FC_TOP, FC_LOW + fi))]
        G2 = emul(G, G); G3 = emul(G2, G); G4 = emul(G3, G)
        k8 = K8[pv[SLOT["EMPH"]]]
        d28 = ONE + emul(k8, G4)                            # 1 + k G^4, Q28 (k/8 in Q31 = k in Q28)
        inv = ((Q31 - 1) // (d28 >> 13)) << 15              # 1 / that, Q31 (divu.l 32/32: 16 bits)
        omg = Q31 - 1 - G
        comp = COMP4[pv[SLOT["EMPH"]]]
        w = wave(pv[SLOT["WAVE"]])
        m15 = MIX15[pv[SLOT["MIX"]]]
        nz = NZ[pv[SLOT["NOIS"]]]
        s = self.s
        out = [0] * FRAMES
        for n in range(FRAMES):
            o1, o2 = osc(self.ph1, dt1, w), osc(self.ph2, dt2, w)
            self.ph1, self.ph2 = (self.ph1 + dt1) & M32, (self.ph2 + dt2) & M32
            self.rng = (self.rng * 1664525 + 1013904223) & M32
            white = (self.rng >> 3) - ONE                   # Q28, -1..1
            x = ((o1 >> 15) * (32768 - m15) + (o2 >> 15) * m15) >> 2      # DRIVE 1/4
            x = sat(x + (emul(white, nz) >> 2))
            S = emul(sat(emul(G3, s[0]) + emul(G2, s[1]) + emul(G, s[2]) + s[3]), omg)
            y4 = emul(sat(emul(G4, x) + S), inv)
            u = tanh28(sat(x - (emul(k8, y4) << 3)))
            for i in range(4):
                v = emul(u - s[i], G)
                u = v + s[i]
                s[i] = sat(u + v)
            y = emul(u, comp) << 2
            self.dc += emul(y - self.dc, DC_A31)
            out[n] = sat(y - self.dc)
        return out

    def frame(self, cv):
        return np.array(self.frame_int(cv), dtype=float) / ONE


def render(x, pv, changes=(), seed=1, frames=None, amp=True):
    """Pitch track x -> (left, right). changes: (frame, slot, value) applied at frame
    starts. amp: the AMP page's stand-in, 1 ms attack, 30 ms release on the gate."""
    v = Voice(pv, seed)
    frames = frames or len(x) // FRAMES
    by = {}
    for fr, sl, val in changes:
        by.setdefault(fr, []).append((sl, val))
    y = np.zeros(frames * FRAMES)
    xs = np.zeros(frames * FRAMES); xs[:min(len(x), len(xs))] = x[:len(xs)]
    for f in range(frames):
        for sl, val in by.get(f, ()):
            v.pv[sl] = val
        y[f * FRAMES:(f + 1) * FRAMES] = v.frame(xs[f * FRAMES:(f + 1) * FRAMES])
    if amp:
        g = (xs > 0).astype(float)
        a = np.zeros_like(g)
        up, down = 1 - math.exp(-1 / (0.001 * FS)), 1 - math.exp(-1 / (0.030 * FS))
        e = 0.0
        for i, t in enumerate(g):
            e += (t - e) * (up if t > e else down)
            a[i] = e
        y = y * a
    return y, y.copy()


# ---- the gate's inputs (bench/gate.py: a machine with signals() is a synth) ----------
def track(notes, seconds, bpm=120.0):
    """[(step, note, steps held)] on 16th steps -> a pitch track."""
    x = np.zeros(int(seconds * FS) // FRAMES * FRAMES)
    step = 60 / bpm / 4 * FS
    for st, note, length in notes:
        a, b = int(st * step), int((st + length) * step)
        x[a:min(b, len(x))] = note
    return x


def signals():
    bass = [(i, n, 0.5) for i, n in enumerate([36, 36, 48, 36, 39, 36, 43, 41] * 4)]
    lead = [(0, 60, 4.2), (4, 67, 4.2), (8, 63, 2.2), (10, 72, 6)]           # held into each other: glide
    return {"bass": track(bass, 4.2), "lead": track(lead, 4.2), "drone": track([(0, 45, 64)], 4.2)}


def dry(x):
    """The rawest bright output for the same notes: SAW, filter open, no emphasis, no
    contour. The baseline the gate's level check measures against."""
    pv = list(DEFAULTS)
    pv[SLOT["CUT"]], pv[SLOT["EMPH"]], pv[SLOT["CONT"]] = 127, 0, 0
    l, r = render(x, pv)
    return (l + r) / 2


class Engine:
    """The bench's live form: plays a pitch track in a loop, a 16-sample frame at a time
    (the AMP stand-in included). pv is shared: knob turns reach the next frame."""
    def __init__(self, x, pv):
        self.x, self.pos, self.v = x, 0, Voice(pv)
        self.pv = self.v.pv
        self.amp, self.up = 0.0, 1 - math.exp(-1 / (0.001 * FS))
        self.down = 1 - math.exp(-1 / (0.030 * FS))

    def process(self, frames):
        out = np.empty(frames * FRAMES)
        for f in range(frames):
            if self.pos + FRAMES > len(self.x):
                self.pos = 0
            cv = self.x[self.pos:self.pos + FRAMES]
            y = self.v.frame(cv)
            for i in range(FRAMES):
                t = 1.0 if cv[i] > 0 else 0.0
                self.amp += (t - self.amp) * (self.up if t > self.amp else self.down)
                y[i] *= self.amp
            out[f * FRAMES:(f + 1) * FRAMES] = y
            self.pos += FRAMES
        return out, out.copy()


def label(knob, k):
    """What the unit's screen prints for this knob value (modules/ladder/fmt.s
    ladder_fmt_*; tools/verify/verify_machine_labels.py holds the two equal)."""
    if knob == "TUNE":
        s = semis(k)
        return f"+{s}" if s > 0 else str(s)
    if knob == "WAVE":
        return WAVES[wave(k)]
    if knob == "DET":
        c = round(det_cents(k))
        return f"+{c}" if c > 0 else str(c)
    return None
