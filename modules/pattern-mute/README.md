# `pattern-mute` -- PATTERN MUTE

Two mute layers, as on the Digitakt II (manual OS 1.17, section 8.5.3):

| layer | applies | saved |
|---|---|---|
| GLOBAL | every pattern | with the project (`TRACK_MUTE_MASK`, `MIDI_TRACK_MUTE_MASK` in `project.work`), and in the battery SRAM mirror |
| PATTERN | the pattern it was set in | in the pattern record, so a pattern copy carries it |

A track is muted when either layer mutes it. Double-press FUNC to choose the layer the next mute edit changes (toast `GLOBAL MUTE` / `PATTERN MUTE`). The edit is whichever stock path makes it: FUNC+track key, the MIXER trig keys, MIDI. The layer starts as GLOBAL at power-up. The stock FUNC press still runs on every press.

## How it works

Stock keeps one mute state per project: bits 8-15 of `0x80000008` (audio tracks 1-8) and of `0x8000000c` (MIDI tracks 1-8), a set bit = muted. Every stock writer of those words is followed by a store to a battery SRAM mirror (`0x100b14d4`, `0x100b14d8`). Those 30 stores are replaced by `pm_mirror_a` / `pm_mirror_m`:

1. read the word stock just wrote (N);
2. the mute bits that differ from the effective word published last go to the layer being edited;
3. the word is republished as GLOBAL OR PATTERN, so MUTE MODE, the LEDs, the MIXER page and MIDI read the effective state without change;
4. the mirror receives N with the GLOBAL layer in its mute bits.

| site | what | hook |
|---|---|---|
| 22 audio + 8 MIDI mirror stores | listed in `manifest.py`; `0x4000fe6c` / `0x4000fe82` clamp the mirror at power-up and are not hooked | `pm_mirror_a`, `pm_mirror_m` |
| `0x40089020`, `0x4008908c` | the project writer's loads of the mute bytes | `pm_save_a`, `pm_save_m` return the GLOBAL layer |
| `0x40062142` | the UI-side pattern commit, after a pattern change and after a project load | `pm_pat_commit` loads the PATTERN layer |
| `0x400bfc12`, `0x400c01f6` | FUNC's press record in the MKI and MKII key tables | `pm_func_press`; two presses within 300 ms of the free-run timer DTCN3 (`0xfc07c00c`, 132 MHz) flip the layer |

**Storage.** Bit 0 of byte 40 of audio track record k of a pattern's file chunk is audio track k+1; bit 1 is MIDI track k+1. In RAM the byte is at `bank + pattern * 0x8ed8 + 31 + 2330 * k`. An edit in the PATTERN layer writes RAM and the current bank's CS1 copy (`0x1001614e`) and sets the bank-edited flags as stock's Part paste does.

## Measured (stock 1.40C under the port, `OCTABAM89_setgate`)

- Byte 40 is zero in all 2,048 audio track records of the project. A SAVE PROJECT round trip returns it unchanged in all 128 records of the bank saved; offsets 95, 2150 and 2200 of the same records are rewritten, and so are the pattern chunk tail bytes +5, +7, +8.
- The current bank's CS1 pattern copy at `0x1001614e` equals the RAM bank byte for byte.
- A lone FUNC tap and a double FUNC tap change no mute word and no LED row on stock. FUNC+Tn toggles bit 8+n-1 per press.
- FUNC's press handler is called with edge 1 on each press (stack: return, code `0x2d`, edge); the stock double-press filter (`0x40040250`, edge 3) does not run for FUNC.
- Project load writes the mute words from `TRACK_MUTE_MASK` and `MIDI_TRACK_MUTE_MASK` (`0x40088022`..`0x40088196`).

## Gate

`tools/verify/verify_pattern_mute.py` (port, one load of the project, forked scenarios; 9 checks, all pass 20 Oct 2026; with the window set to 0 it fails 8): GLOBAL edit, layer flip, PATTERN edit (word = GLOBAL OR PATTERN, mirror keeps GLOBAL, record and CS1 copy hold the bit, bank marked edited), switching to another pattern and back, the MIDI word, and SAVE PROJECT (bank file holds the PATTERN bit, `TRACK_MUTE_MASK` stays 127). `make check REMIX=pattern-mute` and `REMIX=pattern-mute-modes` (beside MUTE_MODES) pass.

## Inferred, not measured

- A set bit = muted: the frame builder's solo path (`0x40004e0a`) silences a track whose mute bit is set, and the test project's `TRACK_MUTE_MASK=127`. The port has no audio path.
- A restore of the words by `memcpy` (`0x40020898`) is taken as a GLOBAL change at the next pattern commit.

## Not done

- The layer is not remembered across power-up.
- Key LEDs do not show the layer or blink for a muted track that has trigs.
- An edit in one layer cannot unmute a track the other layer mutes.
