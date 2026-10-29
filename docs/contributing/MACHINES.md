# Machines: how a ColdFire machine joins the Octatrack's machine list

A track machine is a row of the track's own machine list, after stock's five
(STATIC, FLEX, THRU, NEIGHBOR, PICKUP). Choosing it on the unit, in the list or
in SRC SETUP, puts the track on it; the track's PLAYBACK and SETUP pages are
the machine's; the track's sound is the machine's. The **machine table**
(`modules/machines`, the platform module MACHINES) owns every stock site that
needs. A machine module owns none of them: it declares itself in its manifest
and the build does the rest.

```
module manifest: Machine(...)  ─┐
module manifest: Machine(...)  ─┼─> tools/remix (select) ─> MACHINES: rows, records, dispatch (remix.inc)
module manifest: Machine(...)  ─┘                            └─> owned detours, pokes, symbol refs
```

Design record: [SHARED_HOOKS.md](../proposals/SHARED_HOOKS.md) phase 6.
Confidence markers as in `docs/firmware/CHIP.md`: ✅ measured, 🟡 inferred
with a falsifier, ⬜ not looked at.

## 1. The contract

`schema.Machine` (tools/remix/schema.py), on `Module.machine`. POLY's:

```python
machine=Machine(
    name="JUNO", short="JUNO", sig="PO",
    knobs=(Knob("FREQ", 64), Knob("RES", 24), Knob("ENV", 48), Knob("A", 0), Knob("D", 72),
           Knob("S", 48), Knob("R", 48), Knob("WAVE", 112, fmt="poly_fmt_wave"), Knob("PWM", 0),
           Knob("SUB", 40), Knob("HPF", 48, fmt="poly_fmt_hpf"), Knob("NOISE", 0)),
    frame="poly_frame", state=256, notes=4),
```

| field | what the table does with it |
|---|---|
| `name`, `short` | the list's row and the page title, the page abbreviation. Fields: the title is 13 bytes at P+0x09 (12 characters and a NUL), the abbreviation 5 bytes at P+0x04 (4 and a NUL). ✅ 9 characters shown on the list and page (ANALOG BD, `verify_analog_bassdrum_ui`); 10-12 ⬜ not seen on a screen. A plain name saying what the machine is (CLAUDE rule 8): POLY shows JUNO, LADDER shows MINIMOOG / MOOG. The module key stays the module's |
| `sig` | two ASCII bytes and 1, written at `Part' + 0x3c + 30 * track` when the row is chosen. The track stays FLEX in the Part; the signature says which machine. It is saved in users' projects, so it never changes once shipped |
| `knobs` | twelve `Knob(name, default, count=128, fmt=None)`: PLAYBACK 0-5 then SETUP 6-11. Defaults on a new track, a formatter symbol or stock address (None = stock `%d`), `count=0` hides a slot |
| `frame` | a ColdFire voice, `void frame(state *, const uint8_t pv[12], const int32_t keys[notes], int32_t out[32])`: 16 samples a call, L then R, Q28; C ABI (keeps d2-d7/a2-a6 and the EMAC state). The table renders it into the track's FLEX stream |
| `state` | bytes a track for `frame`, zeroed when a track joins the machine |
| `notes` | keys the voice holds: 0 none, 1 mono, 4 a four-note chord. The table fills `keys` from the note input (section 3) |
| `render` | instead of `frame`: a whole FLEX renderer `(track, ping, start, end)` that hands every other track to `MT_NEXT`. For a machine whose sound is not a ColdFire frame (ANALOG BD's DSP voice, OCTA303's TB-303 sample tracks) |
| `record` | optional: `uint32_t record(Part', track)` returning the page record (PARAM_PAGES.md 2) for a machine whose page depends on the track. Without it the table builds one from `knobs`, a clone of the user's FLEX record |

The schema refuses a name past its field (trap-name-nul), not twelve knobs, a
default past its count, both or neither of `frame`/`render`, and `state` or
`notes` without a `frame`.

## 2. What the build generates

`modules/machines/manifest.py` reads the selection's `Machine`s:

- **rows by module key, sorted.** Row 5 is the first machine. A remix's rows
  are therefore stable when a machine is added only if its key sorts last; a
  Part stores the signature, never the row, so a saved project survives any
  reordering. ✅ `verify_machines` (AB 5, LADDER 6, OCTA303 7, POLY 8 in
  `test/machines`).
- **`table_inc`** writes `remix.inc` macros: the signatures, titles, hidden
  slots, defaults, the record per row (cloned from `FLEX_P` with the knobs'
  names and formatters patched in), and the voice rows (frame, state bytes,
  notes, state base).
- **the owned sites** (the list in `modules/machines/manifest.py`'s
  docstring): the names, the row counts and the five key handlers' cursor
  clamps (trap-machine-clamp), the drawer's row tests, the opens, the three
  commits, SETUP's editor and drawer, the Part validator, the page resolver
  and the tick, every reader of stock's PLAYBACK record table (`mt_pages`,
  trap-pb-table-neighbour), the FLEX renderer entry, and the MIDI send
  primitive when a machine takes notes.
- **`flags_inc`** gives each client `MT_CLIENT 1`, its row `MT_ROW` and the
  renderer it hands on to `MT_NEXT`. A `render` machine chains; the last
  link is stock's FLEX renderer.

Adding a machine edits its own module only. Nothing in `modules/machines`
names a machine.

## 3. Note input: a MIDI track plays the machine on its audio track

**Decision: MIDI track t's notes are the keys of the machine on audio track
t**, when that machine takes notes. Why: an audio track's trig carries one
note (its PTCH lock), so it cannot play a chord; a MIDI track's trig carries
four (NOTE, NOT2-NOT4), is recorded from the grid or live, has the
CHROMATIC keyboard, and receives MIDI note-in on its channel. All of those
leave the unit through one routine, the MIDI send primitive `0x40010bc8`
(`docs/firmware/MIDI_TRACKS.md`), note-offs at the trig's LEN included. So
one hook covers every way the unit already plays notes, and the bench's
phrase picker retires.

`notes.s` parses the sent bytes: a note-on or note-off on the channel of MIDI
track t (`Part' + 0x4e2 + 0x24 * t`, stored as channel + 1) is a key down or
up for audio track t. The first key down posts the track a START (`0x1d`
into its voice command `0x46c80354 + 4 t`, as MIDI note-in on an audio
track's channel does, MIDI.md 2); the last key up posts its release
(`0x40`). So the track's AMP opens and closes with the notes. The message
still leaves the unit.

- ✅ under Unicorn (`verify_machines`): a chord, a CC between notes, another
  channel, note-offs, the START and release posts.
- ✅ under the port, end to end (`verify_poly_port`, 29 Oct 2026): MIDI
  track 1's step-1 chord (C3, NOT2 +4, NOT3 +7) and step-3 G3 reach POLY as
  three keys, then their note-offs at LEN, then one key; the stream track 1
  sends the DSP equals `reference.py` stepped with those keys, 898 of 898
  frames, every sample, on `test/poly` and on `test/machines` (all four
  machines in the image).
- ✅ The UART capture of that run carries the chord in running status
  (`90 30 64 34 64 37 64`), yet all three keys arrive. 🟡 So the send primitive
  is given a status per message and the repeats are dropped later, on the
  way to the UART (inferred from the two observations, not traced). If a
  firmware path ever hands the primitive a running-status buffer, `notes.s`
  stops at the first data byte in status position and the chord's later
  notes are lost; the port gate fails on it.
- Compromise: the MIDI track's channel must not be one an external synth
  listens on, since its notes still go out. A MIDI track set to channel OFF
  sends nothing, so it cannot drive a machine either.

## 4. Sample access: the track's Flex slot (designed, not built)

A sample machine (GRAINER) plays the sample in the track's own Flex slot,
loaded with the unit's sample-slot UI. Measured from the disassembly, not
yet run (subagent, 29 Oct 2026):

- The track's Part FLEX slot reaches its voice at `0x800049d8 + 0xa8 t`
  (+21 the slot id, +30 the format).
- The slot's state record is `0x46c922c4 + 44 * id`: +0 format (0 24-bit
  mono, 2048 frames a block, 3 bytes a frame; 1 24-bit stereo 1024/6; 2
  16-bit mono 3072/2; 3 16-bit stereo 1536/4), +8 nonzero while loading
  (🟡), +16 length in frames, +20 a generation the voice compares at +16.
  Big-endian.
- Flex RAM is **not contiguous**: `ROWS = *(u32 *)0x80006918` (136 longs,
  the first map entry of each slot, -1 unloaded) and `MAP = *(u32
  *)0x80006914` (u16 block numbers). Frame i of slot id is at
  `0x40A955E0 + MAP[ROWS[id] + i / spb] * 6144 + (i % spb) * bpf`.
- The two pointers are double-buffered and flip during compaction, so a
  machine re-resolves them every frame and never caches an address. This
  corrects RECORDER.md's "rows 0-1 free / sample map": they are the map
  and its shadow.

So the contract grows one field, `sample=True`: the table passes the frame
call a fifth argument, a read-only view `{id, fmt, length, rows, map}`
resolved for the track that frame, and the voice reads frames through
`mt_sample_at(view, i)`. GRAINER's voice takes one contiguous sample
pointer today, so it needs that change in its voice and an adapter. Not
built in this branch; GRAINER is not yet a client.

## 5. Installed only when needed (rule 4.1)

- A remix with no machine: MACHINES is not selected. Byte-identical. ✅
- ANALOG BD alone, OCTA303 alone: each keeps its own claims, proven on
  units, and its bytes. ✅ image identical to origin/main's.
- Two or more machines, or any machine with no standalone claims (POLY,
  LADDER, GRAINER): the table installs and overrides every client claim on
  an owned span (`schema.Override`).

## 6. Gates

| gate | proves |
|---|---|
| `verify_machines` | selection and generation (ANALOG BD + OCTA303 refused without the table); every owned hook under Unicorn (names, rows, drawer, commits, the built page records inside their buffers, note input); the installed image's sites |
| `verify_analog_bassdrum_ui`, `verify_octa303_ui` | each machine's pages on a shared image, under the port. ✅ on `test/machines` (OCTA-303 on row 7 of nine), 29 Oct 2026, on the x86-64 work VM's build of the port |
| `verify_poly_voice`, `verify_ladder_voice` | each voice against its reference, bit for bit, on the emulated chip |
| `verify_poly_port` | end to end: a project's MIDI pattern (a chord included) through the firmware into the stream the track sends the DSP, bit for bit with `reference.py`. In the path: the sequencer and MIDI track, the send primitive and `notes.s`, `mt_render`'s ring and packing, `poly_frame`. Not compared: AMP, the FX, the mixer, the DSP (only checked not silent). Needs `OT_PROJECT`; SKIPs without |

## 7. Compromises

- ANALOG BD and OCTA303 keep their standalone paths beside the table, so
  each alone stays byte-identical to what units run. SHARED_HOOKS.md
  section 8 named this as the falsifier ("each would keep a direct path
  beside the registry"); it is the price of not reflashing proven bytes.
- A frame machine is rendered the way OCTA303 has rendered on units since
  v7.0: stock's FLEX renderer runs with PTCH/RATE neutral and the voice's
  positions pinned, then its samples are overwritten. The track keeps
  FLEX's stream shape and its DSP chain; the cost is stock's renderer per
  frame on top of the voice (⬜ not metered here).
- `state` is zeroed, not initialised by the machine. POLY's "no key" is -1,
  so on a zeroed state every idle voice has key 0, and slot 0's first key-up
  runs idle voices through one silent release frame. Measured equal to the
  C (the reference is stepped from the same zero state); inaudible.
- LADDER is mono (`notes=1`): a second key while one is held is ignored,
  not last-note priority.
