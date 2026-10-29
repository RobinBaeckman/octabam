"""stock effects with LADDER's screen text."""

from remix.schema import Proof, Remix

REMIX = Remix(
    name="ladder",
    family="mods", proof=Proof.PORT, proof_note="the labels under the port (bench)",
    doc="stock effects with LADDER's screen text.",
    modules=("LADDER",
             "FILTER", "EQUALIZER", "DJ EQ", "PHASER", "FLANGER",
             "CHORUS", "SPATIALIZER", "COMB FILTER", "COMPRESSOR", "LO-FI",
             "DELAY", "PLATE REV", "SPRING REV", "DARK REV"),
    fallback="NONE",
)
