"""LADDER -- a Minimoog-shaped mono synth machine (bench/specs/ladder.py, README "LADDER").

Two units are firmware. fmt.s: display formatters for TUNE (semitones), WAVE
(the Model D's six names) and DET (cents); the bench writes their addresses
into the page it draws. voice.s: the voice, one 16-sample frame per call,
bit-exact against reference.Voice.step (tables.inc is generated from
reference.py). Nothing calls the voice on a unit yet: that needs a machine row.
"""

from remix.schema import Gate, Kind, Linked, Module

MODULE = Module(
    name="ladder",
    key="LADDER",
    kind=Kind.CF_PATCH,
    doc="LADDER: screen text (TUNE in semitones, WAVE by name, DET in cents) and the ColdFire voice, not yet called by a machine row.",
    linked=(Linked("fmt", "modules/ladder/fmt.s", dram=True),
            Linked("voice", "modules/ladder/voice.s", dram=True)),
    gates=(Gate("tools/verify/verify_machine_labels.py", venv=True, stage="image"),
           Gate("tools/verify/verify_ladder_voice.py", venv=True, stage="image"),),
)
