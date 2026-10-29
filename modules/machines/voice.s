| MACHINES -- a ColdFire voice (schema.Machine.frame) rendered into the FLEX stream.
| Included by table.s when a machine of the remix has a `frame`.
|
| mt_render(track, ping, start, end) is the kind table's FLEX entry.  The packer calls it once a
| 16-sample frame, twice when a START splits the frame ([0,n) then [n,16)).  A track on a frame
| machine is rendered as OCTA303's TB-303 machine has been on units since v7.0 (sy_render): the
| stock renderer is called with the four arguments -- on the frame's last call with PTCH / RATE
| neutral (0x4000 / 0x7f00) and the voice's sample positions pinned around it, so the carrier's
| rate is 1.0 and it never ends -- then its samples (header byte 3 = how many, L/R longs from +16,
| the high 24 bits sent to the DSP) are overwritten with the machine's.  The voice runs in whole
| 16-sample frames from a per-track ring, so a split call costs nothing extra.  Every other track
| goes on to MT_RENDER_NEXT.
|
| What reaches the voice: pv[12] = the track's PLAYBACK words (the frame builder's record, locks
| and LFOs applied, raw << 8) and its SETUP bytes from the live lane; keys = the table's held
| notes for the track (notes.s), Q8 semitones, 0 = up.  Out: Q28, sent as its top 24 bits
| (x >> 5, clamped), so 1.0 is full scale.
        .set    VOICE_BASE,     0x800049d8      | the CF voice structs: +64..+83 the sample positions
        .set    VOICE_STRIDE,   0xa8
        .set    V_POS,          64
        .set    CURSOR,         0x80001c80      | the header this call writes
        .set    NIBBLE,         0x46104d0c      | the packer's per-track event byte, bit 4 = a START
        .set    FP_PTR,         0x800062a8      | the packer's per-track DSP parameter record (halfwords)
        .set    RS_PTR,         0x800062a4      | its render state (+4 = the latched retrig count)
        .set    NEUTRAL_PTCH,   0x4000
        .set    NEUTRAL_RATE,   0x7f00
        .set    S24MAX,         0x7fffff
| the table's per-track block, VT bytes a track
        .set    T_MACH,         0               | 1 + the frame machine the track is on, else 0
        .set    T_POS,          4               | the ring's read position, 16 = empty
        .set    T_PTCH,         8               | PTCH / RATE as the builder wrote them
        .set    T_RATE,         12
        .set    T_VPOS,         16              | the voice's positions (20 bytes)
        .set    T_PV,           36              | the twelve knobs (12 bytes)
        .set    T_RING,         48              | 16 L then 16 R, Q28
        .set    VT,             176
        .global mt_render, mt_vtracks, mt_voices, mt_keys

mt_render:
        lea     -48(%sp),%sp
        movem.l %d2-%d7/%a2-%a6,(%sp)
        move.l  52(%sp),%d2             | track
        moveq   #7,%d0
        cmp.l   %d0,%d2
        bhi     .Lr_next
        move.l  CURSOR,%a2
        move.l  #VT,%d0
        muls.l  %d2,%d0
        lea     mt_vtracks,%a3
        add.l   %d0,%a3
        moveq   #16,%d0
        cmp.l   64(%sp),%d0             | the frame's last call: which machine is the track on now?
        bne     .Lr_have
        bsr     mt_curpart
        moveq   #0,%d3
        tst.l   %d1
        beq     .Lr_set
        move.l  %d2,%d0
        bsr     mt_sig                  | d0 = 1 + machine, or 0
        beq     .Lr_set
        move.l  %d0,%d1
        lsl.l   #4,%d1
        lea     mt_voices-16,%a0
        tst.l   (%a0,%d1.l)             | a frame machine?
        beq     .Lr_set
        move.l  %d0,%d3
.Lr_set:
        cmp.l   T_MACH(%a3),%d3
        beq     .Lr_have
        move.l  %d3,T_MACH(%a3)         | a track joins (or leaves) a voice: its state from zero
        moveq   #16,%d0
        move.l  %d0,T_POS(%a3)
        tst.l   %d3
        beq     .Lr_have
        bsr     .Lr_row
        move.l  4(%a4),%d0              | state bytes
        move.l  %d0,%d1
        muls.l  %d2,%d1
        move.l  12(%a4),%a0
        add.l   %d1,%a0
        lsr.l   #2,%d0
        beq     .Lr_have
1:      clr.l   (%a0)+
        subq.l  #1,%d0
        bne     1b
.Lr_have:
        tst.l   T_MACH(%a3)
        beq     .Lr_next
        bsr     .Lr_row                 | a4 = the machine's voice row
        move.l  FP_PTR,%a5
        moveq   #0,%d4                  | 1 = PTCH / RATE and the positions are pinned for the call
        moveq   #16,%d0
        cmp.l   64(%sp),%d0
        bne     .Lr_call
        lea     NIBBLE,%a0
        add.l   %d2,%a0
        btst    #4,(%a0)
        beq     1f
        move.l  RS_PTR,%a0
        clr.l   4(%a0)                  | a START: no stock retrigs (a knob sits in the RTRG slot)
1:      mvz.w   (%a5),%d0
        move.l  %d0,T_PTCH(%a3)
        mvz.w   6(%a5),%d0
        move.l  %d0,T_RATE(%a3)
        move.l  #NEUTRAL_PTCH,%d0
        move.w  %d0,(%a5)
        move.l  #NEUTRAL_RATE,%d0
        move.w  %d0,6(%a5)
        bsr     .Lr_vpos
        lea     T_VPOS(%a3),%a1
        moveq   #5,%d0
1:      move.l  (%a0)+,(%a1)+
        subq.l  #1,%d0
        bne     1b
        moveq   #1,%d4
.Lr_call:
        move.l  64(%sp),-(%sp)
        move.l  64(%sp),-(%sp)
        move.l  64(%sp),-(%sp)
        move.l  64(%sp),-(%sp)
        jsr     STOCK_RENDER
        lea     16(%sp),%sp
        move.l  %d0,44(%sp)             | the stock return, handed back
        tst.l   %d4
        beq     .Lr_pv
        move.l  T_PTCH(%a3),%d0
        move.w  %d0,(%a5)
        move.l  T_RATE(%a3),%d0
        move.w  %d0,6(%a5)
        bsr     .Lr_vpos
        lea     T_VPOS(%a3),%a1
        moveq   #5,%d0
1:      move.l  (%a1)+,(%a0)+
        subq.l  #1,%d0
        bne     1b
.Lr_pv:
        lea     T_PV(%a3),%a1           | the knobs: PLAYBACK from the builder's words, SETUP the lane's
        move.l  %a5,%a0
        moveq   #6,%d0
1:      move.b  (%a0),(%a1)+            | the high byte of each word
        addq.l  #2,%a0
        subq.l  #1,%d0
        bne     1b
        moveq   #72,%d0
        muls.l  %d2,%d0
        lea     0x80000810+0x20,%a0
        add.l   %d0,%a0
        moveq   #6,%d0
1:      move.b  (%a0)+,(%a1)+
        subq.l  #1,%d0
        bne     1b
        moveq   #0,%d7
        move.b  3(%a2),%d7              | samples this call ships
        beq     .Lr_done
        lea     16(%a2),%a6
.Lr_s:
        move.l  T_POS(%a3),%d5
        moveq   #16,%d0
        cmp.l   %d0,%d5
        blt     .Lr_out
        lea     T_RING(%a3),%a0         | frame(state, pv, keys, out)
        move.l  %a0,-(%sp)
        lea     mt_keys,%a0
        move.l  %d2,%d0
        lsl.l   #4,%d0
        add.l   %d0,%a0
        move.l  %a0,-(%sp)
        pea     T_PV(%a3)
        move.l  4(%a4),%d0
        muls.l  %d2,%d0
        add.l   12(%a4),%d0
        move.l  %d0,-(%sp)
        move.l  (%a4),%a0
        jsr     (%a0)
        lea     16(%sp),%sp
        moveq   #0,%d5
.Lr_out:
        lea     T_RING(%a3),%a0
        move.l  (%a0,%d5.l*4),%d0
        bsr     .Lr_s24
        move.l  %d0,(%a6)+
        lea     T_RING+64(%a3),%a0
        move.l  (%a0,%d5.l*4),%d0
        bsr     .Lr_s24
        move.l  %d0,(%a6)+
        addq.l  #1,%d5
        move.l  %d5,T_POS(%a3)
        subq.l  #1,%d7
        bne     .Lr_s
.Lr_done:
        move.l  44(%sp),%d0
        movem.l (%sp),%d2-%d7/%a2-%a6
        lea     48(%sp),%sp
        rts
.Lr_next:
        movem.l (%sp),%d2-%d7/%a2-%a6
        lea     48(%sp),%sp
        jmp     MT_RENDER_NEXT
.Lr_row:                                | a4 = mt_voices + 16 * (T_MACH - 1)
        move.l  T_MACH(%a3),%d0
        subq.l  #1,%d0
        lsl.l   #4,%d0
        lea     mt_voices,%a4
        add.l   %d0,%a4
        rts
.Lr_vpos:                               | a0 = track d2's voice positions; clobbers d0
        move.l  #VOICE_STRIDE,%d0
        muls.l  %d2,%d0
        lea     VOICE_BASE+V_POS,%a0
        add.l   %d0,%a0
        rts
.Lr_s24:                                | d0 Q28 -> its top 24 bits in a long: clamp(d0 >> 5) << 8
        asr.l   #5,%d0
        cmp.l   #S24MAX,%d0
        ble     1f
        move.l  #S24MAX,%d0
1:      cmp.l   #-S24MAX,%d0
        bge     2f
        move.l  #-S24MAX,%d0
2:      lsl.l   #8,%d0
        rts

        .align  4
mt_voices:                              | frame, state bytes, notes, state base: a machine
        mt_voice_longs
mt_vtracks:
        .fill   VT*8, 1, 0
mt_keys:                                | four held notes a track, Q8 (notes.s writes them)
        .fill   16*8, 1, 0
        mt_voice_state
        .align  4
