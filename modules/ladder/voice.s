| LADDER's voice: one 16-sample frame of reference.Voice.step, sample for sample.
|
|   void ladder_frame(struct state *st, const uint8_t pv[12], int note8, int32_t out[16])
|
| note8: the held note in Q8 semitones, or 0 when the gate is down. out: Q28.
| Every multiply is the EMAC in fractional mode, truncating (MACSR 0x20):
| `mac.l a,b,%acc0; movclr.l %acc0,d` = reference.emul(a, b) = (a * b) >> 31.
| The firmware's own EMAC state is saved in integer mode and put back, as its
| frame interrupt does (docs/contributing/TRAPS.md, MACSR). Tables: tables.inc,
| generated from reference.py. tools/verify/verify_ladder_voice.py runs this on
| the emulated ColdFire against reference.Voice.step, frame by frame.

        .text
        .global ladder_frame
        .include "modules/ladder/tables.inc"

        .set    ONE, 0x10000000         | Q28 1.0
        .set    NONE, 0x80000000        | no note held yet
        .set    ST_PH1, 0               | struct state, as verify_ladder_voice.py lays it out
        .set    ST_PH2, 4
        .set    ST_RNG, 8
        .set    ST_S0, 12               | the ladder's four integrators, S0..S3
        .set    ST_S3, 24
        .set    ST_TGT, 28              | the held note, Q8 (NONE before the first)
        .set    ST_OFF, 32              | the glide's distance to it, Q24
        .set    ST_GATE, 36
        .set    ST_ENV, 40              | the contour, Q31
        .set    ST_STAGE, 44            | 0 idle, 1 attack, 2 decay, 3 release
        .set    ST_DC, 48
        .set    L_DT1, -4               | the frame's coefficients, on the a6 frame
        .set    L_DT2, -8
        .set    L_W, -12
        .set    L_M15, -16
        .set    L_NZ, -20
        .set    L_G, -24
        .set    L_G2, -28
        .set    L_G3, -32
        .set    L_G4, -36
        .set    L_OMG, -40
        .set    L_INV, -44
        .set    L_K8, -48
        .set    L_COMP, -52
        .set    L_N, -56
        .set    LOCALS, 56

ladder_frame:
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
        move.l  %a6@(16),%d7            | note8

| ---- the gate and the glide ------------------------------------------------------
        tst.l   %d7
        ble.w   .Lnohold
        tst.l   %a5@(ST_GATE)
        bne.s   1f
        moveq   #1,%d0
        move.l  %d0,%a5@(ST_STAGE)      | a new note: the contour starts again
1:      move.l  %a5@(ST_TGT),%d1
        cmpi.l  #NONE,%d1
        beq.s   .Lnoglide
        moveq   #0,%d0
        move.b  %a3@(5),%d0             | GLID
        beq.s   .Lnoglide
        sub.l   %d7,%d1                 | old note - new, Q8 (|.| < 2^15)
        moveq   #16,%d2
        asl.l   %d2,%d1                 | Q24
        move.l  %a5@(ST_OFF),%d2
        add.l   %d1,%d2
        bvc.s   2f
        move.l  #0x7fffffff,%d2         | past 32 bits: the side the addend went
        tst.l   %d1
        bpl.s   2f
        move.l  #0x80000000,%d2
2:      lea     GLIDE_C,%a0
        move.l  %a0@(0,%d0.l*4),%d1
        mac.l   %d2,%d1,%acc0
        movclr.l %acc0,%d1
        sub.l   %d1,%d2
        move.l  %d2,%a5@(ST_OFF)
        bra.s   .Lsettgt
.Lnoglide:
        clr.l   %a5@(ST_OFF)
.Lsettgt:
        move.l  %d7,%a5@(ST_TGT)
        moveq   #1,%d0
        move.l  %d0,%a5@(ST_GATE)
        bra.s   .Lenv
.Lnohold:
        tst.l   %a5@(ST_GATE)
        beq.s   1f
        moveq   #3,%d0
        move.l  %d0,%a5@(ST_STAGE)      | the gate fell: release
1:      clr.l   %a5@(ST_GATE)

| ---- the contour --------------------------------------------------------------------
.Lenv:  move.l  %a5@(ST_STAGE),%d0
        move.l  %a5@(ST_ENV),%d2
        moveq   #1,%d1
        cmp.l   %d1,%d0
        bne.s   .Ldec
        moveq   #0,%d1
        move.b  %a3@(10),%d1            | ATK
        lea     ATK_STEP,%a0
        add.l   %a0@(0,%d1.l*4),%d2     | both < 2^31: no carry out of 32 bits
        cmpi.l  #0x7fffffff,%d2
        bcs.s   .Lenvst                 | below full (unsigned)
        move.l  #0x7fffffff,%d2
        moveq   #2,%d0
        move.l  %d0,%a5@(ST_STAGE)
        bra.s   .Lenvst
.Ldec:  moveq   #2,%d1
        cmp.l   %d1,%d0
        bne.s   .Lrel
        moveq   #0,%d1
        move.b  %a3@(11),%d1            | SUS
        lea     SUS_L,%a0
        move.l  %a0@(0,%d1.l*4),%d3
        sub.l   %d3,%d2                 | env - sus
        moveq   #0,%d1
        move.b  %a3@(4),%d1             | DEC
        lea     DEC_C,%a0
        move.l  %a0@(0,%d1.l*4),%d1
        mac.l   %d2,%d1,%acc0
        movclr.l %acc0,%d4
        sub.l   %d4,%d2
        add.l   %d3,%d2
        bra.s   .Lenvst
.Lrel:  moveq   #3,%d1
        cmp.l   %d1,%d0
        bne.s   .Lenvst
        moveq   #0,%d1
        move.b  %a3@(4),%d1             | DEC: also the release
        lea     DEC_C,%a0
        move.l  %a0@(0,%d1.l*4),%d1
        mac.l   %d2,%d1,%acc0
        movclr.l %acc0,%d4
        sub.l   %d4,%d2
.Lenvst:
        move.l  %d2,%a5@(ST_ENV)

| ---- the pitch: two phase increments ------------------------------------------------
        move.l  %a5@(ST_TGT),%d0
        cmpi.l  #NONE,%d0
        bne.s   1f
        move.l  #12288,%d0              | no note yet: C3
        bra.s   2f
1:      move.l  %a5@(ST_OFF),%d1
        moveq   #16,%d3
        asr.l   %d3,%d1
        add.l   %d1,%d0
2:      moveq   #0,%d1
        move.b  %a3@(0),%d1             | TUNE
        lea     SEMI256,%a0
        add.l   %a0@(0,%d1.l*4),%d0
        move.l  %d0,%d6                 | p8
        bsr.w   inc_of
        move.l  %d0,%a6@(L_DT1)
        moveq   #0,%d1
        move.b  %a3@(7),%d1             | DET
        lea     DET_Q8,%a0
        move.l  %d6,%d0
        add.l   %a0@(0,%d1.l*4),%d0
        bsr.w   inc_of
        move.l  %d0,%a6@(L_DT2)

| ---- the cutoff: G and its powers, 1 / (1 + k G^4) ---------------------------------
        moveq   #0,%d1
        move.b  %a3@(1),%d1             | CUT
        lea     CUT_I,%a0
        move.l  %a0@(0,%d1.l*4),%d5
        move.l  %d6,%d0
        subi.l  #12288,%d0
        moveq   #48,%d1
        divs.l  %d1,%d0                 | half key tracking: 1/48 of a Q8 semitone a step (truncates)
        add.l   %d0,%d5
        moveq   #0,%d1
        move.b  %a3@(3),%d1             | CONT
        lea     CONT_I,%a0
        move.l  %a0@(0,%d1.l*4),%d1
        mac.l   %d1,%d2,%acc0           | times the contour
        movclr.l %acc0,%d0
        add.l   %d0,%d5
        addi.l  #FC_LOW,%d5
        bpl.s   1f
        moveq   #0,%d5
1:      cmpi.l  #FC_LOW+FC_TOP,%d5
        ble.s   2f
        move.l  #FC_LOW+FC_TOP,%d5
2:      lea     G_TAB,%a0
        move.l  %a0@(0,%d5.l*4),%d1     | G
        move.l  %d1,%a6@(L_G)
        mac.l   %d1,%d1,%acc0
        movclr.l %acc0,%d0
        move.l  %d0,%a6@(L_G2)
        mac.l   %d0,%d1,%acc0
        movclr.l %acc0,%d0
        move.l  %d0,%a6@(L_G3)
        mac.l   %d0,%d1,%acc0
        movclr.l %acc0,%d0
        move.l  %d0,%a6@(L_G4)
        moveq   #0,%d3
        move.b  %a3@(2),%d3             | EMPH
        lea     K8,%a0
        move.l  %a0@(0,%d3.l*4),%d4
        move.l  %d4,%a6@(L_K8)
        mac.l   %d4,%d0,%acc0           | k G^4, Q28
        movclr.l %acc0,%d0
        addi.l  #ONE,%d0
        moveq   #13,%d4
        lsr.l   %d4,%d0
        move.l  #0x7fffffff,%d4
        divu.l  %d0,%d4
        moveq   #15,%d0
        lsl.l   %d0,%d4
        move.l  %d4,%a6@(L_INV)
        move.l  #0x7fffffff,%d0
        sub.l   %d1,%d0
        move.l  %d0,%a6@(L_OMG)         | 1 - G
        lea     COMP4,%a0
        move.l  %a0@(0,%d3.l*4),%d1
        move.l  %d1,%a6@(L_COMP)
        moveq   #0,%d0
        move.b  %a3@(6),%d0             | WAVE
        lea     WAVE_OF,%a0
        move.l  %a0@(0,%d0.l*4),%d1
        move.l  %d1,%a6@(L_W)
        moveq   #0,%d0
        move.b  %a3@(8),%d0             | MIX
        lea     MIX15,%a0
        move.l  %a0@(0,%d0.l*4),%d1
        move.l  %d1,%a6@(L_M15)
        moveq   #0,%d0
        move.b  %a3@(9),%d0             | NOIS
        lea     NZ,%a0
        move.l  %a0@(0,%d0.l*4),%d1
        move.l  %d1,%a6@(L_NZ)

| ---- 16 samples -------------------------------------------------------------------------
        movea.l %a6@(20),%a4            | out
        moveq   #16,%d0
        move.l  %d0,%a6@(L_N)
.Lsmp:  move.l  %a5@(ST_PH1),%d0
        move.l  %a6@(L_DT1),%d1
        move.l  %a6@(L_W),%d2
        bsr.w   osc
        move.l  %d0,%d6                 | o1
        move.l  %a5@(ST_PH2),%d0
        move.l  %a6@(L_DT2),%d1
        move.l  %a6@(L_W),%d2
        bsr.w   osc
        move.l  %d0,%d7                 | o2
        move.l  %a6@(L_DT1),%d0
        add.l   %d0,%a5@(ST_PH1)
        move.l  %a6@(L_DT2),%d0
        add.l   %d0,%a5@(ST_PH2)
        move.l  %a5@(ST_RNG),%d0        | the noise: a 32-bit LCG
        move.l  #1664525,%d1
        mulu.l  %d1,%d0
        addi.l  #1013904223,%d0
        move.l  %d0,%a5@(ST_RNG)
        lsr.l   #3,%d0
        subi.l  #ONE,%d0                | white, Q28
        moveq   #15,%d3
        asr.l   %d3,%d6
        asr.l   %d3,%d7
        move.l  %a6@(L_M15),%d1
        move.l  #32768,%d2
        sub.l   %d1,%d2
        muls.l  %d2,%d6
        muls.l  %d1,%d7
        add.l   %d7,%d6
        asr.l   #2,%d6                  | the mix, DRIVE 1/4
        move.l  %a6@(L_NZ),%d1
        mac.l   %d0,%d1,%acc0
        movclr.l %acc0,%d0
        asr.l   #2,%d0
        add.l   %d0,%d6                 | x
| the ladder: the linear solve for the output, then the tanh on the feedback sum
        move.l  %a6@(L_G3),%d1
        move.l  %a5@(ST_S0),%d2
        mac.l   %d1,%d2,%acc0
        movclr.l %acc0,%d3
        move.l  %a6@(L_G2),%d1
        move.l  %a5@(ST_S0+4),%d2
        mac.l   %d1,%d2,%acc0
        movclr.l %acc0,%d4
        add.l   %d4,%d3
        move.l  %a6@(L_G),%d1
        move.l  %a5@(ST_S0+8),%d2
        mac.l   %d1,%d2,%acc0
        movclr.l %acc0,%d4
        add.l   %d4,%d3
        add.l   %a5@(ST_S3),%d3
        move.l  %a6@(L_OMG),%d1
        mac.l   %d3,%d1,%acc0
        movclr.l %acc0,%d3              | S
        move.l  %a6@(L_G4),%d1
        mac.l   %d1,%d6,%acc0
        movclr.l %acc0,%d4
        add.l   %d3,%d4
        move.l  %a6@(L_INV),%d1
        mac.l   %d4,%d1,%acc0
        movclr.l %acc0,%d4              | y4, the estimate
        move.l  %a6@(L_K8),%d1
        mac.l   %d1,%d4,%acc0
        movclr.l %acc0,%d4
        asl.l   #3,%d4                  | k y4
        move.l  %d6,%d0
        sub.l   %d4,%d0
        bsr.w   tanh28                  | u
        move.l  %a6@(L_G),%d1
        lea     %a5@(ST_S0),%a0
        moveq   #3,%d5
.Lst:   move.l  %a0@,%d2                | s
        move.l  %d0,%d3
        sub.l   %d2,%d3
        mac.l   %d3,%d1,%acc0
        movclr.l %acc0,%d3              | v = (u - s) G
        move.l  %d3,%d0
        add.l   %d2,%d0                 | u = v + s
        move.l  %d0,%d4
        add.l   %d3,%d4
        move.l  %d4,%a0@+               | s = u + v
        subq.l  #1,%d5
        bpl.s   .Lst
        move.l  %a6@(L_COMP),%d1
        mac.l   %d0,%d1,%acc0
        movclr.l %acc0,%d0
        asl.l   #2,%d0                  | y
        move.l  %a5@(ST_DC),%d1
        move.l  %d0,%d2
        sub.l   %d1,%d2
        move.l  #DC_A31,%d3
        mac.l   %d2,%d3,%acc0
        movclr.l %acc0,%d2
        add.l   %d2,%d1
        move.l  %d1,%a5@(ST_DC)         | the output coupling, 10 Hz
        sub.l   %d1,%d0
        move.l  %d0,%a4@+
        subq.l  #1,%a6@(L_N)
        bne.w   .Lsmp

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

| inc_of: d0 = Q8 semitones over MIDI 0 -> the phase increment, capped at 0.45 FS.
| Uses d1, d3, d4, a0.
inc_of: tst.l   %d0
        bpl.s   1f
        moveq   #0,%d0
1:      move.l  #3072,%d1
        move.l  %d0,%d3
        divu.l  %d1,%d3                 | the octave
        move.l  %d3,%d4
        mulu.l  %d1,%d4
        sub.l   %d4,%d0                 | within it, 1/256 semitone
        lea     INC,%a0
        move.l  %a0@(0,%d0.l*4),%d0
        move.l  #INC_MAX,%d1
        lsr.l   %d3,%d1
        cmp.l   %d1,%d0
        bls.s   2f                      | INC << octave fits under the cap
        move.l  #INC_MAX,%d0
        rts
2:      lsl.l   %d3,%d0
        rts

| osc: d0 = phase, d1 = increment, d2 = wave -> d0 = the sample, Q28.
| Uses d2-d5, a0, a1 (and blep's).
osc:    tst.l   %d2
        bne.s   1f
        move.l  %d0,%d3                 | TRI
        lsr.l   #2,%d3
        tst.l   %d0
        bmi.s   2f
        move.l  %d3,%d0
        subi.l  #ONE,%d0
        rts
2:      move.l  #3*ONE,%d0
        sub.l   %d3,%d0
        rts
1:      moveq   #1,%d3
        cmp.l   %d3,%d2
        bne.s   3f
        cmpi.l  #0xC0000000,%d0         | SHRK
        bcc.s   4f
        lsr.l   #1,%d0
        move.l  #THIRD,%d3
        mac.l   %d0,%d3,%acc0
        movclr.l %acc0,%d0              | ph / 6
        subi.l  #ONE,%d0
        rts
4:      subi.l  #0xC0000000,%d0
        lsr.l   #1,%d0
        move.l  #ONE,%d3
        sub.l   %d0,%d3
        move.l  %d3,%d0
        rts
3:      moveq   #2,%d3
        cmp.l   %d3,%d2
        bne.s   5f
        move.l  %d0,%d4                 | SAW
        lsr.l   #3,%d4
        subi.l  #ONE,%d4
        bsr.s   blep
        sub.l   %d0,%d4
        move.l  %d4,%d0
        rts
5:      lea     PW_TAB,%a0              | SQR WIDE NARR
        move.l  %a0@(-12,%d2.l*4),%d3   | the width
        move.l  #ONE,%d4
        cmp.l   %d3,%d0
        bcs.s   6f
        move.l  #-ONE,%d4
6:      movea.l %d0,%a1
        bsr.s   blep
        add.l   %d0,%d4
        move.l  %a1,%d0
        sub.l   %d3,%d0
        bsr.s   blep
        sub.l   %d0,%d4
        move.l  %d4,%d0
        rts

| blep: d0 = phase, d1 = increment -> d0 = the PolyBLEP correction, Q28. Uses d2, d5.
blep:   cmp.l   %d1,%d0
        bcc.s   1f
        bsr.s   .Lq                     | t < dt: -(1 - t/dt)^2
        neg.l   %d0
        rts
1:      neg.l   %d0                     | r = 2^32 - t (t >= dt > 0 here)
        cmp.l   %d1,%d0
        bcc.s   2f
        bra.s   .Lq                     | r < dt: (1 - r/dt)^2
2:      moveq   #0,%d0
        rts
.Lq:    move.l  %d1,%d2                 | ((32768 - min(32768, d0 / (dt >> 15)))^2) >> 2
        moveq   #15,%d5
        lsr.l   %d5,%d2
        bne.s   3f
        moveq   #1,%d2
3:      divu.l  %d2,%d0
        move.l  #32768,%d2
        cmp.l   %d2,%d0
        bls.s   4f
        move.l  %d2,%d0
4:      sub.l   %d0,%d2
        mulu.l  %d2,%d2
        lsr.l   #2,%d2
        move.l  %d2,%d0
        rts

| tanh28: d0 = x, Q28 -> tanh(x), Q28, interpolated in 1/64 steps. Uses d1, d2, a0.
tanh28: move.l  %d0,%d1
        moveq   #22,%d2
        asr.l   %d2,%d1
        addi.l  #512,%d1
        bpl.s   1f
        lea     TANH,%a0
        move.l  %a0@,%d0
        rts
1:      cmpi.l  #1024,%d1
        blt.s   2f
        lea     TANH+4096,%a0
        move.l  %a0@,%d0
        rts
2:      lea     TANH,%a0
        lea     %a0@(0,%d1.l*4),%a0
        andi.l  #0x3fffff,%d0
        moveq   #9,%d2
        lsl.l   %d2,%d0
        move.l  %a0@(4),%d1
        sub.l   %a0@,%d1
        mac.l   %d1,%d0,%acc0
        movclr.l %acc0,%d0
        add.l   %a0@,%d0
        rts
