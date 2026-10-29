"""POLY -- a four-voice Juno-106-shaped synth machine (bench/specs/poly.py, README "POLY").

fmt.s: display formatters for WAVE (OFF PULSE SAW P+S) and HPF (0-3), the
Juno's own names; the bench writes their addresses into the page
it draws. voice.s: the noise, the four voices and the HPF, one 16-sample frame per call,
bit-exact against reference.Poly.step (tables.inc is generated from
reference.py). Nothing calls it on a unit yet: that needs a machine row.
"""

from remix.schema import Gate, Kind, Knob, Linked, Machine, Module

MODULE = Module(
    name="poly",
    key="POLY",
    kind=Kind.CF_PATCH,
    doc="POLY: screen text (WAVE and HPF by name) and the ColdFire voice of a four-voice Juno-106-shaped synth, a row of the machine table.",
    linked=(Linked("fmt", "modules/poly/fmt.s", dram=True),
            Linked("voice", "modules/poly/voice.s", dram=True)),
    # a row of the machine table (modules/machines): four keys, a chord from its MIDI track
    # (NOTE NOT2 NOT3 NOT4); poly_frame is the table's frame call as it stands. state: the
    # struct verify_poly_voice lays out, 8 longs and four voices of 14.
    machine=Machine(
        name="JUNO", short="JUNO", sig="PO",
        knobs=(Knob("FREQ", 64), Knob("RES", 24), Knob("ENV", 48), Knob("A", 0), Knob("D", 72),
               Knob("S", 48), Knob("R", 48), Knob("WAVE", 112, fmt="poly_fmt_wave"), Knob("PWM", 0),
               Knob("SUB", 40), Knob("HPF", 48, fmt="poly_fmt_hpf"), Knob("NOISE", 0)),
        frame="poly_frame", state=256, notes=4),
    gates=(Gate("tools/verify/verify_machine_labels.py", venv=True, stage="image"),
           Gate("tools/verify/verify_poly_voice.py", venv=True, stage="image"),
           Gate("tools/verify/verify_poly_port.py", venv=True, stage="image"),),
)
