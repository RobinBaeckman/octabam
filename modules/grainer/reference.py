"""GRAINER's reference: a granular sample machine, Tonverk GRAINER's knobs.

The machine plays grains from the track's sample, not from live input, so a
grain can start anywhere in the sample (an FX2 slot reaches back ~0.36 s).

INTEGER, the way the ColdFire runs it (no FPU; the EMAC multiplies fractions):
samples are 24-bit and widened to Q27, every value-times-fraction is the
EMAC's emul(a, b) = (a * b) >> 31, a grain's read point is 16.16 and moves by
a fixed 16.16 step, and every curve is a table. Grains are scheduled once per
16-sample frame into ten fixed slots (the lowest free one), every grain's
settings are fixed when it starts, reads are 2-tap linear, and the window is
the stock timestretch crossfade table (TS_TABLE, 512 entries, at 0x80004000
on the unit). The ColdFire voice is to equal this sample for sample.

    render(sample, pv, changes=(), seed=1) -> (left, right)

sample: float mono, the track's sample (rounded to 24 bits here). pv: 12 knob
values, slot order below. changes: (frame, slot, value) applied at that
frame's start (a knob moving).
"""
import math

import numpy as np

FS, FRAMES = 44100, 16
Q31 = 1 << 31
OUT_Q = 27                          # Q27 out: nine grains at full gain cannot wrap 32 bits

# slot: (name, default, what it does). Page 1 = SRC (A-F), page 2 = SRC SETUP.
KNOBS = [
    ("TUNE", 64, "grain pitch, -24..+24 semitones, 64 = original"),
    ("POS", 0, "where in the sample the grains start, 0 = start, 127 = end"),
    ("SCAN", 109, "how the read point moves: 64 = stopped (grains keep playing around it, spread by SPRD), above forward, below backward, 109 = the sample's own speed (the default: a fresh sample plays through), 127 = 2x"),
    ("SIZE", 64, "grain length, 10 ms .. 2 s (64 = 141 ms)"),
    ("DENS", 96, "RAND: chance a grain plays; SYNC: tempo division; OSC: overlap (0 full, 127 back to back)"),
    ("SPRD", 16, "random offset from POS: 0 none, 127 anywhere in the sample"),
    ("AMNT", 91, "grains at once, 1..8"),
    ("DIR", 0, "chance a grain plays backwards, 0 never, 127 always"),
    ("FADE", 127, "how much of each grain is fade, 0 = 2 ms edges, 127 = all fade"),
    ("SHAPE", 64, "fade balance: 0 fast in/slow out, 64 even, 127 slow in/fast out"),
    ("PAN", 48, "random pan per grain, 0 = centre"),
    ("MODE", 0, "how grains are timed: 0-42 RAND, 43-85 SYNC, 86-127 OSC"),
]
NAMES = [k[0] for k in KNOBS]
DEFAULTS = [k[1] for k in KNOBS]
SLOT = {n: i for i, n in enumerate(NAMES) if n}
SLOTS = 10                          # grains alive at once: AMNT's 8, and one ending as the next starts (asserted)

# Stock timestretch's crossfade table, T[i] = round(2^31 sin^2(pi/2 (i+1)/513)),
# rising 0 -> 1, T[i] + T[511-i] = 2^31 (DSP.md). The window reads it by index.
TS_TABLE = [round(2.0 ** 31 * math.sin(math.pi / 2 * (i + 1) / 513) ** 2) for i in range(512)]
EDGE = int(0.002 * FS)              # shortest fade: FADE 0 is a 2 ms edge, not a click


class Rng:
    """xorshift32: one shift-xor triple per draw, cheap on the ColdFire."""
    def __init__(self, seed):
        self.s = seed & 0xFFFFFFFF or 1

    def u32(self):
        s = self.s
        s ^= (s << 13) & 0xFFFFFFFF
        s ^= s >> 17
        s ^= (s << 5) & 0xFFFFFFFF
        self.s = s
        return s


def emul(a, b):
    """The EMAC's fractional multiply, truncated: (a * b) >> 31, both signed 32-bit."""
    assert -Q31 <= a < Q31 and -Q31 <= b < Q31, (a, b)
    return (a * b) >> 31


def q31(v):
    return max(-Q31, min(Q31 - 1, round(v * Q31)))


def semis(k):
    return max(-24, min(24, round((k - 64) * 24 / 63)))


def size_samples(k):
    return int(0.010 * FS * 200 ** (k / 127))


def grains_max(k):
    return 1 + k * 7 // 127


def scan_speed(k):
    d = (k - 64) / 63
    return math.copysign(2 * d * d, d)


RAND, SYNC, OSC = 0, 1, 2
# SYNC's divisions of a 4-beat bar, DENS 0..127 in 8 steps: 1, 1/2 .. 1/128, a shift each.
# Inferred, not from Elektron's manual: it names the mode (grains on a tempo division of the
# BPM) but not the list. Elektron's stutter recipe uses DENS ~16, a slow division.
SYNC_DIV = tuple(1 / 2 ** i for i in range(8))


def mode(k):
    return RAND if k < 43 else SYNC if k < 86 else OSC


def sync_div(dens):
    return SYNC_DIV[dens * len(SYNC_DIV) // 128]


def bar_samples(bpm):
    """Samples in a 4-beat bar: the SYNC clock's base (the unit's tempo, given to the voice)."""
    return round(240 * FS / bpm)


# the tables the ColdFire reads
SIZE_N = [size_samples(k) for k in range(128)]
GMAX = [grains_max(k) for k in range(128)]
MODE_OF = [mode(k) for k in range(128)]
SYNC_SH = [dens * 8 // 128 for dens in range(128)]                      # SYNC: the bar >> this
CH = [(k << 31) // 127 for k in range(128)]                             # chance k/127: (u >> 1) < CH[k]
RATE = [round(2 ** (semis(k) / 12) * 65536) for k in range(128)]       # 16.16 read step
SCAN_Q = [round(scan_speed(k) * FRAMES * 65536) for k in range(128)]    # 16.16 samples a frame
POS_Q = [q31(k / 127) for k in range(128)]
SPRD_Q = [q31(k / 127) for k in range(128)]
PAN_Q = [round(k / 127 * 32768) for k in range(128)]                    # Q15, 127 = 1.0
GAIN16 = [q31(1 / math.sqrt(max(16, i) / 16)) for i in range(129)]      # 1/sqrt(overlap), overlap in 1/16
SQ = [round(math.sqrt(i / 128) * 2 ** 30) for i in range(257)]          # sqrt(0..2), Q30: the pan law


def clock(pv, size, spb):
    """Samples between grain ATTEMPTS, and the chance an attempt plays (num/127).
    RAND: AMNT attempts per grain length at random times, each plays with
          chance DENS/127 (Tonverk manual: DENS is the probability).
    SYNC: one attempt per tempo division, always plays.
    OSC:  regular, overlap set by DENS: 0 = full overlap, 64 ~ 50%, 127 = back to back."""
    m, d, n = MODE_OF[pv[SLOT["MODE"]]], pv[SLOT["DENS"]], GMAX[pv[SLOT["AMNT"]]]
    if m == SYNC:
        return spb >> SYNC_SH[d], 127
    if m == OSC:
        return max(size // n, size * d // 127), 127
    return size // n, d


def overlap16(pv, size, spb):
    """Grains sounding at once on average, in 1/16 (sets the gain, 1/sqrt of it)."""
    every, chance = clock(pv, size, spb)
    n = GMAX[pv[SLOT["AMNT"]]]
    return max(16, min(16 * n, 16 * size * chance // (127 * max(every, FRAMES))))


def window_shape(n, fade, shap):
    """A grain of n samples: its rise a and fall d (on TS_TABLE), flat between."""
    f = min(n, max(2 * EDGE, n * fade // 127))
    a = max(EDGE, min(f - EDGE, f * shap // 127))
    return a, max(EDGE, f - a)


def window_at(k, n, a, d):
    """The window at sample k of n, Q31: what the ColdFire computes per sample."""
    if k >= n - d:
        return TS_TABLE[511 - (((k - (n - d)) * ((512 << 22) // d)) >> 22)]
    if k < a:
        return TS_TABLE[(k * ((512 << 22) // a)) >> 22]
    return Q31 - 1


class Grain:
    __slots__ = ("start", "end", "base", "rate", "gl", "gr", "a", "d")

    def __init__(self, start, size, base, rate, gl, gr, a, d):
        self.start, self.end, self.base, self.rate = start, start + size, base, rate
        self.gl, self.gr, self.a, self.d = gl, gr, a, d


class Engine:
    """One GRAINER voice, streamed: process() renders the next frames with the knobs
    as they are now. A grain's settings are fixed when it starts; its audio is
    computed from its own start, so streaming in any block size gives the same
    samples as one long render (checked in __main__)."""

    def __init__(self, sample, pv=None, seed=1, bpm=120.0):
        x = np.asarray(sample, float)
        self.x = np.clip(np.round(x * (1 << 23)), -(1 << 23), (1 << 23) - 1).astype(np.int64)   # 24-bit
        self.n = len(self.x)
        assert self.n >= 64, "a sample shorter than 4 frames"
        self.pv = list(pv or DEFAULTS)
        self.rng, self.spb = Rng(seed), bar_samples(bpm)
        self.t = 0                   # samples rendered since the trig
        self.head = 0                # scanned offset from POS, 16.16 in [0, n << 16)
        self.next_at = 0
        self.slots = [None] * SLOTS
        self.live = []               # grains with audio left to render

    def _spawn(self, start, size, ov16):
        pv, rng, n = self.pv, self.rng, self.n
        pos = emul(n - 1, POS_Q[pv[SLOT["POS"]]]) + (self.head >> 16)
        pos -= n if pos >= n else 0
        # the spread stays inside the sample, reflected off its edges: POS 0 with spread
        # must not reach the end (a wrap), nor pile grains on sample 0 (a clamp: the gate
        # measured DC). SCAN wraps, per the Tonverk manual; the spread's edge is undocumented.
        u = rng.u32()
        pos += emul(emul(n, SPRD_Q[pv[SLOT["SPRD"]]]), u - Q31) >> 1
        pos = -pos if pos < 0 else 2 * (n - 1) - pos if pos > n - 1 else pos
        assert 0 <= pos < n, pos
        rate = RATE[pv[SLOT["TUNE"]]]
        if rng.u32() >> 1 < CH[pv[SLOT["DIR"]]]:
            rate = -rate
        p = (PAN_Q[pv[SLOT["PAN"]]] * ((rng.u32() >> 16) - 32768)) >> 15
        g = GAIN16[min(ov16, 128)]
        a, d = window_shape(size, pv[SLOT["FADE"]], pv[SLOT["SHAPE"]])
        gr = Grain(start, size, (pos << 16) | (self.head & 0xFFFF), rate,
                   emul(g, SQ[(32768 - p) >> 8]), emul(g, SQ[(32768 + p) >> 8]), a, d)
        i = self.slots.index(None)                      # ValueError = more than SLOTS alive
        self.slots[i] = gr
        self.live.append(gr)

    def schedule(self):
        """One frame's grain starts (and the scan's move), as the ColdFire's frame does."""
        pv, t = self.pv, self.t
        size = SIZE_N[pv[SLOT["SIZE"]]]
        nmax = GMAX[pv[SLOT["AMNT"]]]
        m = MODE_OF[pv[SLOT["MODE"]]]
        every, chance = clock(pv, size, self.spb)
        ov16 = overlap16(pv, size, self.spb)
        while self.next_at < t + FRAMES:
            start = max(self.next_at, t)
            # a grain still sounding AT THE NEW ONE'S START holds a slot; counted at the
            # frame's start instead, back-to-back grains of a length not a multiple of 16
            # samples were skipped every other time (sweep_dens_osc/sweep_dir, 28 Oct 2026)
            ends = [g.end for g in self.slots if g]
            if sum(e > start for e in ends) >= nmax:
                if m == RAND:
                    self.next_at = max(self.next_at, min(ends))   # waits for the first grain to end
                    break
            elif self.rng.u32() >> 1 < CH[chance]:
                self._spawn(start, size, ov16)
            if m == RAND:
                self.next_at += max(FRAMES, (every >> 1) + emul(every, self.rng.u32() >> 1))
            else:                                # SYNC and OSC keep their grid; a full voice skips a beat
                self.next_at += max(FRAMES, every)
        h = self.head + SCAN_Q[pv[SLOT["SCAN"]]]
        self.head = h % (self.n << 16)
        self.t = t + FRAMES
        self.slots = [g if g and g.end > self.t else None for g in self.slots]

    def process(self, frames, changes=()):
        """frames x 16 samples -> (L, R) floats. changes: (frame offset, slot, value)."""
        n = frames * FRAMES
        t0 = self.t
        pv, ch, ci = self.pv, sorted(changes), 0
        for fr in range(frames):
            while ci < len(ch) and ch[ci][0] <= fr:
                pv[ch[ci][1]] = ch[ci][2]; ci += 1
            self.schedule()
        L, R = self.render_grains(t0, n)
        return L / (1 << OUT_Q), R / (1 << OUT_Q)

    def render_grains(self, t0, n):
        """Q27 ints for samples t0 .. t0+n of every live grain (vectorised; the
        ColdFire walks the same arithmetic a sample at a time)."""
        L, R = np.zeros(n, np.int64), np.zeros(n, np.int64)
        x, ns = self.x, self.n
        for g in self.live:
            lo, hi = max(g.start, t0), min(g.end, t0 + n)
            if hi <= lo:
                continue
            k = np.arange(lo - g.start, hi - g.start, dtype=np.int64)
            P = g.base + g.rate * k
            i0 = (P >> 16) % ns
            f = P & 0xFFFF
            x0, x1 = x[i0] << 4, x[(i0 + 1) % ns] << 4
            y = x0 + (((x1 - x0) * (f << 15)) >> 31)
            size = g.end - g.start
            w = np.full(len(k), Q31 - 1, np.int64)
            rise = k < g.a
            w[rise] = np.asarray(TS_TABLE)[(k[rise] * ((512 << 22) // g.a)) >> 22]
            fall = k >= size - g.d
            w[fall] = np.asarray(TS_TABLE)[511 - (((k[fall] - (size - g.d)) * ((512 << 22) // g.d)) >> 22)]
            y = (y * w) >> 31
            L[lo - t0:hi - t0] += ((y * g.gl) >> 31) << 1
            R[lo - t0:hi - t0] += ((y * g.gr) >> 31) << 1
        self.live = [g for g in self.live if g.end > t0 + n]
        return L, R

    def where(self):
        """Bench view: the scan point and each sounding grain's read point, as fractions of the sample."""
        n = self.n
        base = (emul(n - 1, POS_Q[self.pv[SLOT["POS"]]]) + (self.head >> 16)) % n / n
        return base, [(((g.base + g.rate * (self.t - g.start)) >> 16) % n) / n for g in self.live]


def render(sample, pv, changes=(), seed=1, frames=None, bpm=120.0):
    """The whole render at once: the gate's form."""
    e = Engine(sample, pv, seed, bpm)
    return e.process(frames or len(sample) // FRAMES, changes)


def label(knob, k):
    """What the unit's screen prints for this knob value (modules/grainer/view.s
    grainer_fmt_*; tools/verify/verify_machine_labels.py holds the two equal)."""
    if knob == "TUNE":
        s = semis(k)
        return f"+{s}" if s > 0 else str(s)
    if knob == "SCAN":                      # a speed, as Tonverk prints it ("Set SCAN to 0.25")
        h = round(abs(scan_speed(k)) * 100)
        return ("-" if k < 64 and h else "") + f"{h // 100}.{h % 100:02d}"
    if knob == "AMNT":
        return str(grains_max(k))
    if knob == "MODE":
        return ("RAND", "SYNC", "OSC")[mode(k)]
    return None


if __name__ == "__main__":
    # self-check: the table matches DSP.md's two stated properties, and a steady sine stays in tune
    assert TS_TABLE[-1] == round(2 ** 31 * math.sin(math.pi / 2 * 512 / 513) ** 2)
    assert all(TS_TABLE[i] + TS_TABLE[511 - i] == 2 ** 31 for i in range(512)), "T[i] + T[511-i] = 2^31"
    # the vectorised window is window_at, sample for sample
    for n_, fd, sh in ((441, 0, 0), (6000, 127, 64), (88200, 60, 127), (500, 127, 0)):
        a_, d_ = window_shape(n_, fd, sh)
        k_ = np.arange(n_, dtype=np.int64)
        w_ = np.full(n_, Q31 - 1, np.int64)
        w_[k_ < a_] = np.asarray(TS_TABLE)[(k_[k_ < a_] * ((512 << 22) // a_)) >> 22]
        fl = k_ >= n_ - d_
        w_[fl] = np.asarray(TS_TABLE)[511 - (((k_[fl] - (n_ - d_)) * ((512 << 22) // d_)) >> 22)]
        assert [window_at(int(j), n_, a_, d_) for j in k_] == w_.tolist(), (n_, fd, sh)
    s = 0.5 * np.sin(2 * np.pi * 440 * np.arange(FS * 2) / FS)
    v = list(DEFAULTS); v[SLOT["SPRD"]] = 0; v[SLOT["AMNT"]] = 0   # one grain at a time: overlapping copies of a pure tone interfere
    l, r = render(s, v)
    seg = l[FS // 2: FS + FS // 2]
    # the energy's centre near 440, not the tallest bin: one grain at a time modulates the
    # tone, and the sidebands ~3 Hz either side outgrow the carrier's bin (443 Hz in float too)
    sp = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2
    fr = np.fft.rfftfreq(len(seg), 1 / FS)
    band = (fr > 380) & (fr < 500)
    f = float((fr[band] * sp[band]).sum() / sp[band].sum())
    assert abs(f - 440) < 1, f
    sp = np.abs(np.fft.rfft(render(s, v[:SLOT["TUNE"]] + [76] + v[SLOT["TUNE"] + 1:])[0][FS // 2: FS + FS // 2] * np.hanning(FS))) ** 2
    band = (fr > 580) & (fr < 740)
    f = float((fr[band] * sp[band]).sum() / sp[band].sum())
    assert abs(f - 440 * 2 ** (semis(76) / 12)) < 1.5, f          # +5 semitones
    # streaming in odd block sizes, with a knob moving, gives the same samples as one render
    ch = [(300, SLOT["SIZE"], 30), (900, SLOT["TUNE"], 80)]
    whole = render(s, DEFAULTS, ch, frames=2000)
    e, parts, done = Engine(s, DEFAULTS), [], 0
    for blk in (1, 7, 64, 3, 500, 1425):
        parts.append(e.process(blk, [(f - done, sl, v) for f, sl, v in ch if done <= f < done + blk]))
        done += blk
    for c in (0, 1):
        assert np.array_equal(np.concatenate([q[c] for q in parts]), whole[c]), "streamed != whole"
    # every knob at its ends never needs an eleventh slot nor leaves the sample
    for i in range(len(DEFAULTS)):
        for val in (0, 127):
            v = list(DEFAULTS); v[i] = val
            render(s[:FS], v, frames=FS // FRAMES)
    print("reference self-check ok")
