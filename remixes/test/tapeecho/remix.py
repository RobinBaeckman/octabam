"""tapeecho -- Tape Echo, alone.

Tape Echo runs on the ColdFire in the stock per-track delay rings and owns
no DSP tape buffer. It is an FX2 effect of its own, on id 0x1f.
This minimal remix contains the CPU engine in isolation. Stock DELAY remains
available for the verifier's patched-firmware baseline comparison.
"""

from remix.schema import Proof, Remix

REMIX = Remix(
    name="tapeecho",
    family="effects", proof=Proof.CHECK, proof_note="Before window placement and an id of its own (the module on a stock effect's id, the stock effects around it harvested): " "the author's unit (OCTACLID4): six instances; a seventh freezes it, open",
    doc="Tape Echo, alone.",
    modules=("TAPE ECHO",),
    window_auto=True,
    ids={"TAPE ECHO": 0x1f},   # cpu.c tests this id (TE_FX_ID)
    fallback="NONE",
)
