"""Every machine on the machine table: ANALOG BD, LADDER, OCTA-303, POLY (rows 5-8)."""

from remix.schema import Proof, Remix

REMIX = Remix(
    name="machines",
    family="mods", proof=Proof.PORT,
    proof_note="verify_machines; each machine's UI gate on this image; verify_poly_port",
    doc="Every machine on the machine table: ANALOG BD, LADDER, OCTA-303, POLY on rows 5-8 of the track's machine list.",
    # SPRING REV out: ANALOG BD's DSP voices sit in its words (as analog-bassdrum)
    modules=("ANALOG BD", "OCTA303", "POLY", "LADDER",
             "FILTER", "EQUALIZER", "DJ EQ", "PHASER", "FLANGER",
             "CHORUS", "SPATIALIZER", "COMB FILTER", "COMPRESSOR", "LO-FI",
             "DELAY", "PLATE REV", "DARK REV"),
    fallback="NONE",
)
