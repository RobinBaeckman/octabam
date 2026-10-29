"""LADDER -- a Minimoog-shaped mono synth machine (bench/specs/ladder.py, README "LADDER").

Two units are firmware. fmt.s: display formatters for TUNE (semitones), WAVE
(the Model D's six names) and DET (cents); the bench writes their addresses
into the page it draws. voice.s: the voice, one 16-sample frame per call,
bit-exact against reference.Voice.step (tables.inc is generated from
reference.py). Nothing calls the voice on a unit yet: that needs a machine row.
"""

from remix.schema import Gate, Kind, Knob, Linked, Machine, Module

MODULE = Module(
    name="ladder",
    key="LADDER",
    kind=Kind.CF_PATCH,
    doc="LADDER: screen text (TUNE in semitones, WAVE by name, DET in cents) and the ColdFire voice, a row of the machine table.",
    linked=(Linked("fmt", "modules/ladder/fmt.s", dram=True),
            Linked("voice", "modules/ladder/voice.s", dram=True),
            Linked("play", "modules/ladder/play.s", dram=True)),
    # a row of the machine table (modules/machines): one key, from its MIDI track
    machine=Machine(
        name="MINIMOOG", short="MOOG", sig="LD",
        knobs=(Knob("TUNE", 64, fmt="ladder_fmt_tune"), Knob("CUT", 48), Knob("EMPH", 40), Knob("CONT", 80),
               Knob("DEC", 64), Knob("GLID", 0), Knob("WAVE", 53, fmt="ladder_fmt_wave"),
               Knob("DET", 76, fmt="ladder_fmt_det"), Knob("MIX", 64), Knob("NOIS", 0), Knob("ATK", 0),
               Knob("SUS", 0)),
        frame="ladder_play", state=56, notes=1),
    gates=(Gate("tools/verify/verify_machine_labels.py", venv=True, stage="image"),
           Gate("tools/verify/verify_ladder_voice.py", venv=True, stage="image"),),
)
