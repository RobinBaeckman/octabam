"""stock effects with POLY's voice."""

from remix.schema import Proof, Remix

REMIX = Remix(
    name="poly",
    family="mods", proof=Proof.PORT, proof_note="the voice under the port (verify_poly_voice)",
    doc="stock effects with POLY's voice.",
    modules=("POLY",
             "FILTER", "EQUALIZER", "DJ EQ", "PHASER", "FLANGER",
             "CHORUS", "SPATIALIZER", "COMB FILTER", "COMPRESSOR", "LO-FI",
             "DELAY", "PLATE REV", "SPRING REV", "DARK REV"),
    fallback="NONE",
)
