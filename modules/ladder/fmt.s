| LADDER's SRC page display formatters, fmt(buf 4(sp), value 8(sp)) like every
| stock one (docs/firmware/PARAM_PAGES.md section 7). The mappings are
| reference.py's (semis, wave, det_cents); verify_machine_labels.py calls each
| for all 128 values against reference.label.
        .text
        .global ladder_fmt_tune, ladder_fmt_wave, ladder_fmt_det
SPRINTF = 0x40013a08
S_D     = 0x400b465d                    | "%d"
S_PD    = 0x400b449f                    | "+%d"

ladder_fmt_tune:                        | round((k - 64) * 24 / 63), -24..+24
        move.l  %sp@(8),%d0
        subi.l  #64,%d0
        moveq   #24,%d1
        muls.l  %d1,%d0
        movea.l #31,%a1                 | half of 63: round half away from 0 (a1: d2 is the caller's)
        moveq   #63,%d1
        bra.s   .Lsigned

ladder_fmt_det:                         | round(1200 * (k - 64)^3 / 63^3), cents
        move.l  %sp@(8),%d0
        subi.l  #64,%d0
        move.l  %d0,%d1
        muls.l  %d0,%d1
        muls.l  %d1,%d0                 | (k - 64)^3, |.| <= 262144
        move.l  #1200,%d1
        muls.l  %d1,%d0                 | <= 314,572,800: fits
        movea.l #125023,%a1             | half of 63^3
        move.l  #250047,%d1
.Lsigned:                               | d0 / d1 rounded by a1, printed with its sign
        movea.l #S_D,%a0
        tst.l   %d0
        bmi.s   .Lneg
        add.l   %a1,%d0
        divu.l  %d1,%d0
        beq.s   .Lprint                 | rounded to 0: "0", not "+0"
        movea.l #S_PD,%a0
        bra.s   .Lprint
.Lneg:  neg.l   %d0
        add.l   %a1,%d0
        divu.l  %d1,%d0
        neg.l   %d0
.Lprint:                                | sprintf(buf, a0, d0)
        move.l  %d0,%sp@-
        move.l  %a0,%sp@-
        move.l  %sp@(12),%sp@-
        jsr     SPRINTF
        lea     %sp@(12),%sp
        rts

ladder_fmt_wave:                        | six zones of 0..127: k * 6 / 128
        move.l  %sp@(8),%d0
        moveq   #6,%d1
        mulu.l  %d1,%d0
        lsr.l   #7,%d0
        move.l  %d0,%d1
        lsl.l   #2,%d1
        add.l   %d1,%d0                 | 5 bytes a name, NUL included
        lea     names(%pc),%a0
        adda.l  %d0,%a0
        move.l  %a0,%sp@(8)             | value slot := the name (no %)
        jmp     SPRINTF                 | sprintf(buf, name)
names:  .asciz  "TRI\0"                 | 5 bytes each: reference.WAVES in order
        .asciz  "SHRK"
        .asciz  "SAW\0"
        .asciz  "SQR\0"
        .asciz  "WIDE"
        .asciz  "NARR"
        .even
