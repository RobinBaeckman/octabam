| GRAINER's voice: one 16-sample frame of reference.Engine (schedule, then the grains), sample for sample.
|
|   void grainer_frame(struct state *st, const uint8_t pv[12], const int32_t *smp, int32_t out[32])
|
| smp: the sample, one long per sample, 24-bit (Q23). The state holds its length
| (ST_N) and the bar in samples (ST_SPB, the tempo). out: 16 L then 16 R, Q27.
| Every value-times-fraction is the EMAC in fractional mode, truncating (MACSR
| 0x20): `mac.l a,b,%acc0; movclr.l %acc0,d` = reference.emul(a, b). The
| firmware's EMAC state is saved and put back, and ACC0 cleared before the
| first mac (LADDER's lesson). Tables: tables.inc, generated from reference.py.
| tools/verify/verify_grainer_voice.py runs this on the emulated ColdFire
| against the reference, frame by frame.

        .text
        .global grainer_frame
        .include "modules/grainer/tables.inc"

        .set    ST_T, 0                 | samples since the trig
        .set    ST_HEADI, 4             | the scan's offset from POS: whole samples ...
        .set    ST_HEADF, 8             | ... and 1/65536
        .set    ST_NEXT, 12             | the next grain attempt, in samples
        .set    ST_RNG, 16              | xorshift32
        .set    ST_N, 20                | the sample's length (set by the caller)
        .set    ST_SPB, 24              | a 4-beat bar in samples (set by the caller)
        .set    ST_SLOTS, 32            | NSLOTS grains
        .set    SL_STRIDE, 48
        .set    G_ON, 0
        .set    G_START, 4
        .set    G_END, 8
        .set    G_CURI, 12              | the next read: whole samples ...
        .set    G_CURF, 16              | ... and 1/65536
        .set    G_RATE, 20              | 16.16 a sample, negative backwards
        .set    G_GL, 24                | Q30
        .set    G_GR, 28
        .set    G_A, 32                 | the window's rise ...
        .set    G_D, 36                 | ... and fall, in samples
        .set    G_STEPA, 40             | 2^31 / A: the rise's table step, Q22
        .set    G_STEPD, 44
        .set    K_TUNE, 0               | pv[]
        .set    K_POS, 1
        .set    K_SCAN, 2
        .set    K_SIZE, 3
        .set    K_DENS, 4
        .set    K_SPRD, 5
        .set    K_AMNT, 6
        .set    K_DIR, 7
        .set    K_FADE, 8
        .set    K_SHAP, 9
        .set    K_PAN, 10
        .set    K_MODE, 11
        .set    L_SIZE, -4              | the frame's clock, on the a6 frame
        .set    L_NMAX, -8
        .set    L_MODE, -12
        .set    L_EVERY, -16
        .set    L_CH, -20
        .set    L_OV, -24
        .set    L_START, -28
        .set    L_SL, -32
        .set    L_OEND, -36
        .set    L_FALL, -40
        .set    LOCALS, 40

grainer_frame:
        link    %a6,#-LOCALS
        lea     %sp@(-52),%sp
        movem.l %d2-%d7/%a2-%a5,%sp@
        move.l  %macsr,%d0
        move.l  %d0,%sp@(40)
        move.l  #0,%macsr               | integer mode: the accumulator's whole layout
        move.l  %acc0,%d0
        move.l  %d0,%sp@(44)
        move.l  %accext01,%d0
        move.l  %d0,%sp@(48)
        move.l  #0x20,%macsr            | fractional, truncating
        movclr.l %acc0,%d0              | every mac below starts from 0, not the firmware's ACC0
        movea.l %a6@(8),%a5             | st
        movea.l %a6@(12),%a3            | pv
        movea.l %a6@(16),%a2            | smp
        movea.l %a6@(20),%a4            | out

| ---- the clock: grain length, how many, attempts every, chance, overlap -----------
        moveq   #0,%d0
        move.b  %a3@(K_SIZE),%d0
        lea     SIZE_N,%a0
        move.l  %a0@(0,%d0.l*4),%d2     | size
        move.l  %d2,%a6@(L_SIZE)
        moveq   #0,%d0
        move.b  %a3@(K_AMNT),%d0
        lea     GMAX,%a0
        move.l  %a0@(0,%d0.l*4),%d3     | nmax
        move.l  %d3,%a6@(L_NMAX)
        moveq   #0,%d0
        move.b  %a3@(K_MODE),%d0
        lea     MODE_OF,%a0
        move.l  %a0@(0,%d0.l*4),%d4     | 0 RAND, 1 SYNC, 2 OSC
        move.l  %d4,%a6@(L_MODE)
        moveq   #0,%d5
        move.b  %a3@(K_DENS),%d5        | chance: DENS in RAND
        moveq   #1,%d0
        cmp.l   %d0,%d4
        bne.s   1f
        lea     SYNC_SH,%a0             | SYNC: the bar >> the division
        move.l  %a0@(0,%d5.l*4),%d0
        move.l  %a5@(ST_SPB),%d6
        lsr.l   %d0,%d6
        moveq   #127,%d5
        bra.s   3f
1:      move.l  %d2,%d6
        divu.l  %d3,%d6                 | size / nmax
        moveq   #2,%d0
        cmp.l   %d0,%d4
        bne.s   3f
        move.l  %d2,%d0                 | OSC: or size DENS / 127, the longer
        mulu.l  %d5,%d0
        moveq   #127,%d1
        divu.l  %d1,%d0
        cmp.l   %d0,%d6
        bcc.s   2f
        move.l  %d0,%d6
2:      moveq   #127,%d5
3:      move.l  %d6,%a6@(L_EVERY)
        move.l  %d5,%a6@(L_CH)
        move.l  %d2,%d0                 | overlap, 1/16: 16 size chance / (127 max(every, 16))
        lsl.l   #4,%d0
        mulu.l  %d5,%d0
        move.l  %d6,%d1
        moveq   #16,%d7
        cmp.l   %d7,%d1
        bcc.s   4f
        move.l  %d7,%d1
4:      moveq   #127,%d7
        mulu.l  %d7,%d1
        divu.l  %d1,%d0
        move.l  %d3,%d1
        lsl.l   #4,%d1
        cmp.l   %d1,%d0
        bls.s   5f
        move.l  %d1,%d0                 | at most 16 nmax
5:      moveq   #16,%d1
        cmp.l   %d1,%d0
        bcc.s   6f
        move.l  %d1,%d0                 | at least 1
6:      move.l  %d0,%a6@(L_OV)

| ---- the attempts that fall in this frame -------------------------------------------
.Lloop: move.l  %a5@(ST_T),%d0
        moveq   #16,%d1
        add.l   %d0,%d1                 | t + 16
        move.l  %a5@(ST_NEXT),%d2
        cmp.l   %d1,%d2
        bcc.w   .Lscan                  | the next attempt is a later frame's
        cmp.l   %d0,%d2
        bcc.s   1f
        move.l  %d0,%d2
1:      move.l  %d2,%a6@(L_START)       | start = max(next, t)
        lea     %a5@(ST_SLOTS),%a0      | grains sounding at start, and the first to end
        moveq   #NSLOTS,%d1
        moveq   #0,%d3
        moveq   #-1,%d4
2:      tst.l   %a0@(G_ON)
        beq.s   3f
        move.l  %a0@(G_END),%d0
        cmp.l   %d4,%d0
        bcc.s   21f
        move.l  %d0,%d4
21:     cmp.l   %d2,%d0
        bls.s   3f
        addq.l  #1,%d3
3:      lea     %a0@(SL_STRIDE),%a0
        subq.l  #1,%d1
        bne.s   2b
        cmp.l   %a6@(L_NMAX),%d3
        bcs.s   .Lfree
        tst.l   %a6@(L_MODE)
        bne.s   .Lstep                  | SYNC, OSC: a full voice skips a beat
        move.l  %a5@(ST_NEXT),%d0       | RAND waits for the first grain to end
        cmp.l   %d4,%d0
        bcc.s   4f
        move.l  %d4,%d0
4:      move.l  %d0,%a5@(ST_NEXT)
        bra.w   .Lscan
.Lfree: bsr.w   rng
        lsr.l   #1,%d0
        move.l  %a6@(L_CH),%d1
        lea     CH,%a0
        cmp.l   %a0@(0,%d1.l*4),%d0
        bcc.s   .Lstep                  | this attempt does not play
        bsr.w   spawn
.Lstep: move.l  %a6@(L_EVERY),%d0
        tst.l   %a6@(L_MODE)
        bne.s   5f
        move.l  %d0,%d2                 | RAND: every / 2 + every u
        bsr.w   rng
        lsr.l   #1,%d0
        mac.l   %d2,%d0,%acc0
        movclr.l %acc0,%d1
        lsr.l   #1,%d2
        add.l   %d1,%d2
        move.l  %d2,%d0
5:      moveq   #16,%d1
        cmp.l   %d1,%d0
        bge.s   6f
        move.l  %d1,%d0
6:      add.l   %d0,%a5@(ST_NEXT)
        bra.w   .Lloop

| ---- the scan moves, after this frame's grains took their start -----------------------
.Lscan: moveq   #0,%d0
        move.b  %a3@(K_SCAN),%d0
        lea     SCAN_Q,%a0
        move.l  %a5@(ST_HEADF),%d1
        add.l   %a0@(0,%d0.l*4),%d1
        move.l  %d1,%d2
        moveq   #16,%d3
        asr.l   %d3,%d2
        andi.l  #0xffff,%d1
        move.l  %d1,%a5@(ST_HEADF)
        add.l   %a5@(ST_HEADI),%d2
        move.l  %a5@(ST_N),%d1
        cmp.l   %d1,%d2
        blt.s   1f
        sub.l   %d1,%d2
        bra.s   2f
1:      tst.l   %d2
        bpl.s   2f
        add.l   %d1,%d2
2:      move.l  %d2,%a5@(ST_HEADI)

| ---- the grains, 16 samples ------------------------------------------------------------
| Per grain: the samples of this frame it covers, found once; then a loop over just those,
| with the read point, the sample's length and where the fall starts in registers.
        movea.l %a4,%a0
        moveq   #31,%d0
1:      clr.l   %a0@+
        subq.l  #1,%d0
        bpl.s   1b
        lea     TS,%a0
        lea     %a5@(ST_SLOTS),%a1
        moveq   #NSLOTS,%d0
        move.l  %d0,%a6@(L_SL)
        move.l  %a5@(ST_N),%d7          | n
.Lslot: tst.l   %a1@(G_ON)
        beq.w   .Lnext
        move.l  %a1@(G_START),%d0
        sub.l   %a5@(ST_T),%d0          | the grain's first sample in this frame: start - t ...
        bpl.s   1f
        moveq   #0,%d0                  | ... or 0, already sounding
1:      moveq   #16,%d1
        cmp.l   %d1,%d0
        bge.w   .Lnext                  | starts in a later frame
        move.l  %a1@(G_END),%d1
        sub.l   %a5@(ST_T),%d1          | and its end: end - t, at most 16
        moveq   #16,%d2
        cmp.l   %d2,%d1
        ble.s   2f
        move.l  %d2,%d1
2:      lea     %a4@(0,%d1.l*4),%a3
        move.l  %a3,%a6@(L_OEND)        | out + end: where the loop stops
        lea     %a4@(0,%d0.l*4),%a3     | out + first
        move.l  %a5@(ST_T),%d6
        add.l   %d0,%d6
        sub.l   %a1@(G_START),%d6       | k, the grain's sample
        move.l  %a1@(G_END),%d0
        sub.l   %a1@(G_START),%d0
        sub.l   %a1@(G_D),%d0
        move.l  %d0,%a6@(L_FALL)        | where the fall starts
        move.l  %a1@(G_CURI),%d4
        move.l  %a1@(G_CURF),%d5
.Lsmp:  move.l  %a2@(0,%d4.l*4),%d1     | two taps, linear
        move.l  %d4,%d0
        addq.l  #1,%d0
        cmp.l   %d7,%d0
        bne.s   1f
        moveq   #0,%d0
1:      move.l  %a2@(0,%d0.l*4),%d2
        asl.l   #4,%d1                  | Q23 -> Q27
        asl.l   #4,%d2
        sub.l   %d1,%d2
        move.l  %d5,%d0
        moveq   #15,%d3
        lsl.l   %d3,%d0
        mac.l   %d2,%d0,%acc0
        movclr.l %acc0,%d2
        add.l   %d2,%d1                 | y
        move.l  %a6@(L_FALL),%d2        | the window: the fall, the rise, or flat
        cmp.l   %d2,%d6
        blt.s   2f
        move.l  %d6,%d0
        sub.l   %d2,%d0
        move.l  %a1@(G_STEPD),%d2
        mulu.l  %d2,%d0
        moveq   #22,%d3
        lsr.l   %d3,%d0
        move.l  #511,%d2
        sub.l   %d0,%d2
        move.l  %a0@(0,%d2.l*4),%d0
        bra.s   4f
2:      cmp.l   %a1@(G_A),%d6
        bge.s   3f
        move.l  %d6,%d0
        move.l  %a1@(G_STEPA),%d2
        mulu.l  %d2,%d0
        moveq   #22,%d3
        lsr.l   %d3,%d0
        move.l  %a0@(0,%d0.l*4),%d0
        bra.s   4f
3:      move.l  #0x7fffffff,%d0
4:      mac.l   %d1,%d0,%acc0
        movclr.l %acc0,%d1
        move.l  %a1@(G_GL),%d0
        mac.l   %d1,%d0,%acc0
        movclr.l %acc0,%d0
        add.l   %d0,%d0
        add.l   %d0,%a3@
        move.l  %a1@(G_GR),%d0
        mac.l   %d1,%d0,%acc0
        movclr.l %acc0,%d0
        add.l   %d0,%d0
        add.l   %d0,%a3@(64)
        addq.l  #4,%a3
        add.l   %a1@(G_RATE),%d5        | the read point moves
        move.l  %d5,%d0
        moveq   #16,%d3
        asr.l   %d3,%d0
        andi.l  #0xffff,%d5
        add.l   %d0,%d4
        cmp.l   %d7,%d4
        blt.s   5f
        sub.l   %d7,%d4
        bra.s   6f
5:      tst.l   %d4
        bpl.s   6f
        add.l   %d7,%d4
6:      addq.l  #1,%d6
        cmpa.l  %a6@(L_OEND),%a3
        bne.w   .Lsmp
        move.l  %d4,%a1@(G_CURI)
        move.l  %d5,%a1@(G_CURF)
        move.l  %a5@(ST_T),%d0          | a grain that ends by the frame's end frees its slot
        moveq   #16,%d1
        add.l   %d1,%d0
        cmp.l   %a1@(G_END),%d0
        bcs.s   .Lnext
        clr.l   %a1@(G_ON)
.Lnext: lea     %a1@(SL_STRIDE),%a1
        subq.l  #1,%a6@(L_SL)
        bne.w   .Lslot
        moveq   #16,%d0
        add.l   %d0,%a5@(ST_T)

        move.l  #0,%macsr
        move.l  %sp@(44),%d0
        move.l  %d0,%acc0
        move.l  %sp@(48),%d0
        move.l  %d0,%accext01
        move.l  %sp@(40),%d0
        move.l  %d0,%macsr
        movem.l %sp@,%d2-%d7/%a2-%a5
        unlk    %a6
        rts

| rng: d0 = the next xorshift32. Uses d1.
rng:    move.l  %a5@(ST_RNG),%d0
        move.l  %d0,%d1
        lsl.l   #8,%d1
        lsl.l   #5,%d1
        eor.l   %d1,%d0
        move.l  %d0,%d1
        lsr.l   #8,%d1
        lsr.l   #8,%d1
        lsr.l   #1,%d1
        eor.l   %d1,%d0
        move.l  %d0,%d1
        lsl.l   #5,%d1
        eor.l   %d1,%d0
        move.l  %d0,%a5@(ST_RNG)
        rts

| spawn: a grain at L_START into the lowest free slot: where, which way, pan, gain, window.
| Uses d0-d7, a0, a1.
spawn:  move.l  %a5@(ST_N),%d7          | n
        moveq   #0,%d0
        move.b  %a3@(K_POS),%d0
        lea     POS_Q,%a0
        move.l  %a0@(0,%d0.l*4),%d0
        move.l  %d7,%d1
        subq.l  #1,%d1
        mac.l   %d1,%d0,%acc0
        movclr.l %acc0,%d6
        add.l   %a5@(ST_HEADI),%d6      | POS + the scan
        cmp.l   %d7,%d6
        blt.s   1f
        sub.l   %d7,%d6
1:      bsr.w   rng                     | the spread: n SPRD/127 (u - 1/2), reflected off the ends
        addi.l  #0x80000000,%d0
        moveq   #0,%d1
        move.b  %a3@(K_SPRD),%d1
        lea     SPRD_Q,%a0
        move.l  %a0@(0,%d1.l*4),%d1
        mac.l   %d7,%d1,%acc0
        movclr.l %acc0,%d1
        mac.l   %d1,%d0,%acc0
        movclr.l %acc0,%d1
        asr.l   #1,%d1
        add.l   %d1,%d6
        bpl.s   2f
        neg.l   %d6
        bra.s   3f
2:      move.l  %d7,%d1
        subq.l  #1,%d1
        cmp.l   %d1,%d6
        ble.s   3f
        add.l   %d1,%d1
        sub.l   %d6,%d1
        move.l  %d1,%d6
3:      moveq   #0,%d0                  | the rate, backwards by DIR's chance
        move.b  %a3@(K_TUNE),%d0
        lea     RATE,%a0
        move.l  %a0@(0,%d0.l*4),%d5
        bsr.w   rng
        lsr.l   #1,%d0
        moveq   #0,%d1
        move.b  %a3@(K_DIR),%d1
        lea     CH,%a0
        cmp.l   %a0@(0,%d1.l*4),%d0
        bcc.s   4f
        neg.l   %d5
4:      bsr.w   rng                     | pan: PAN (2u - 1), Q15
        moveq   #16,%d1
        lsr.l   %d1,%d0
        subi.l  #32768,%d0
        moveq   #0,%d1
        move.b  %a3@(K_PAN),%d1
        lea     PAN_Q,%a0
        move.l  %a0@(0,%d1.l*4),%d1
        muls.l  %d1,%d0
        moveq   #15,%d1
        asr.l   %d1,%d0
        move.l  %d0,%d4                 | p
        lea     %a5@(ST_SLOTS),%a1
        moveq   #NSLOTS,%d1
5:      tst.l   %a1@(G_ON)
        beq.s   6f
        lea     %a1@(SL_STRIDE),%a1
        subq.l  #1,%d1
        bne.s   5b
        rts                             | none free (the reference raises: the gate sees it)
6:      move.l  %a6@(L_OV),%d0          | gain 1/sqrt(overlap), the pan law sqrt(1 -+ p)
        lea     GAIN16,%a0
        move.l  %a0@(0,%d0.l*4),%d3
        lea     SQ,%a0
        move.l  #32768,%d0
        sub.l   %d4,%d0
        asr.l   #8,%d0
        move.l  %a0@(0,%d0.l*4),%d0
        mac.l   %d3,%d0,%acc0
        movclr.l %acc0,%d0
        move.l  %d0,%a1@(G_GL)
        move.l  #32768,%d0
        add.l   %d4,%d0
        asr.l   #8,%d0
        move.l  %a0@(0,%d0.l*4),%d0
        mac.l   %d3,%d0,%acc0
        movclr.l %acc0,%d0
        move.l  %d0,%a1@(G_GR)
        move.l  %a6@(L_SIZE),%d2        | the window: f = fade's share, a = SHAPE's share of f
        moveq   #0,%d0
        move.b  %a3@(K_FADE),%d0
        mulu.l  %d2,%d0
        moveq   #127,%d1
        divu.l  %d1,%d0
        move.l  #2*EDGE,%d1
        cmp.l   %d1,%d0
        bge.s   7f
        move.l  %d1,%d0
7:      cmp.l   %d2,%d0
        ble.s   8f
        move.l  %d2,%d0                 | f
8:      moveq   #0,%d1
        move.b  %a3@(K_SHAP),%d1
        mulu.l  %d0,%d1
        moveq   #127,%d3
        divu.l  %d3,%d1
        move.l  %d0,%d3
        subi.l  #EDGE,%d3
        cmp.l   %d3,%d1
        ble.s   9f
        move.l  %d3,%d1
9:      move.l  #EDGE,%d3
        cmp.l   %d3,%d1
        bge.s   10f
        move.l  %d3,%d1                 | a
10:     sub.l   %d1,%d0
        cmp.l   %d3,%d0
        bge.s   11f
        move.l  %d3,%d0                 | d
11:     move.l  %d1,%a1@(G_A)
        move.l  %d0,%a1@(G_D)
        move.l  #0x80000000,%d3
        divu.l  %d0,%d3
        move.l  %d3,%a1@(G_STEPD)
        move.l  #0x80000000,%d3
        divu.l  %d1,%d3
        move.l  %d3,%a1@(G_STEPA)
        move.l  %a6@(L_START),%d0
        move.l  %d0,%a1@(G_START)
        add.l   %d2,%d0
        move.l  %d0,%a1@(G_END)
        move.l  %d6,%a1@(G_CURI)
        move.l  %a5@(ST_HEADF),%d0
        move.l  %d0,%a1@(G_CURF)
        move.l  %d5,%a1@(G_RATE)
        moveq   #1,%d0
        move.l  %d0,%a1@(G_ON)
        rts
