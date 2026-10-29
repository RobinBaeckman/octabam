| MACHINES -- the machine table: the one owner of every stock site a machine row needs.
| modules/machines/manifest.py says what each site is and why the table owns it;
| docs/contributing/MACHINES.md says how a machine joins.
|
| remix.inc (generated from each module's schema.Machine) gives:
|   MT_N            the machines, rows 5 .. 4 + MT_N of the track's machine list
|   MT_FRAMES       1 when one of them is a ColdFire voice (a `frame`)
|   MT_NOTES        1 when one of them takes notes
|   MT_RENDER_NEXT  the FLEX renderer after the table's: the first `render`
|                   machine's, or stock's 0x40004008
|   mt_sig_words    .short 'A'<<8|'B', ... one a machine, in row order
|   mt_title_longs  .long each machine's name
|   mt_strings      the names
|   mt_hidden_bytes .byte each machine's hidden SETUP slots (bit k = slot 6 + k)
|   mt_record_longs .long each machine's record(Part', track)
|   mt_defaults     .byte twelve a machine: a new track's PLAYBACK then SETUP
|   mt_voice_longs  .long frame, state bytes, notes, state base: a machine
|   mt_built        the records the table builds from the knobs, and their thunks
| A track on machine i is FLEX (Part' + 0x22 + track = 1) signed with
| machine i's two bytes and 1 at Part' + 0x3c + 30 * track; its row is 5 + i.
        .text
        .include "remix.inc"

        .set    SIG_OFF,        0x3c            | Part' + 0x3c + 30 * track (NEIGHBOR's PLAYBACK bytes)
        .set    PART_OFF,       0x8ed80         | the bank blob's Part 0
        .set    PART_SIZE,      6322
        .set    BANK_PTR,       0x46c82456
        .set    PART_IDX,       0x100b14cf
        .set    UI_TRACK,       0x100b14cc
        .set    SRAM_PART,      0x100a4ece      | Part 0's shadow
        .set    SRC_CURSOR,     0x460d5c30      | SRC SETUP's selected row
        .set    PAGE2_GAP,      0x1b0           | SETUP bytes - PLAYBACK bytes (0x1da - 0x2a)
        .set    STOCK_DEFS,     0x400d320c      | FLEX_P + 0x5e: FLEX's twelve defaults
        .set    FLEX_P,         0x400d31ae      | the stock FLEX PLAYBACK record (P form)
        .set    REC_LEN,        0x192
        .set    CURVALS,        0x80000810      | the live lane, 72 bytes a track
        .set    CV_STRIDE,      72
        .set    LANE_SETUP,     0x20
        .set    MC_LIST,        0x460e7386      | the machine list: +0 the top row, +8 the cursor, +16 the count
        .set    STOCK_RENDER,   0x40004008

        .global mt_type, mt_sig, mt_curpart, mt_pages
        .global mt_name, mt_src_names, mt_name_a, mt_name_b, mt_setup_row, mt_setup_open
        .global mt_chooser_open, mt_tick, mt_main_commit, mt_src_commit, mt_src_commit2
        .global mt_setup_edit6, mt_setup_draw6, mt_validate, mt_resolve, mt_mc_name, mt_mc_box
        .global mt_render

| ---- mt_curpart: a0 = the current part's Part', d1 = 1; d1 = 0 when no bank is loaded (a0 junk).
mt_curpart:
        move.l  BANK_PTR,%d1
        cmp.l   #0x40000000,%d1
        bcs     .Lcp_no
        move.l  %d1,%a0
        adda.l  #PART_OFF,%a0
        mvz.b   PART_IDX,%d1
        and.l   #3,%d1
        move.l  %d0,-(%sp)
        move.l  #PART_SIZE,%d0
        muls.l  %d0,%d1
        add.l   %d1,%a0
        move.l  (%sp)+,%d0
        moveq   #1,%d1
        rts
.Lcp_no:
        moveq   #0,%d1
        rts

| ---- mt_sig: a0 = Part', d0 = track -> d0 = 1 + the machine the track is on, else 0 (flags set).
|      Clobbers d1.  (OCTA303's o3_sig, one signature per machine.)
mt_sig:
        lea     -8(%sp),%sp
        movem.l %d2/%a1,(%sp)
        moveq   #7,%d1
        cmp.l   %d1,%d0
        bhi     .Lsg_no
        moveq   #0,%d1
        move.b  0x22(%a0,%d0.l),%d1
        subq.l  #1,%d1                  | FLEX
        bne     .Lsg_no
        moveq   #30,%d1
        muls.l  %d0,%d1
        move.l  %a0,%a1
        add.l   %d1,%a1
        moveq   #0,%d1
        move.b  SIG_OFF+2(%a1),%d1
        subq.l  #1,%d1
        bne     .Lsg_no
        move.b  SIG_OFF(%a1),%d1        | d1 = the two signature bytes
        lsl.l   #8,%d1
        move.b  SIG_OFF+1(%a1),%d1
        lea     mt_sigs,%a1
        moveq   #0,%d0
.Lsg_l:
        addq.l  #1,%d0
        mvz.w   (%a1)+,%d2
        cmp.l   %d2,%d1
        beq     .Lsg_x
        moveq   #MT_N,%d2
        cmp.l   %d2,%d0
        blt     .Lsg_l
.Lsg_no:
        moveq   #0,%d0
.Lsg_x:
        movem.l (%sp),%d2/%a1
        lea     8(%sp),%sp
        tst.l   %d0
        rts

| ---- mt_type: d0 = a machine byte, a0 = where it was read -> d0 = the machine's row when the byte is
|      the current part's machine byte of a signed track, else d0 unchanged.  Keeps every other register.
mt_type:
        lea     -12(%sp),%sp
        movem.l %d1/%a0-%a1,(%sp)
        moveq   #1,%d1
        cmp.l   %d1,%d0
        bne     .Lty_x
        move.l  %a0,%a1
        bsr     mt_curpart
        tst.l   %d1
        beq     .Lty_1
        move.l  %a1,%d1
        sub.l   %a0,%d1
        sub.l   #0x22,%d1               | the track, if a1 is a machine byte
        cmp.l   #7,%d1
        bhi     .Lty_1
        move.l  %d1,%d0
        bsr     mt_sig
        beq     .Lty_1
        addq.l  #4,%d0                  | 1 + i -> row 5 + i
        bra     .Lty_x
.Lty_1:
        moveq   #1,%d0
.Lty_x:
        movem.l (%sp),%d1/%a0-%a1
        lea     12(%sp),%sp
        rts

| ---- the list's names -------------------------------------------------------------------------
| mt_name -- 0x400334d8 (`move.l d2,-(sp); move.l 8(sp),d1`): name(row) -> d0.
mt_name:
        move.l  4(%sp),%d0
        subq.l  #5,%d0
        moveq   #MT_N,%d1
        cmp.l   %d1,%d0
        bcc     .Lnm_stock
        lea     mt_titles,%a0
        move.l  (%a0,%d0.l*4),%d0
        rts
.Lnm_stock:
        move.l  %d2,-(%sp)
        move.l  8(%sp),%d1
        jmp     0x400334de

| mt_src_names -- the lea at 0x4003c928: SRC SETUP's names, stock's five rows then the machines'.
        .align  4
mt_src_names:
        .long   0x400b3eac, 0x400b3e98, 0x400b7c67, 0x400b5413, 0x400b7a63
mt_titles:
        mt_title_longs

| mt_name_a / mt_name_b -- 0x4003d718 / 0x4004c36a (`lea 0x400a78c8,a0`; then d1 = name[d0]).
mt_name_a:
        bsr     mt_name_pick
        jmp     0x4003d722
mt_name_b:
        bsr     mt_name_pick
        jmp     0x4004c374
mt_name_pick:
        bsr     mt_type
        lea     mt_src_names,%a0
        move.l  (%a0,%d0.l*4),%d1
        rts

| ---- rows: highlights, opens ------------------------------------------------------------------
| mt_setup_row -- 0x4003c980 (`mvs.b (a0),d0; lea 24(sp),sp`): the row SRC SETUP highlights.
mt_setup_row:
        mvs.b   (%a0),%d0
        lea     24(%sp),%sp
        bsr     mt_type
        jmp     0x4003c986

| mt_setup_open -- 0x400585dc (`move.b (a0),d3; mvs.b d3,d4; pea 0x400bb704`).
mt_setup_open:
        move.b  (%a0),%d3
        move.l  %d0,-(%sp)
        mvs.b   %d3,%d0
        bsr     mt_type
        move.l  %d0,%d3
        move.l  (%sp)+,%d0
        mvs.b   %d3,%d4
        pea     0x400bb704
        jmp     0x400585e6

| mt_chooser_open -- 0x40078886 (`mvs.b (a0),d0; move.l d0,-(sp); pea 0x460e7386`).
mt_chooser_open:
        mvs.b   (%a0),%d0
        bsr     mt_type
        move.l  %d0,-(%sp)
        pea     MC_LIST
        jmp     0x40078890

| The list scrolls (it has more rows than the six on screen). The drawer's loop
| (0x4007864c..0x400787b2) keeps d2 the screen row, a2 its y, d3 the name formatter, d4 the
| surface, d7 the text drawer; stock draws and boxes row d2, right only while the list never
| scrolls.  d0, d1, a0, a1 are scratch at both sites.  (HOOKS's machine_rows drawer, moved here.)
| mt_mc_name -- 0x40078678 (`moveq #4,d0; cmp.l d2,d0; blt.s`): row top + d2's name, then 0x400786a2.
mt_mc_name:
        move.l  (MC_LIST).l,%d0
        add.l   %d2,%d0
        cmp.l   (MC_LIST+16).l,%d0
        bge.s   1f
        move.l  %d0,-(%sp)
        movea.l %d3,%a0
        jsr     (%a0)
        move.l  %d0,-(%sp)
        moveq   #-1,%d1
        move.l  %d1,-(%sp)
        pea     1(%a2)
        pea     0x5.w
        move.l  %d4,-(%sp)
        pea     (0x400ba876).l
        movea.l %d7,%a1
        jsr     (%a1)
        lea     28(%sp),%sp
1:      jmp     (0x400786a2).l
| mt_mc_box -- 0x400786c8, a0 the UI track's machine byte: the box on screen row d2 when that
| track's row is top + d2.
mt_mc_box:
        mvs.b   (%a0),%d0
        bsr     mt_type
        move.l  (MC_LIST).l,%d1
        add.l   %d2,%d1
        cmp.l   %d1,%d0
        bne.s   1f
        cmp.l   (MC_LIST+16).l,%d1
        bge.s   1f
        jmp     (0x400786d4).l
1:      jmp     (0x400786fc).l

| ---- the page records ---------------------------------------------------------------------------
| mt_pages: the PLAYBACK records by row, in place of stock's seven at 0x400d5f38 (whose rows 5
| and 6 are NEIGHBOR's and whose eighth word is the FX1 table's neighbour): the table points
| every reader of stock's at this one (manifest PB_LEAS).  Rows 5.. are written by mt_tick.
        .align  4
mt_pages:
        .long   0x400d301c, 0x400d31ae, 0x400d3340, 0x400d34d2, 0x400d3664
        .rept   MT_N
        .long   0x400d34d2
        .endr

| mt_record: d0 = machine index, a0 = Part', d1 = track -> d0 = its record (P).  C ABI.
mt_record:
        move.l  %d1,-(%sp)
        move.l  %a0,-(%sp)
        lea     mt_records,%a0
        move.l  (%a0,%d0.l*4),%a0
        jsr     (%a0)
        addq.l  #8,%sp
        rts

| mt_tick -- 0x4005221e (`jsr 0x4005213c; jsr 0x4007e940`): each machine's record for the UI
| track into its row of mt_pages (the SETUP editor and drawer read it by row).  d0, d1, a0, a1
| are free at 0x40052228.
mt_tick:
        jsr     0x4005213c
        jsr     0x4007e940
        bsr     mt_curpart
        tst.l   %d1
        beq     .Ltk_x
        lea     -12(%sp),%sp
        movem.l %d2/%a2-%a3,(%sp)
        move.l  %a0,%a2
        moveq   #0,%d2
.Ltk_l:
        move.l  %d2,%d0
        move.l  %a2,%a0
        mvz.b   UI_TRACK,%d1
        and.l   #7,%d1
        bsr     mt_record
        lea     mt_pages+20,%a3
        move.l  %d0,(%a3,%d2.l*4)
        addq.l  #1,%d2
        moveq   #MT_N,%d0
        cmp.l   %d0,%d2
        blt     .Ltk_l
        movem.l (%sp),%d2/%a2-%a3
        lea     12(%sp),%sp
.Ltk_x:
        jmp     0x40052228

| mt_resolve -- 0x40031e74 (`mvs.b d5,d0; lea 0x400d5f38,a0; bra.s 0x40031ece`), the page resolver's
| PLAYBACK case: a0 = the track's machine byte (Part' + 0x22 + d3), d3 = the track.  A machine's
| track gets its record; every other one stock's lookup at 0x40031ece (OCTA303's o3_page, for its
| TB303* sample tracks, sits there).  d0, d1, a0, a1 are scratch past 0x40031ed6.
mt_resolve:
        mvs.b   %d5,%d0
        bsr     mt_type
        subq.l  #5,%d0
        bmi     .Lrs_stock
        move.l  %d3,%d1
        suba.l  %d3,%a0
        suba.l  #0x22,%a0               | Part'
        bsr     mt_record
        jmp     0x40031ed6
.Lrs_stock:
        addq.l  #5,%d0
        lea     mt_pages,%a0
        jmp     0x40031ece

| ---- signing: the commits ------------------------------------------------------------------------
| mt_sigwrite: a0 = Part' (in the bank blob), d0 = track, d1 = 1 + the machine to sign it with, or 0
| to unsign, in the Part and its shadow.  Signing a copy not already on that machine writes the
| machine's twelve defaults into its FLEX PLAYBACK and SETUP bytes; unsigning clears a machine's
| signature (any machine's), nothing else.  A signed track of the current part gets its twelve
| bytes into the live lane too.  Keeps every register.  (OCTA303's o3_sigwrite, for any machine.)
mt_sigwrite:
        lea     -24(%sp),%sp
        movem.l %d0-%d3/%a0-%a1,(%sp)
        move.l  %d1,%d3
        moveq   #30,%d2
        muls.l  %d2,%d0
        move.l  %a0,%a1
        add.l   %d0,%a1
        lea     SIG_OFF(%a1),%a1
        bsr     .Lsw_one
        move.l  %a1,%d2                 | the shadow: Part' - BANK - PART_OFF + SRAM_PART
        sub.l   BANK_PTR,%d2
        sub.l   #PART_OFF,%d2
        add.l   #SRAM_PART,%d2
        move.l  %d2,%a1
        bsr     .Lsw_one
        tst.l   %d3
        beq     .Lsw_done
        move.l  16(%sp),%a1             | Part'
        bsr     mt_curpart
        tst.l   %d1
        beq     .Lsw_done
        cmp.l   %a0,%a1
        bne     .Lsw_done
        move.l  (%sp),%d0               | the track
        moveq   #CV_STRIDE,%d2
        muls.l  %d0,%d2
        lea     CURVALS,%a0
        add.l   %d2,%a0
        moveq   #30,%d2
        muls.l  %d0,%d2
        add.l   %d2,%a1
        lea     0x30(%a1),%a1           | the FLEX PLAYBACK bytes
        moveq   #6,%d0
.Lsw_l:
        move.b  PAGE2_GAP(%a1),%d2
        move.b  %d2,LANE_SETUP(%a0)
        move.b  (%a1)+,%d2
        move.b  %d2,(%a0)+
        subq.l  #1,%d0
        bne     .Lsw_l
.Lsw_done:
        movem.l (%sp),%d0-%d3/%a0-%a1
        lea     24(%sp),%sp
        rts
.Lsw_one:                               | a1 = a copy's signature, d3 = 1 + machine or 0; clobbers d0-d2, a0
        moveq   #0,%d0                  | d0 = 1 + the machine this copy is signed with, or 0
        moveq   #0,%d1
        move.b  2(%a1),%d1
        subq.l  #1,%d1
        bne     .Lsw_s
        move.b  (%a1),%d1
        lsl.l   #8,%d1
        move.b  1(%a1),%d1
        lea     mt_sigs,%a0
.Lsw_f:
        addq.l  #1,%d0
        mvz.w   (%a0)+,%d2
        cmp.l   %d2,%d1
        beq     .Lsw_s
        moveq   #MT_N,%d2
        cmp.l   %d2,%d0
        blt     .Lsw_f
        moveq   #0,%d0
.Lsw_s:
        tst.l   %d3
        beq     .Lsw_clr
        cmp.l   %d3,%d0
        beq     .Lsw_x                  | on this machine already: the author's knobs stand
        move.l  %d3,%d0
        subq.l  #1,%d0
        moveq   #12,%d1
        muls.l  %d1,%d0
        lea     mt_defs,%a0
        add.l   %d0,%a0
        lea     -12(%a1),%a1            | the FLEX PLAYBACK bytes (Part' + 0x30 + 30 * track)
        moveq   #6,%d0
.Lsw_d:
        move.b  6(%a0),%d2
        move.b  %d2,PAGE2_GAP(%a1)      | SETUP
        move.b  (%a0)+,%d2
        move.b  %d2,(%a1)+              | PLAYBACK
        subq.l  #1,%d0
        bne     .Lsw_d
        lea     6(%a1),%a1
        move.l  %d3,%d0
        subq.l  #1,%d0
        lea     mt_sigs,%a0
        move.b  (%a0,%d0.l*2),%d2
        move.b  %d2,(%a1)
        lea     1(%a0),%a0
        move.b  (%a0,%d0.l*2),%d2
        move.b  %d2,1(%a1)
        moveq   #1,%d2
        move.b  %d2,2(%a1)
        rts
.Lsw_clr:
        tst.l   %d0
        beq     .Lsw_x
        clr.b   (%a1)
        clr.b   1(%a1)
        clr.b   2(%a1)
.Lsw_x:
        rts

| mt_main_commit -- 0x4007981c (`mvs.b (a0),d3; move.b d4,(a0); add.l d1,d0`): the machine list's
| commit, a1 = bank, d0 = part * PART_SIZE, d1 = track, d4 = the row.  A machine's row signs the
| track and stores FLEX; any other row unsigns it.  Every audio track is admitted.
mt_main_commit:
        lea     -12(%sp),%sp
        movem.l %d0-%d1/%a0,(%sp)
        movea.l %a1,%a0
        adda.l  %d0,%a0
        adda.l  #PART_OFF,%a0
        move.l  %d1,%d0
        move.l  %d4,%d1
        bsr     .Lrow_m                 | d1 = 1 + machine, or 0
        beq     .Lmc_w
        moveq   #1,%d4                  | FLEX
.Lmc_w:
        bsr     mt_sigwrite
        movem.l (%sp),%d0-%d1/%a0
        lea     12(%sp),%sp
        mvs.b   (%a0),%d3
        move.b  %d4,(%a0)
        add.l   %d1,%d0
        jmp     0x40079822
.Lrow_m:                                | d1 = a row -> 1 + its machine, or 0 (flags set)
        subq.l  #4,%d1
        ble     .Lrm_no
        cmp.l   #MT_N,%d1
        bhi     .Lrm_no
        tst.l   %d1
        rts
.Lrm_no:
        moveq   #0,%d1
        rts

| mt_src_commit / 2 -- 0x4005a616 / 0x4005a850 (`move.l SRC_CURSOR,d1`, then `move.b d1,(a0)`):
| SRC SETUP's two commits, a1 = bank, d0 = part * PART_SIZE, d2 = track.
mt_src_commit:
        pea     0x4005a61c
        bra     .Lsrc
mt_src_commit2:
        pea     0x4005a856
.Lsrc:
        move.l  SRC_CURSOR,%d1
        lea     -12(%sp),%sp
        movem.l %d0/%d2/%a0,(%sp)
        movea.l %a1,%a0
        adda.l  %d0,%a0
        adda.l  #PART_OFF,%a0
        move.l  %d2,%d0
        move.l  %d1,%d2                 | the row
        bsr     .Lrow_m                 | d1 = 1 + machine, or 0
        bsr     mt_sigwrite
        tst.l   %d1
        beq     .Lsrc_go
        moveq   #1,%d2                  | a machine's row stores FLEX
.Lsrc_go:
        move.l  %d2,%d1                 | what the commit stores
        movem.l (%sp),%d0/%d2/%a0
        lea     12(%sp),%sp
        rts

| ---- SETUP's editor and drawer -----------------------------------------------------------------
| mt_setup_edit6 -- 0x4003a52e (`move.l d2,d0; lsl.l #3,d0; add.l d2,d2; sub.l d2,d0`, 6 * machine):
| a machine's SETUP bytes are FLEX's (Part' + 0x1da + 6 + 30 * track).  a3 = the slot: a slot the
| machine hides (Knob.count 0) is not edited here (ANALOG BD's MODEL: its engine browser's).
mt_setup_edit6:
        move.l  %d2,%d0
        subq.l  #5,%d0
        bmi     .Le6
        cmp.l   #MT_N,%d0
        bge     .Le6
        move.l  %a5,-(%sp)
        lea     mt_hidden,%a5
        mvz.b   (%a5,%d0.l),%d0
        move.l  (%sp)+,%a5
        move.l  %a3,%d2
        btst    %d2,%d0
        beq     .Le6_flex
        jmp     0x4003a624
.Le6_flex:
        moveq   #1,%d2
.Le6:
        move.l  %d2,%d0
        lsl.l   #3,%d0
        add.l   %d2,%d2
        sub.l   %d2,%d0
        jmp     0x4003a536
| mt_setup_draw6 -- 0x4003cd98 (`move.l d6,d7; lsl.l #3,d7; add.l d6,d6; sub.l d6,d7`).
mt_setup_draw6:
        move.l  %d6,%d7
        subq.l  #5,%d7
        bmi     .Ld6
        cmp.l   #MT_N,%d7
        bge     .Ld6
        moveq   #1,%d6
.Ld6:
        move.l  %d6,%d7
        lsl.l   #3,%d7
        add.l   %d6,%d6
        sub.l   %d6,%d7
        jmp     0x4003cda0

| ---- the Part validator ---------------------------------------------------------------------------
| mt_validate -- 0x40002318 (the validator's entry, `lea -96(sp),sp; movem.l ...`), validate(Part'):
| stock's validator sees FLEX's defaults in each machine track's twelve bytes (a machine's knob may
| hold a value FLEX's slot would clamp); the machine's bytes are put back after.  (OCTA303's and
| ANALOG BD's validators did exactly this, each for its own tracks.)
mt_validate:
        lea     -112(%sp),%sp           | 96: the saved bytes (12 a track), 16: d2, d3, a2, a3
        movem.l %d2-%d3/%a2-%a3,96(%sp)
        move.l  116(%sp),%a2            | Part'
        moveq   #0,%d3                  | the machine tracks' mask
        moveq   #0,%d2
.Lv_t:
        move.l  %d2,%d0
        move.l  %a2,%a0
        bsr     mt_sig
        beq     .Lv_n
        moveq   #1,%d0
        lsl.l   %d2,%d0
        or.l    %d0,%d3
        bsr     .Lvptr                  | a0 = the PLAYBACK bytes, a1 = the save slot
        lea     STOCK_DEFS,%a3
        moveq   #6,%d1
.Lv_s:
        move.b  (%a0),%d0
        move.b  %d0,(%a1)
        move.b  PAGE2_GAP(%a0),%d0
        move.b  %d0,6(%a1)
        move.b  (%a3),%d0
        move.b  %d0,(%a0)
        move.b  6(%a3),%d0
        move.b  %d0,PAGE2_GAP(%a0)
        addq.l  #1,%a0
        addq.l  #1,%a1
        addq.l  #1,%a3
        subq.l  #1,%d1
        bne     .Lv_s
.Lv_n:
        addq.l  #1,%d2
        moveq   #8,%d0
        cmp.l   %d0,%d2
        blt     .Lv_t
        move.l  %a2,-(%sp)
        jsr     .Lstock_validate
        addq.l  #4,%sp
        move.l  %d0,%a3                 | the validator's result
        moveq   #0,%d2
.Lv_r:
        btst    %d2,%d3
        beq     .Lv_rn
        bsr     .Lvptr
        moveq   #6,%d1
.Lv_rr:
        move.b  (%a1),%d0
        move.b  %d0,(%a0)
        move.b  6(%a1),%d0
        move.b  %d0,PAGE2_GAP(%a0)
        addq.l  #1,%a0
        addq.l  #1,%a1
        subq.l  #1,%d1
        bne     .Lv_rr
.Lv_rn:
        addq.l  #1,%d2
        moveq   #8,%d1
        cmp.l   %d1,%d2
        blt     .Lv_r
        move.l  %a3,%d0
        movem.l 96(%sp),%d2-%d3/%a2-%a3
        lea     112(%sp),%sp
        rts
.Lvptr:                                 | d2 = track, a2 = Part' -> a0 = Part' + 0x30 + 30*track, a1 = 4 + sp + 12*track
        moveq   #30,%d0
        muls.l  %d2,%d0
        lea     0x30(%a2),%a0
        add.l   %d0,%a0
        moveq   #12,%d0
        muls.l  %d2,%d0
        lea     4(%sp),%a1
        add.l   %d0,%a1
        rts
.Lstock_validate:
        lea     -96(%sp),%sp
        movem.l %d2-%d7/%a2-%a6,(%sp)
        jmp     0x40002320

| ---- the tables, generated -----------------------------------------------------------------------
        .align  4
mt_records:
        mt_record_longs
mt_sigs:
        mt_sig_words
mt_hidden:
        mt_hidden_bytes
mt_defs:
        mt_defaults
        .align  2
        mt_strings
        .align  4
        mt_built

| mt_build: d0 = a built record's buffer (0x192 bytes), a1 = its patch list -> d0 = its P, the
| buffer: a clone of stock's FLEX record P (0x192 bytes from P, OCTA303's o3_clone) with the listed
| fields replaced, made once (its first byte past the record is the made flag).  Patch list:
| .short offset from P, length; .long source; ended by .short -1.  Clobbers d0, d1, a0, a1.
mt_build:
        move.l  %a2,-(%sp)
        move.l  %d0,%a2
        tst.b   REC_LEN(%a2)
        bne     .Lbd_have
        lea     FLEX_P,%a0
        move.l  #REC_LEN,%d1
.Lbd_cp:
        move.b  (%a0)+,(%a2)+
        subq.l  #1,%d1
        bne     .Lbd_cp
        move.l  %d0,%a2
.Lbd_p:
        mvs.w   (%a1)+,%d1
        bmi     .Lbd_done
        lea     (%a2,%d1.l),%a0         | P + offset
        mvz.w   (%a1)+,%d1
        move.l  %a1,-(%sp)
        move.l  (%a1),%a1
.Lbd_b:
        move.b  (%a1)+,(%a0)+
        subq.l  #1,%d1
        bne     .Lbd_b
        move.l  (%sp)+,%a1
        addq.l  #4,%a1
        bra     .Lbd_p
.Lbd_done:
        moveq   #1,%d1
        move.b  %d1,REC_LEN(%a2)
.Lbd_have:
        move.l  %a2,%d0
        move.l  (%sp)+,%a2
        rts

        .if     MT_FRAMES
        .include "modules/machines/voice.s"
        .endif
        .if     MT_NOTES
        .include "modules/machines/notes.s"
        .endif

| mt_render -- the kind table's FLEX entry (0x400d6438), render(track, ping, start, end).  Without
| a ColdFire voice in the remix every track goes on to MT_RENDER_NEXT (OCTA303's sy_render or
| ANALOG BD's ab_render, each handing the tracks not its own to the next, the last to stock's).
        .if     MT_FRAMES == 0
mt_render:
        jmp     MT_RENDER_NEXT
        .endif
