| POLY's voice: one 16-sample frame of reference.Poly.step, sample for sample.
|
|   void poly_frame(struct state *st, const uint8_t pv[12], const int32_t keys[4], int32_t out[32])
|
| keys: each key's note in Q8 semitones, or 0 when it is up. out: 16 L then 16 R, Q28.
| Every multiply is the EMAC in fractional mode, truncating (MACSR 0x20), as LADDER's
| voice: `mac.l a,b,%acc0; movclr.l %acc0,d` = reference.emul(a, b). The firmware's
| EMAC state is saved and put back. Tables: tables.inc, generated from reference.py.
| tools/verify/verify_poly_voice.py runs this on the emulated ColdFire against
| reference.Poly.step, frame by frame.

        .text
        .global poly_frame
        .include "modules/poly/tables.inc"

        .set    ONE, 0x10000000         | Q28 1.0
        .set    ST_KEYS, 0              | struct state, as verify_poly_voice.py lays it out
        .set    ST_CLOCK, 16
        .set    ST_HP, 20
        .set    ST_DC, 24
        .set    ST_NZ, 28               | the noise LCG
        .set    ST_V, 32                | the four voices
        .set    VSZ, 56
        .set    V_PH, 0
        .set    V_SUB, 4                | the sub's half, 0 or 1
        .set    V_S0, 8                 | the filter's four stages
        .set    V_Y4, 24
        .set    V_CAP, 28               | the coupling capacitor
        .set    V_ENV, 32               | Q31
        .set    V_STAGE, 36             | 0 idle, 1 attack, 2 decay, 3 release
        .set    V_G, 40                 | the VCA's gain now, Q31
        .set    V_NOTE, 44              | Q8 semitones
        .set    V_KEY, 48               | its key, -1 none
        .set    V_AGE, 52
        .set    L_DT, -4                | the frame's coefficients, on the a6 frame
        .set    L_PW, -8
        .set    L_SUBL, -12
        .set    L_KV, -16
        .set    L_G, -20
        .set    L_COMP, -24
        .set    L_DG, -28
        .set    L_N, -40
        .set    L_K8, -44
        .set    L_VI, -48
        .set    L_HZ, -52
        .set    L_VAR, -60
        .set    L_2DT, -68
        .set    LOCALS, 68

poly_frame:
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
        movea.l %a6@(16),%a2            | keys

| ---- the keys -> the voices (Poly.take) ---------------------------------------------
        moveq   #0,%d7                  | k
.Lkey:  move.l  %a2@(0,%d7.l*4),%d6     | n
        lea     %a5@(ST_KEYS),%a0
        move.l  %a0@(0,%d7.l*4),%d5     | the key's last note
        cmp.l   %d5,%d6
        beq.w   .Lkeynext
        tst.l   %d5
        beq.s   .Lkeydown
        lea     %a5@(ST_V),%a1          | it was down: release the voice it holds
        moveq   #3,%d4
1:      cmp.l   %a1@(V_KEY),%d7
        bne.s   2f
        moveq   #-1,%d0
        move.l  %d0,%a1@(V_KEY)
        moveq   #3,%d0
        move.l  %d0,%a1@(V_STAGE)
2:      lea     %a1@(VSZ),%a1
        subq.l  #1,%d4
        bpl.s   1b
.Lkeydown:
        tst.l   %d6
        beq.s   .Lkeyset
        bsr.w   alloc                   | a1 = the voice
        move.l  %a5@(ST_CLOCK),%d0
        addq.l  #1,%d0
        move.l  %d0,%a5@(ST_CLOCK)
        move.l  %d7,%a1@(V_KEY)
        move.l  %d6,%a1@(V_NOTE)
        move.l  %d0,%a1@(V_AGE)
        moveq   #1,%d0
        move.l  %d0,%a1@(V_STAGE)       | attack, from its current level
.Lkeyset:
        lea     %a5@(ST_KEYS),%a0
        move.l  %d6,%a0@(0,%d7.l*4)
.Lkeynext:
        addq.l  #1,%d7
        moveq   #4,%d0
        cmp.l   %d0,%d7
        blt.w   .Lkey

| ---- the frame's knobs ----------------------------------------------------------------
        moveq   #0,%d0
        move.b  %a3@(8),%d0             | PWM
        lea     PW,%a0
        move.l  %a0@(0,%d0.l*4),%d1
        move.l  %d1,%a6@(L_PW)
        moveq   #0,%d0
        move.b  %a3@(9),%d0             | SUB
        lea     SUB_L,%a0
        move.l  %a0@(0,%d0.l*4),%d1
        move.l  %d1,%a6@(L_SUBL)
        moveq   #0,%d0
        move.b  %a3@(7),%d0             | WAVE's zone, twice, and 1 if the sub sounds: the loop
        lsr.l   #5,%d0
        add.l   %d0,%d0
        tst.l   %d1
        beq.s   1f
        addq.l  #1,%d0
1:      lea     VTAB,%a0
        move.l  %a0@(0,%d0.l*4),%d0
        move.l  %d0,%a6@(L_VAR)
        moveq   #0,%d0
        move.b  %a3@(1),%d0             | RES
        lea     K8,%a0
        move.l  %a0@(0,%d0.l*4),%d1
        move.l  %d1,%a6@(L_K8)
        lea     COMP4,%a0
        move.l  %a0@(0,%d0.l*4),%d1
        move.l  %d1,%a6@(L_COMP)
        movea.l %a6@(20),%a4            | out: its first 16 longs hold the voices' mix
        moveq   #15,%d0
1:      clr.l   %a4@+
        subq.l  #1,%d0
        bpl.s   1b
        moveq   #0,%d0                  | and its last 16 the frame's noise (R is written
        move.b  %a3@(11),%d0            | only after the voices): NOISE
        lea     NOISE_L,%a0
        move.l  %a0@(0,%d0.l*4),%d2
        move.l  %a5@(ST_NZ),%d1
        move.l  #NZ_A,%d3
        move.l  #NZ_C,%d4
        moveq   #15,%d5
1:      mulu.l  %d3,%d1                 | the LCG, mod 2^32
        add.l   %d4,%d1
        move.l  %d1,%d0
        asr.l   #3,%d0                  | its top bits, Q28 -1..1
        mac.l   %d0,%d2,%acc0
        movclr.l %acc0,%d0
        move.l  %d0,%a4@+
        subq.l  #1,%d5
        bpl.s   1b
        move.l  %d1,%a5@(ST_NZ)

| ---- each voice that sounds ------------------------------------------------------------
        moveq   #0,%d0
        move.l  %d0,%a6@(L_VI)
.Lvoice:
        move.l  %a6@(L_VI),%d0
        moveq   #VSZ,%d1
        mulu.l  %d1,%d0
        lea     %a5@(ST_V),%a1
        adda.l  %d0,%a1
        move.l  %a1@(V_STAGE),%d0
        beq.w   .Lvnext
        movea.l %a1,%a5                 | a5 = the voice from here to .Lvnext
| the envelope, once a frame
        move.l  %a5@(V_ENV),%d2
        moveq   #1,%d1
        cmp.l   %d1,%d0
        bne.s   .Ldec
        moveq   #0,%d1
        move.b  %a3@(3),%d1             | A
        lea     ATK_STEP,%a0
        add.l   %a0@(0,%d1.l*4),%d2     | both < 2^31: no carry out of 32 bits
        cmpi.l  #0x7fffffff,%d2
        bcs.s   .Lenvst                 | below full (unsigned)
        move.l  #0x7fffffff,%d2
        moveq   #2,%d0
        move.l  %d0,%a5@(V_STAGE)
        bra.s   .Lenvst
.Ldec:  moveq   #2,%d1
        cmp.l   %d1,%d0
        bne.s   .Lrel
        moveq   #0,%d1
        move.b  %a3@(5),%d1             | S
        lea     SUS_L,%a0
        move.l  %d2,%d3
        sub.l   %a0@(0,%d1.l*4),%d3     | env - sus
        moveq   #0,%d1
        move.b  %a3@(4),%d1             | D
        lea     DEC_C,%a0
        move.l  %a0@(0,%d1.l*4),%d1
        mac.l   %d3,%d1,%acc0
        movclr.l %acc0,%d4
        sub.l   %d4,%d2
        bra.s   .Lenvst
.Lrel:  moveq   #0,%d1
        move.b  %a3@(6),%d1             | R
        lea     DEC_C,%a0
        move.l  %a0@(0,%d1.l*4),%d1
        mac.l   %d2,%d1,%acc0
        movclr.l %acc0,%d4
        sub.l   %d4,%d2
.Lenvst:
        move.l  %d2,%a5@(V_ENV)
        move.l  %d2,%d0
        sub.l   %a5@(V_G),%d0
        asr.l   #4,%d0
        move.l  %d0,%a6@(L_DG)          | the VCA's step a sample
| the pitch and the cutoff
        move.l  %a5@(V_NOTE),%d0
        bsr.w   inc_of
        move.l  %d0,%a6@(L_DT)
        moveq   #0,%d1
        move.b  %a3@(0),%d1             | FREQ
        lea     CUT_I,%a0
        move.l  %a0@(0,%d1.l*4),%d5
        move.l  %a5@(V_NOTE),%d0
        subi.l  #12288,%d0
        moveq   #48,%d1
        divs.l  %d1,%d0                 | half key tracking (truncates, as tdiv)
        add.l   %d0,%d5
        moveq   #0,%d1
        move.b  %a3@(2),%d1             | ENV
        lea     ENV_I,%a0
        move.l  %a0@(0,%d1.l*4),%d1
        mac.l   %d1,%d2,%acc0           | times the envelope
        movclr.l %acc0,%d0
        add.l   %d0,%d5
        addi.l  #FC_LOW,%d5
        bpl.s   1f
        moveq   #0,%d5
1:      cmpi.l  #FC_MAX,%d5
        ble.s   2f
        move.l  #FC_MAX,%d5
2:      lea     G_TAB,%a0
        move.l  %a0@(0,%d5.l*4),%d1
        move.l  %d1,%a6@(L_G)
        lea     KS,%a0
        move.l  %a0@(0,%d5.l*4),%d1
        move.l  %a6@(L_K8),%d0
        mac.l   %d0,%d1,%acc0
        movclr.l %acc0,%d1
        move.l  %d1,%a6@(L_KV)          | the feedback, scaled for this cutoff

| ---- the voice's 16 samples, added into the mix ----------------------------------------
        movea.l %a6@(L_G),%a3           | G, kv and 2 dt live in a3, a1, a2 for the 16 samples
        movea.l %a6@(L_KV),%a1
        move.l  %a6@(L_DT),%d0
        add.l   %d0,%d0
        move.l  %d0,%a6@(L_2DT)
        movea.l %a5@(V_G),%a2           | the gain in a2, the last stage's output in d5
        move.l  %a5@(V_Y4),%d5
        movea.l %a6@(20),%a4
        moveq   #16,%d0
        move.l  %d0,%a6@(L_N)
        move.l  %a5@(V_PH),%d6          | ph, in d6 for the 16 samples
        movea.l %a6@(L_VAR),%a0         | the loop for this wave and sub
        jmp     %a0@
.Lvend: move.l  %d6,%a5@(V_PH)
        move.l  %a2,%a5@(V_G)
        move.l  %d5,%a5@(V_Y4)
        movea.l %a6@(12),%a3            | pv again
| a released voice below -100 dB falls silent
        moveq   #3,%d0
        cmp.l   %a5@(V_STAGE),%d0
        bne.s   .Lvdone
        move.l  %a5@(V_ENV),%d0
        cmpi.l  #ENV_FLOOR,%d0
        bge.s   .Lvdone
        moveq   #0,%d0
        move.l  %d0,%a5@(V_STAGE)
        move.l  %d0,%a5@(V_ENV)
        move.l  %d0,%a5@(V_G)
        move.l  %d0,%a5@(V_S0)
        move.l  %d0,%a5@(V_S0+4)
        move.l  %d0,%a5@(V_S0+8)
        move.l  %d0,%a5@(V_S0+12)
        move.l  %d0,%a5@(V_Y4)
        move.l  %d0,%a5@(V_CAP)
.Lvdone:
        movea.l %a6@(8),%a5             | st again
.Lvnext:
        addq.l  #1,%a6@(L_VI)
        moveq   #4,%d0
        cmp.l   %a6@(L_VI),%d0
        bne.w   .Lvoice

| ---- after the voices: HPF, DC, the soft clip; mono --------------------------------------
        moveq   #0,%d0
        move.b  %a3@(10),%d0            | HPF: its position, and its coefficient in a3
        lsr.l   #5,%d0
        move.l  %d0,%a6@(L_HZ)
        lea     HPF_A,%a0
        movea.l %a0@(0,%d0.l*4),%a3
        lea     TANH+2048,%a2           | tanh's middle
        movea.l %a6@(20),%a4
        moveq   #16,%d0
        move.l  %d0,%a6@(L_N)
        move.l  %a6@(L_HZ),%d0          | the post loop for this HPF position
        moveq   #2,%d1
        cmp.l   %d1,%d0
        bls.s   1f
        move.l  %d1,%d0                 | 2 and 3 share one
1:      lea     PTAB,%a0
        movea.l %a0@(0,%d0.l*4),%a0
        jmp     %a0@
.Lpend:

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


| ---- the sample loop, once for each wave (OFF, PULSE, SAW, P+S) with and without the sub:
| what the knobs leave out is not tested sample by sample. blep(t, dt) is 0 unless t < dt
| or 2^32 - t < dt, i.e. unless (t + dt) mod 2^32 < 2 dt: one add and one compare decide
| whether the subroutine runs at all. P+S needs no blep(ph): the saw's -b and the
| pulse's +b cancel, exactly (integer sums).
        .macro  SAMPLE saw, pls, sub
        move.l  %a6@(L_DT),%d1
        .if \saw + \pls == 0
        moveq   #0,%d7                  | x
        .endif
        .if \saw + \pls == 1
        moveq   #0,%d4                  | b = blep(ph, dt)
        move.l  %d6,%d3
        add.l   %d1,%d3
        cmp.l   %a6@(L_2DT),%d3
        bcc.s   1f
        move.l  %d6,%d0
        bsr.w   blep
        move.l  %d0,%d4
1:
        .endif
        .if \saw
        move.l  %d6,%d7                 | SAW: ph/8 - 1 (- b)
        lsr.l   #3,%d7
        subi.l  #ONE,%d7
        .if \pls == 0
        sub.l   %d4,%d7
        .endif
        .endif
        .if \pls
        .if \saw == 0
        move.l  %d4,%d7                 | PULSE: (+b) +-1 - blep(ph - pw, dt)
        .endif
        move.l  %a6@(L_PW),%d3
        cmp.l   %d3,%d6
        bcs.s   4f
        subi.l  #ONE,%d7
        bra.s   5f
4:      addi.l  #ONE,%d7
5:      move.l  %d6,%d0
        sub.l   %d3,%d0
        move.l  %d0,%d3
        add.l   %d1,%d3
        cmp.l   %a6@(L_2DT),%d3
        bcc.s   3f
        bsr.w   blep
        sub.l   %d0,%d7
3:
        .endif
        .if \saw + \pls
        asr.l   #1,%d7
        .endif
        .if \sub
        move.l  %d6,%d3                 | the sub's phase: ph/2, its half on top
        lsr.l   #1,%d3
        move.l  #ONE,%d4
        tst.l   %a5@(V_SUB)
        beq.s   1f
        ori.l   #0x80000000,%d3
        neg.l   %d4
1:      lsr.l   #1,%d1                  | dt / 2 (its own 2 dt is <= dt: the test stays safe)
        move.l  %d3,%d0
        add.l   %d1,%d0
        cmp.l   %a6@(L_DT),%d0
        bcc.s   2f
        move.l  %d3,%d0
        bsr.w   blep
        add.l   %d0,%d4
2:      move.l  %d3,%d0
        eori.l  #0x80000000,%d0         | sph - 2^31
        move.l  %d0,%d2
        add.l   %d1,%d2
        cmp.l   %a6@(L_DT),%d2
        bcc.s   3f
        bsr.w   blep
        sub.l   %d0,%d4
3:      move.l  %a6@(L_SUBL),%d0
        mac.l   %d4,%d0,%acc0
        movclr.l %acc0,%d4
        add.l   %d4,%d7
        .endif
        add.l   %a4@(64),%d7            | the noise: |x| <= 1 + 0.67 + 0.5
        move.l  %d6,%d0                 | the phase, and the sub's half on its wrap
        add.l   %a6@(L_DT),%d6
        cmp.l   %d0,%d6
        bcc.s   6f
        move.l  %a5@(V_SUB),%d0
        eori.l  #1,%d0
        move.l  %d0,%a5@(V_SUB)
6:      move.l  %a5@(V_CAP),%d1         | the coupling cap, 10 Hz
        move.l  %d7,%d0
        sub.l   %d1,%d0
        move.l  #DC_A,%d2
        mac.l   %d0,%d2,%acc0
        movclr.l %acc0,%d0
        add.l   %d0,%d1
        move.l  %d1,%a5@(V_CAP)
        sub.l   %d1,%d7
        mac.l   %a1,%d5,%acc0           | the feedback from the last stage's last sample
        movclr.l %acc0,%d1
        asl.l   #3,%d1
        move.l  %d7,%d0
        asr.l   #2,%d0
        sub.l   %d1,%d0                 | |.| <= 2 x 2.17 / 4 + 4.2 < 8: inside the table, no end checks
        move.l  %d0,%d1                 | u = tanh28, inline
        moveq   #22,%d2
        asr.l   %d2,%d1
        lea     TANH+2048,%a0
        lea     %a0@(0,%d1.l*4),%a0
        andi.l  #0x3fffff,%d0
        moveq   #9,%d2
        lsl.l   %d2,%d0
        move.l  %a0@(4),%d1
        sub.l   %a0@,%d1
        mac.l   %d1,%d0,%acc0
        movclr.l %acc0,%d0
        add.l   %a0@,%d0
| the four stages: w = (u - s) G, u' = s + w, s' = u' + w
        move.l  %a5@(V_S0),%d2
        sub.l   %d2,%d0
        mac.l   %d0,%a3,%acc0
        movclr.l %acc0,%d0
        add.l   %d0,%d2
        add.l   %d2,%d0
        move.l  %d0,%a5@(V_S0)
        move.l  %a5@(V_S0+4),%d3
        sub.l   %d3,%d2
        mac.l   %d2,%a3,%acc0
        movclr.l %acc0,%d2
        add.l   %d2,%d3
        add.l   %d3,%d2
        move.l  %d2,%a5@(V_S0+4)
        move.l  %a5@(V_S0+8),%d0
        sub.l   %d0,%d3
        mac.l   %d3,%a3,%acc0
        movclr.l %acc0,%d3
        add.l   %d3,%d0
        add.l   %d0,%d3
        move.l  %d3,%a5@(V_S0+8)
        move.l  %a5@(V_S0+12),%d2
        sub.l   %d2,%d0
        mac.l   %d0,%a3,%acc0
        movclr.l %acc0,%d0
        add.l   %d0,%d2
        add.l   %d2,%d0
        move.l  %d0,%a5@(V_S0+12)
        move.l  %d2,%d5                 | the last stage's output
        adda.l  %a6@(L_DG),%a2
        move.l  %a6@(L_COMP),%d0
        mac.l   %d2,%d0,%acc0
        movclr.l %acc0,%d0
        mac.l   %d0,%a2,%acc0
        movclr.l %acc0,%d0
        add.l   %d0,%a4@+
        .endm

        .macro  VLOOP saw, pls, sub, name
\name:  SAMPLE  \saw, \pls, \sub
        SAMPLE  \saw, \pls, \sub
        subq.l  #2,%a6@(L_N)
        bne.w   \name
        bra.w   .Lvend
        .endm

        VLOOP   0, 0, 0, .Lv0
        VLOOP   0, 0, 1, .Lv1
        VLOOP   0, 1, 0, .Lv2
        VLOOP   0, 1, 1, .Lv3
        VLOOP   1, 0, 0, .Lv4
        VLOOP   1, 0, 1, .Lv5
        VLOOP   1, 1, 0, .Lv6
        VLOOP   1, 1, 1, .Lv7
VTAB:   .long   .Lv0, .Lv1, .Lv2, .Lv3, .Lv4, .Lv5, .Lv6, .Lv7

        .macro  POST hz, name
\name:  move.l  %a4@,%d7
        asr.l   #2,%d7                  | x = mix / 4
        .if \hz != 1
        move.l  %a5@(ST_HP),%d1
        move.l  %d7,%d3
        sub.l   %d1,%d3
        mac.l   %d3,%a3,%acc0
        movclr.l %acc0,%d3
        add.l   %d3,%d1
        move.l  %d1,%a5@(ST_HP)
        .if \hz == 0
        move.l  %d1,%d3                 | 0: x + 2 hp + SHELF hp
        add.l   %d3,%d3
        add.l   %d3,%d7
        move.l  #SHELF,%d2
        mac.l   %d1,%d2,%acc0
        movclr.l %acc0,%d3
        add.l   %d3,%d7
        .else
        sub.l   %d1,%d7                 | 2, 3: x - hp
        .endif
        .endif
        move.l  %a5@(ST_DC),%d1         | the output coupling, 10 Hz
        move.l  %d7,%d3
        sub.l   %d1,%d3
        move.l  #DC_A,%d2
        mac.l   %d3,%d2,%acc0
        movclr.l %acc0,%d3
        add.l   %d3,%d1
        move.l  %d1,%a5@(ST_DC)
        sub.l   %d1,%d7
        move.l  #ONE/2-1,%d0            | clamp to +-0.5: tanh(8) is 1 already
        cmp.l   %d0,%d7
        ble.s   1f
        move.l  %d0,%d7
1:      move.l  #-ONE/2,%d0
        cmp.l   %d0,%d7
        bge.s   2f
        move.l  %d0,%d7
2:      move.l  %d7,%d0                 | tanh28(x 16), inline: x 16 is inside the table
        lsl.l   #4,%d0
        move.l  %d0,%d1
        moveq   #22,%d2
        asr.l   %d2,%d1
        lea     %a2@(0,%d1.l*4),%a0
        andi.l  #0x3fffff,%d0
        moveq   #9,%d2
        lsl.l   %d2,%d0
        move.l  %a0@(4),%d1
        sub.l   %a0@,%d1
        mac.l   %d1,%d0,%acc0
        movclr.l %acc0,%d0
        add.l   %a0@,%d0
        move.l  #CLIP_G,%d1
        mac.l   %d0,%d1,%acc0
        movclr.l %acc0,%d7              | x, under 0.9
        move.l  %d7,%a4@(64)            | R = L = x
        move.l  %d7,%a4@+
        subq.l  #1,%a6@(L_N)
        bne.w   \name
        bra.w   .Lpend
        .endm
        POST    0, .Lp0
        POST    1, .Lp1
        POST    2, .Lp2
PTAB:   .long   .Lp0, .Lp1, .Lp2

| alloc: -> a1 = the voice a new key takes (Poly.alloc): the first silent one, else the
| quietest releasing one (the first of equals), else the oldest. Uses d0-d3.
alloc:  lea     %a5@(ST_V),%a1
        moveq   #3,%d0
1:      tst.l   %a1@(V_STAGE)
        beq.s   9f
        lea     %a1@(VSZ),%a1
        subq.l  #1,%d0
        bpl.s   1b
        suba.l  %a0,%a0                 | the quietest releasing one so far
        lea     %a5@(ST_V),%a1
        moveq   #3,%d0
2:      moveq   #3,%d1
        cmp.l   %a1@(V_STAGE),%d1
        bne.s   3f
        move.l  %a0,%d3
        beq.s   4f
        move.l  %a1@(V_ENV),%d2
        cmp.l   %a0@(V_ENV),%d2
        bge.s   3f
4:      movea.l %a1,%a0
3:      lea     %a1@(VSZ),%a1
        subq.l  #1,%d0
        bpl.s   2b
        move.l  %a0,%d3
        beq.s   5f
        movea.l %a0,%a1
9:      rts
5:      lea     %a5@(ST_V),%a1          | the oldest
        movea.l %a1,%a0
        moveq   #2,%d0
6:      lea     %a1@(VSZ),%a1
        move.l  %a1@(V_AGE),%d2
        cmp.l   %a0@(V_AGE),%d2
        bge.s   7f
        movea.l %a1,%a0
7:      subq.l  #1,%d0
        bpl.s   6b
        movea.l %a0,%a1
        rts

| inc_of: d0 = Q8 semitones over MIDI 0 -> the phase increment, capped at 0.45 FS
| (LADDER's). Uses d1, d3, d4, a0.
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

| blep: d0 = phase, d1 = increment -> d0 = the PolyBLEP correction, Q28 (LADDER's, but
| leaving d5 alone). Uses d2.
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
        lsr.l   #8,%d2
        lsr.l   #7,%d2
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

| tanh28: d0 = x, Q28 -> tanh(x), Q28, interpolated in 1/64 steps (LADDER's).
| Uses d1, d2, a0.
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
