# MACHINES: the machine table

The owner of every stock site a track machine's row needs: the machine list and
SRC SETUP, the commits, the Part validator, the page records, the FLEX renderer
entry and the note input. A machine module declares `schema.Machine` and claims
none of them; the build generates the rows, records and dispatch. Selected by
the build, never by a remix: when a remix carries two machines, or one without
claims of its own.

The contract, the generation, the note input and the Flex slot design:
[docs/contributing/MACHINES.md](../../docs/contributing/MACHINES.md).

- `manifest.py`: the owned sites, selection, the generated `remix.inc` macros.
- `table.s`: the rows, names, commits, SETUP, validator, records, tick.
- `voice.s`: a `frame` machine rendered into the track's FLEX stream.
- `notes.s`: MIDI track t's notes as the keys of the machine on audio track t.

## Where it has run

Not flashed. Under Unicorn (`verify_machines`) and the ColdFire port.
