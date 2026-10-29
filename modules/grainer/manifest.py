"""GRAINER -- a granular sample machine with Tonverk GRAINER's knobs.

So far only its screen is firmware: the grain strip in the SRC page's sample
box. The sound is still the float reference (reference.py), run by the bench.

The strip: the sample box (screen x 10..57, y 32..47, lit) is drawn by
0x4004c0a8, which stock re-runs on a 5-tick UI timer from the first SRC page
draw on (registered at 0x4004e8c6; read in objdump, 28 Oct 2026). Every path
through it ends at 0x4004c69c (`moveq #1,d0; move.l d0,0x46c7c72c`, the LCD's
dirty flag), where this module's hook copies 46 columns of dark pixels from
`grainer_view` into the box's lower half (y 39..47). The engine writes those
columns: the sample's envelope, each sounding grain inverted, the scan point
a notch. The hook draws only when the block's magic is set and the box is
showing: rows 39 and 47 lit across x 10..57 (the SETUP list and other screens
fail that test). Inferred, not measured: the 5-tick rate; that no other
screen lights those two rows; the track (any audio track's SRC page draws it).
"""

from remix.schema import Detour, DramRegion, Gate, Kind, Linked, Module

MODULE = Module(
    name="grainer",
    key="GRAINER",
    kind=Kind.CF_PATCH,
    doc="GRAINER's screen (a live grain strip in the SRC page's sample box) and its ColdFire voice, not yet called by a machine row.",
    linked=(Linked("view", "modules/grainer/view.s", dram=True),
            Linked("voice", "modules/grainer/voice.s", dram=True)),
    detours=(
        Detour(0x4004c69c, bytes.fromhex("700123c046c7c72c"), "view", "grainer_view_hook",
               "the sample box drawer's last block: the strip over the box stock just filled",
               kind="jmp", pad_to=8),
    ),
    # +0 magic 'GRNV' (written last by the engine: DRAM is not cleared at boot)
    # +4 46 x u16: column x = 11 + i, bit (y - 32) set = pixel (x, y) dark, y 39..47
    dram_regions=(DramRegion("grainer_view", 128),),
    # the SRC page's text (grainer_fmt_*, against reference.label), the strip hook, and the
    # voice bit-exact against reference.py (bench/gate.py's layers 1-2 for this machine)
    gates=(Gate("tools/verify/verify_machine_labels.py", venv=True, stage="image"),
           Gate("tools/verify/verify_grainer_screen.py", venv=True, stage="image"),
           Gate("tools/verify/verify_grainer_voice.py", venv=True, stage="image")),
)
