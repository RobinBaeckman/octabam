#!/usr/bin/env python3
"""Writes pextprobe.asm: the rung blocks are the same code at different addresses.

    python3 modules/pextprobe/gen_pextprobe.py        # rewrites modules/pextprobe/pextprobe.asm
"""
import pathlib

BASE = 0x1FE0                                            # spare on both payloads (A's code ends 0x1fdf, B's 0x1d9f)
LOW = [BASE, 0x2000, 0x2100, 0x2400, 0x2800, 0x3000, 0x3800]   # rung 0 is the control at the base
WINDOW = [0x30100, 0x35900, 0x36300, 0x36800, 0x37000, 0x37800, 0x37E00]
PATTERN, SENTINEL = 0x123456, 0x5A5A5A
NRUNG = 7
OMR_BITS = 0x600080                                      # MS (bit 7), MSW1:MSW0 (bits 22:21) = 1,1,1: Fig 3-3, 16K program / 36K X / 40K Y
OMR_P = [0x2000, 0x3000, 0x3FE0]                         # P rungs after the switch (the last one executes a routine)
OMR_Y = [0x9FE0, 0xA000, 0xBFE0]                         # Y rungs: a control below the 40K line, then two above it

head = '''; ---------------------------------------------------------------------------
; PEXT PROBE -- where can a DSP core keep code besides its stock P memory?
; (modules/pextprobe/README.md: what it proves, how to run it, how to read it.
; This file is written by gen_pextprobe.py: the rungs are the same code at
; different addresses.)
;
; Insert contract: frames in place at x:(r0) / x:(r0+n0), knobs from r6,
; state in this instance's r7 block. No bus, no buffers.
;
; GO is a select: 0 OFF (the idle signature), 1 LOW, 2 WINDOW, 3 OMR. Seven rungs,
; one every 64 frames after 64 idle ones.
;
; LOW  rung 0 is a CONTROL at the spare base P:0x1fe0 (known real: write a
;      pattern, read it back; if that is not REAL the P store does not work and
;      nothing else here means anything). Rungs 1..6 are P:0x2000, 0x2100,
;      0x2400, 0x2800, 0x3000, 0x3800. P:0x2000..0x2148 ran CHORUS on the unit.
;      A rung reads its address and the address 0x2000 below it first: equal
;      and non-zero is a wrap onto live code (ALIAS) and nothing is written;
;      otherwise it writes PATTERN, reads it back (REAL, or ABSENT), and puts
;      the old word back.
;      Codes: 1 REAL, 2 ALIAS, 3 ABSENT.
; WINDOW  seven addresses in the shared window (the words the bus remix leaves
;      free in payload A's half: 0x30048..0x307ff, 0x35800..0x35fff,
;      0x36200..0x37eff). A rung writes PATTERN and reads it back; if that
;      holds it writes a three-word routine (move #$a5a5a5,x0 / rts), calls it
;      and reads x0, then zeroes the three words.
;      Codes: 1 read/write only (the routine returned the wrong x0), 2 read/
;      write and execute, 3 read/write failed. A call that freezes the core
;      leaves its rung index in the last frame. Run one core at a time: both
;      cores' instances use the same words.
;
; OMR  rung 0 sets OMR bits 7 and 22:21 (MS, MSW1, MSW0: CHIP.md Fig 3-3, 16K
;      program, 36K X, 40K Y) and reads OMR back: code 1 if the bits stuck, 3 if
;      not. Rungs 1..3 are P:0x2000, 0x3000 and 0x3fe0: write PATTERN, read it
;      back; the last also writes a routine, calls it and reads x0 (codes as
;      WINDOW). Rungs 4..6 are Y:0x9fe0 (a control below the 40K line), Y:0xa000
;      and Y:0xbfe0 (above it): write PATTERN, read it back, put the word back
;      (1 REAL, 3 ABSENT). OMR is put back when the ladder finishes, when GO
;      leaves OMR or goes OFF. Run it with no reverb on the second FX2 slot of
;      the core: Y:0xa000..0xbfff is that slot's top half.
;
; ---- what each frame carries (read by modules/pextprobe/decode.py) -----------
; Thirty-two bits, one per sample slot: L sample j = bit j, R sample j = bit
; 16 + j; a one is +0.5 (0x400000), a zero -0.5 (0xc00000). Only the sign is
; read, so any gain on the track leaves it intact.
;   L bits 0..13   the mask: rung m's code in bits 2m, 2m+1
;   L bits 14..15  the rung index k, low two bits   (k = 7: ladder finished)
;   R bit 0        k, bit 2
;   R bits 1..2    GO, the select
;   R bit 3        parity of the frame counter
;   R bits 8..15   0xa5, the frame marker
; ---- r7 slots ---------------------------------------------------------------
;   $10 k, the next rung   $11 frames until it runs   $12 the mask
;   $13 the frame counter  $14 GO   $15 the L word   $16 the R word
;   $17 the word a rung found   $18 OMR before the OMR ladder   $19 1 while OMR is changed
; ---------------------------------------------------------------------------

init:
        clr     a
        move    a,x:(r7+$10)
        move    a,x:(r7+$12)
        move    a,x:(r7+$13)
        move    a,x:(r7+$14)
        move    a,x:(r7+$17)
        move    a,x:(r7+$18)
        move    a,x:(r7+$19)
        move    #>64,x0
        move    x0,x:(r7+$11)            ; 64 frames of idle signature before the first rung
        rts

proc:
        move    #$1,n0
        move    #>$ffffff,m5             ; the rungs are read at (r5) and written at (r1), linear
        move    #>$ffffff,m1
        move    x:(r7+$13),a
        add     #>$1,a
        move    a1,x:(r7+$13)
        move    x:(r6+$0),a              ; GO, slot 0: the value in bits 22..16
        and     #>$7f0000,a
        asr     #$10,a,a
        move    a1,x:(r7+$14)
        cmp     #>$3,a
        beq     px_kp
        bsr     px_omrback               ; GO is not OMR: put OMR back if the OMR ladder changed it
px_kp:
        move    x:(r7+$14),a
        tst     a
        bne     px_go
        clr     a                        ; GO off: the ladder starts over at the next GO
        move    a,x:(r7+$10)
        move    a,x:(r7+$12)
        move    #>64,x0
        move    x0,x:(r7+$11)
        bra     px_pub
px_go:
        move    x:(r7+$10),a
        cmp     #>$7,a
        blt     px_run
        bsr     px_omrback               ; finished: OMR back
        bra     px_pub
px_run:
        move    x:(r7+$11),a
        sub     #>$1,a
        move    a1,x:(r7+$11)
        bne     px_pub
        move    #>64,x0
        move    x0,x:(r7+$11)            ; 64 frames between rungs
        move    x:(r7+$14),a
        cmp     #>$2,a
        beq     px_win
        cmp     #>$3,a
        beq     px_omd
        move    x:(r7+$10),a
        tst     a
        beq     pxl0
'''
for k in range(1, NRUNG):
    head += f"        cmp     #>${k:x},a\n        beq     pxl{k}\n"
head += "        bra     px_pub\npx_win:\n        move    x:(r7+$10),a\n        tst     a\n        beq     pxw0\n"
for k in range(1, NRUNG):
    head += f"        cmp     #>${k:x},a\n        beq     pxw{k}\n"
head += "        bra     px_pub\npx_omd:\n        move    x:(r7+$10),a\n        tst     a\n        beq     pxo0\n"
for k in range(1, NRUNG):
    head += f"        cmp     #>${k:x},a\n        beq     pxo{k}\n"
head += "        bra     px_pub\n\n"

def done_block(k, label_prefix):
    return f'''{label_prefix}d{k}:
        move    x:(r7+$12),a
        or      x0,a
        move    a1,x:(r7+$12)
        move    x:(r7+$10),a
        add     #>$1,a
        move    a1,x:(r7+$10)
        bra     px_pub

'''

def readback(addr_reg_setup, cmp_reg="x0"):
    return ""

body = ""
for k, a in enumerate(LOW):
    if k == 0:
        body += f'''; ---- LOW rung 0: the control at P:0x{a:04x} -------------------------------------
pxl0:
        move    #>${PATTERN:x},x0
        move    #>${a:x},r1
        move    x0,p:(r1)
        move    #>${a:x},r5
        move    p:(r5),a
        move    a1,x1
        move    x1,a                     ; A2-clean before the compare
        cmp     x0,a
        bne     pxlb0
        clr     a
        move    a,x0
        move    x0,p:(r1)                ; the spare word back to zero
        move    #>$1,x0
        bra     pxld0
pxlb0:
        move    #>$3,x0
'''
        body += done_block(0, "pxl")
        continue
    body += f'''; ---- LOW rung {k}: P:0x{a:04x} --------------------------------------------------------
pxl{k}:
        move    #>${a:x},r5
        move    p:(r5),a
        move    a1,x0
        move    x0,x:(r7+$17)            ; the word there now
        move    #>${a - 0x2000:x},r5
        move    p:(r5),a
        move    a1,x1
        move    x1,a
        cmp     x0,a
        bne     pxln{k}
        tst     a
        bne     pxla{k}                  ; equal and non-zero: a wrap onto live code
pxln{k}:
        move    #>${PATTERN:x},x0
        move    #>${a:x},r1
        move    x0,p:(r1)
        move    #>${a:x},r5
        move    p:(r5),a
        move    a1,x1
        move    x1,a
        cmp     x0,a
        bne     pxlb{k}
        move    x:(r7+$17),x0
        move    x0,p:(r1)                ; the old word back
        move    #>${1 << (2 * k):x},x0
        bra     pxld{k}
pxla{k}:
        move    #>${2 << (2 * k):x},x0
        bra     pxld{k}
pxlb{k}:
        move    #>${3 << (2 * k):x},x0
'''
    body += done_block(k, "pxl")

for k, a in enumerate(WINDOW):
    body += f'''; ---- WINDOW rung {k}: P:0x{a:05x} -------------------------------------------------------
pxw{k}:
        move    #>${PATTERN:x},x0
        move    #>${a:x},r1
        move    x0,p:(r1)
        move    #>${a:x},r5
        move    p:(r5),a
        move    a1,x1
        move    x1,a
        cmp     x0,a
        bne     pxwb{k}
        move    #>$44f400,x0             ; move #>$a5a5a5,x0
        move    #>${a:x},r1
        move    x0,p:(r1)+
        move    #>$a5a5a5,x0
        move    x0,p:(r1)+
        move    #>$00000c,x0             ; rts
        move    x0,p:(r1)
        clr     a
        move    a,x0
        move    #>${a:x},r5
        jsr     (r5)
        move    x0,a
        move    a1,x1
        move    x1,a
        move    #>$a5a5a5,x0
        cmp     x0,a
        bne     pxwe{k}
        move    #>${2 << (2 * k):x},x0
        bra     pxwz{k}
pxwe{k}:
        move    #>${1 << (2 * k):x},x0
        bra     pxwz{k}
pxwb{k}:
        move    #>${3 << (2 * k):x},x0
        bra     pxwd{k}
pxwz{k}:
        move    x0,y1                    ; the code, while the three words are zeroed
        clr     a
        move    a,x0
        move    #>${a:x},r1
        move    x0,p:(r1)+
        move    x0,p:(r1)+
        move    x0,p:(r1)
        move    y1,x0
'''
    body += done_block(k, "pxw")

omr = f'''; ---- OMR rung 0: set MS, MSW1, MSW0 ------------------------------------------
pxo0:
        move    omr,x0
        move    x0,x:(r7+$18)
        move    x0,a
        or      #>${OMR_BITS:x},a
        move    a1,x0
        move    x0,omr
        move    #>$1,x0
        move    x0,x:(r7+$19)            ; OMR is changed: px_omrback puts it back
        move    omr,x0
        move    x0,a
        and     #>${OMR_BITS:x},a
        cmp     #>${OMR_BITS:x},a
        bne     pxob0
        move    #>$1,x0
        bra     pxod0
pxob0:
        move    #>$3,x0
'''
omr += done_block(0, "pxo")
for i, a in enumerate(OMR_P):
    k = 1 + i
    ex = i == len(OMR_P) - 1
    omr += f'''; ---- OMR rung {k}: P:0x{a:04x} ---------------------------------------------------------
pxo{k}:
        move    #>${PATTERN:x},x0
        move    #>${a:x},r1
        move    p:(r1),a
        move    a1,x:(r7+$17)            ; the word there now
        move    x0,p:(r1)
        move    #>${a:x},r5
        move    p:(r5),a
        move    a1,x1
        move    x1,a
        cmp     x0,a
        bne     pxob{k}
'''
    if ex:
        omr += f'''        move    #>$44f400,x0             ; move #>$a5a5a5,x0
        move    #>${a:x},r1
        move    x0,p:(r1)+
        move    #>$a5a5a5,x0
        move    x0,p:(r1)+
        move    #>$00000c,x0             ; rts
        move    x0,p:(r1)
        clr     a
        move    a,x0
        move    #>${a:x},r5
        jsr     (r5)
        move    x0,a
        move    a1,x1
        move    x1,a
        move    #>$a5a5a5,x0
        cmp     x0,a
        bne     pxoe{k}
        move    #>${2 << (2 * k):x},x0
        bra     pxoz{k}
pxoe{k}:
        move    #>${1 << (2 * k):x},x0
pxoz{k}:
        move    x0,y1                    ; the code, while the three words are zeroed
        clr     a
        move    a,x0
        move    #>${a:x},r1
        move    x0,p:(r1)+
        move    x0,p:(r1)+
        move    x0,p:(r1)
        move    y1,x0
        bra     pxod{k}
'''
    else:
        omr += f'''        move    x:(r7+$17),x0
        move    x0,p:(r1)                ; the old word back
        move    #>${1 << (2 * k):x},x0
        bra     pxod{k}
'''
    omr += f"pxob{k}:\n        move    #>${3 << (2 * k):x},x0\n" + done_block(k, "pxo")
for i, a in enumerate(OMR_Y):
    k = 1 + len(OMR_P) + i
    omr += f'''; ---- OMR rung {k}: Y:0x{a:04x} ---------------------------------------------------------
pxo{k}:
        move    #>${a:x},r1
        move    y:(r1),a
        move    a1,x:(r7+$17)            ; the word there now
        move    #>${PATTERN:x},x0
        move    x0,y:(r1)
        move    y:(r1),a
        move    a1,x1
        move    x1,a
        cmp     x0,a
        bne     pxob{k}
        move    x:(r7+$17),x0
        move    x0,y:(r1)                ; the old word back
        move    #>${1 << (2 * k):x},x0
        bra     pxod{k}
pxob{k}:
        move    #>${3 << (2 * k):x},x0
''' + done_block(k, "pxo")
omr += '''; ---- OMR back, if the ladder changed it ----------------------------------------
px_omrback:
        move    x:(r7+$19),a
        tst     a
        beq     px_omrx
        move    x:(r7+$18),x0
        move    x0,omr
        clr     a
        move    a,x:(r7+$19)
px_omrx:
        rts

'''

pub = '''; ---- publish: the 32 bits into the frame --------------------------------------
px_pub:
; L word = mask + (k & 3) << 14
        move    x:(r7+$10),a
        and     #>$3,a
        asl     #$e,a,a
        move    x:(r7+$12),x0
        add     x0,a
        move    a1,x:(r7+$15)
; R word = k >> 2 + GO << 1 + parity << 3 + 0xa500
        move    x:(r7+$10),a
        asr     #$2,a,a
        move    x:(r7+$14),b
        and     #>$3,b
        asl     #$1,b,b
        add     b,a
        move    x:(r7+$13),b
        and     #>$1,b
        asl     #$3,b,b
        add     b,a
        add     #>$a500,a
        move    a1,x:(r7+$16)
        do      n7,>pxfin                ; 16 on the unit
        move    x:(r7+$15),a
        and     #>$1,a
        move    #>$c00000,b
        move    #>$400000,x1
        tne     x1,b
        move    b,x:(r0)
        move    x:(r7+$16),a
        and     #>$1,a
        move    #>$c00000,b
        tne     x1,b
        move    b,x:(r0+n0)
        move    x:(r7+$15),a
        asr     #$1,a,a
        move    a1,x:(r7+$15)
        move    x:(r7+$16),a
        asr     #$1,a,a
        move    a1,x:(r7+$16)
        move    (r0)+n0
        move    (r0)+n0
pxfin:
        rts
'''
out = pathlib.Path(__file__).with_name("pextprobe.asm")
out.write_text(head + body + omr + pub)
print(f"{out} written")
