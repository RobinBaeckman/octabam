| GRAINER's grain strip, drawn into the SRC page's sample box (manifest.py).
|
| The LCD surface (0x400bf10a) holds its buffer pointer at +12. A column is
| two words at buf + 8x, and the buffer counts y UP from the bottom: screen
| row y is bit 0x80000000 >> ((63 - y) & 31) of word (63 - y) >> 5, so rows
| 32..47 are bits 0..15 of the column's first word, row y = bit (y - 32)
| (measured 28 Oct 2026: the lit box reads 0xffff there, the inverted bottom
| line 0xfe000000). One column of the strip is one read-modify-write.
        .text
        .global grainer_view_hook

ROWS_LIT  = 0x00007F00                  | rows 40..46: the strip's background
EDGES     = 0x00008080                  | rows 39 and 47: lit when the box shows

grainer_view_hook:
        lea     %sp@(-24),%sp
        movem.l %d0-%d3/%a0-%a1,%sp@
        movea.l #grainer_view,%a0
        addq.l  #1,%a0@(124)            | debug: entries
        move.l  %a0@,%d0
        cmpi.l  #0x47524e56,%d0         | 'GRNV': the engine has written a frame
        bne.s   .Ldone
        movea.l 0x400bf116,%a1          | the surface's buffer
        cmpa.l  #0,%a1
        beq.s   .Ldone
        lea     %a1@(80),%a1            | column 10
        movea.l %a1,%a0                 | (a0 reloaded below)
        moveq   #47,%d1                 | the box is showing: x 10..57 lit on rows 39 and 47
.Lchk:  move.l  %a0@,%d0
        andi.l  #EDGES,%d0
        cmpi.l  #EDGES,%d0
        bne.s   .Ldone
        addq.l  #8,%a0
        subq.l  #1,%d1
        bpl.s   .Lchk
        movea.l #grainer_view+4,%a0
        addq.l  #1,%a0@(116)            | debug: draws (+120)
        move.l  %a1@,%d0                | column 10: the stock '~' icon's first column off
        ori.l   #ROWS_LIT,%d0
        move.l  %d0,%a1@
        moveq   #45,%d1                 | columns 11..56
.Lcol:  addq.l  #8,%a1
        move.l  %a1@,%d0
        ori.l   #ROWS_LIT,%d0
        moveq   #0,%d2
        move.w  %a0@+,%d2
        not.l   %d2
        and.l   %d2,%d0
        move.l  %d0,%a1@
        subq.l  #1,%d1
        bpl.s   .Lcol
.Ldone: movem.l %sp@,%d0-%d3/%a0-%a1
        lea     %sp@(24),%sp
        moveq   #1,%d0                  | the displaced: the LCD's dirty flag
        move.l  %d0,0x46c7c72c
        jmp     0x4004c6a4

| The SRC page's display formatters, fmt(buf 4(sp), value 8(sp)) like every
| stock one (docs/firmware/PARAM_PAGES.md section 7). The bench writes their
| addresses into the descriptor's formatter array A; the mappings are the
| reference's (reference.py semis, grains_max, mode).
        .global grainer_fmt_tune, grainer_fmt_amnt, grainer_fmt_mode, grainer_fmt_scan
SPRINTF = 0x40013a08
S_D     = 0x400b465d                    | "%d"
S_PD    = 0x400b449f                    | "+%d"

grainer_fmt_tune:                       | round((k - 64) * 24 / 63), -24..+24
        move.l  %sp@(8),%d0
        subi.l  #64,%d0
        moveq   #24,%d1
        muls.l  %d1,%d0
        movea.l #S_D,%a0
        tst.l   %d0
        bmi.s   .Lneg
        addi.l  #31,%d0
        moveq   #63,%d1
        divu.l  %d1,%d0
        beq.s   .Lprint                 | rounded to 0: "0", not "+0"
        movea.l #S_PD,%a0
        bra.s   .Lprint
.Lneg:  neg.l   %d0
        addi.l  #31,%d0
        moveq   #63,%d1
        divu.l  %d1,%d0
        neg.l   %d0
        bra.s   .Lprint

grainer_fmt_amnt:                       | 1 + k * 7 / 127, grains at once
        move.l  %sp@(8),%d0
        moveq   #7,%d1
        mulu.l  %d1,%d0
        moveq   #127,%d1
        divu.l  %d1,%d0
        addq.l  #1,%d0
        movea.l #S_D,%a0
.Lprint:                                | sprintf(buf, a0, d0)
        move.l  %d0,%sp@-
        move.l  %a0,%sp@-
        move.l  %sp@(12),%sp@-
        jsr     SPRINTF
        lea     %sp@(12),%sp
        rts

grainer_fmt_mode:                       | 0-42 RAND, 43-85 SYNC, 86-127 OSC
        move.l  %sp@(8),%d0
        lea     s_rand(%pc),%a0
        moveq   #43,%d1
        cmp.l   %d1,%d0
        blt.s   1f
        lea     s_sync(%pc),%a0
        moveq   #86,%d1
        cmp.l   %d1,%d0
        blt.s   1f
        lea     s_osc(%pc),%a0
1:      move.l  %a0,%sp@(8)             | value slot := the label (no %)
        jmp     SPRINTF                 | sprintf(buf, label)
grainer_fmt_scan:                       | the scan speed, as Tonverk prints it: 2 ((k - 64) / 63)^2, signed, "1.02"
        move.l  %sp@(8),%d0
        subi.l  #64,%d0
        movea.l %d0,%a1                 | the sign, kept
        muls.l  %d0,%d0
        move.l  #200,%d1
        mulu.l  %d1,%d0
        addi.l  #1984,%d0               | + 3969/2: rounds (an exact half cannot occur)
        move.l  #3969,%d1
        divu.l  %d1,%d0                 | hundredths
        move.l  %d0,%sp@-
        moveq   #100,%d1
        divu.l  %d1,%d0                 | whole
        move.l  %d0,%d1
        mulu.w  #100,%d1
        neg.l   %d1
        add.l   %sp@+,%d1               | hundredths left
        move.l  %d1,%sp@-
        move.l  %d0,%sp@-
        lea     s_none(%pc),%a0
        move.l  %a1,%d1
        bpl.s   1f
        or.l    %sp@(4),%d0
        beq.s   1f                      | "0.00", not "-0.00"
        lea     s_minus(%pc),%a0
1:      move.l  %a0,%sp@-
        pea     s_scan(%pc)
        move.l  %sp@(20),%sp@-          | buf
        jsr     SPRINTF
        lea     %sp@(20),%sp
        rts
s_scan: .asciz  "%s%d.%02d"
s_minus: .asciz "-"
s_none: .byte   0
s_rand: .asciz  "RAND"
s_sync: .asciz  "SYNC"
s_osc:  .asciz  "OSC"
        .even
