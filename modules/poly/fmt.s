| POLY's display formatters, fmt(buf 4(sp), value 8(sp)) like every stock one
| (docs/firmware/PARAM_PAGES.md section 7), as LADDER's. The mappings are
| reference.py's (wave, hpf); verify_machine_labels.py calls each for all
| 128 values against reference.label.
        .text
        .global poly_fmt_wave, poly_fmt_hpf
SPRINTF = 0x40013a08

poly_fmt_wave:                          | four zones: k >> 5
        move.l  %sp@(8),%d0
        lsr.l   #5,%d0
        lea     waves(%pc),%a0
        bra.s   .Lname
poly_fmt_hpf:                           | four positions: k >> 5
        move.l  %sp@(8),%d0
        lsr.l   #5,%d0
        lea     hpfs(%pc),%a0
.Lname:                                 | a0 + 6 d0: the name, NUL included
        move.l  %d0,%d1
        add.l   %d1,%d1
        add.l   %d0,%d1
        add.l   %d1,%d1
        adda.l  %d1,%a0
        move.l  %a0,%sp@(8)             | value slot := the name (no %)
        jmp     SPRINTF                 | sprintf(buf, name)
waves:  .asciz  "OFF\0\0"               | 6 bytes each: reference.WAVES in order
        .asciz  "PULSE"
        .asciz  "SAW\0\0"
        .asciz  "P+S\0\0"
hpfs:   .asciz  "0\0\0\0\0"
        .asciz  "1\0\0\0\0"
        .asciz  "2\0\0\0\0"
        .asciz  "3\0\0\0\0"
        .even
