"""POLY -- a four-voice Juno-106-shaped synth machine (bench/specs/poly.py, README "POLY").

fmt.s: display formatters for WAVE (OFF PULSE SAW P+S) and HPF (0-3), the
Juno's own names; the bench writes their addresses into the page
it draws. voice.s: the noise, the four voices and the HPF, one 16-sample frame per call,
bit-exact against reference.Poly.step (tables.inc is generated from
reference.py). Nothing calls it on a unit yet: that needs a machine row.
"""

from remix.schema import Gate, Kind, Linked, Module

MODULE = Module(
    name="poly",
    key="POLY",
    kind=Kind.CF_PATCH,
    doc="POLY: screen text (WAVE and HPF by name) and the ColdFire voice of a four-voice Juno-106-shaped synth, not yet called by a machine row.",
    linked=(Linked("fmt", "modules/poly/fmt.s", dram=True),
            Linked("voice", "modules/poly/voice.s", dram=True)),
    gates=(Gate("tools/verify/verify_machine_labels.py", venv=True, stage="image"),
           Gate("tools/verify/verify_poly_voice.py", venv=True, stage="image"),),
)
