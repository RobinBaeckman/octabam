"""stock effects with GRAINER's screen: the grain strip in the SRC page's sample box."""

from remix.schema import Proof, Remix

REMIX = Remix(
    name="grainer",
    family="mods", proof=Proof.PORT, proof_note="the strip under the port (bench)",
    doc="stock effects with GRAINER's screen: the grain strip in the SRC page's sample box.",
    modules=("GRAINER",
             "FILTER", "EQUALIZER", "DJ EQ", "PHASER", "FLANGER",
             "CHORUS", "SPATIALIZER", "COMB FILTER", "COMPRESSOR", "LO-FI",
             "DELAY", "PLATE REV", "SPRING REV", "DARK REV"),
    fallback="NONE",
)
