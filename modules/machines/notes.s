| MACHINES -- the note input: a MIDI track plays the machine on its audio track.
| Included by table.s when a machine of the remix takes notes (schema.Machine.notes).
|
| An audio track's own trig carries one note (its PTCH), so it cannot play a chord.  A MIDI
| track's trig carries four (NOTE NOT2 NOT3 NOT4), recorded from the grid or live, shown on its
| trig keys; its CHROMATIC keyboard plays them live; MIDI note-in on its channel reaches it.  All
| of those leave the unit as MIDI messages through one routine, the send primitive
| 0x40010bc8(len, buffer) (docs/firmware/MIDI_TRACKS.md), note-offs at the trig's LEN included.
| So the table hooks its entry: a note-on or note-off on MIDI track t's channel (Part' + 0x4e2 +
| 0x24 * t: 0 = off, else channel + 1) is a key down or up for the machine on audio track t,
| when that machine takes notes.  The first key down posts the audio track a START (0x1d into
| its voice command, 0x46c80354 + 4 * t, as MIDI note-in on an audio track's channel does,
| docs/firmware/MIDI.md 2); the last key up posts its release (0x40).  So the track's AMP opens
| and closes with the notes.  The message is sent as before: the MIDI track still plays out.
        .set    MIDI_CHAN,      0x4e2           | Part' + this + 0x24 * MIDI track: CHAN
        .set    VCMD,           0x46c80354      | the per-track voice command (a long a track)
        .global mt_midi

| mt_midi -- 0x40010bc8 (`lea -20(sp),sp; movem.l d2-d5/a2,(sp)`), send(len 4(sp), buffer 8(sp)).
mt_midi:
        lea     -32(%sp),%sp
        movem.l %d0-%d5/%a0-%a1,(%sp)
        move.l  36(%sp),%d4             | len
        move.l  40(%sp),%a1             | buffer
        moveq   #0,%d5                  | i
.Lm_msg:
        move.l  %d4,%d0
        sub.l   %d5,%d0
        moveq   #3,%d1
        cmp.l   %d1,%d0
        blt     .Lm_out                 | fewer than three bytes left: no note
        moveq   #0,%d2
        move.b  (%a1,%d5.l),%d2         | status
        moveq   #0,%d0
        move.b  %d2,%d0
        lsr.l   #4,%d0
        moveq   #8,%d1
        cmp.l   %d1,%d0
        blt     .Lm_out                 | a data byte: running status, not ours to parse
        beq     .Lm_note
        moveq   #9,%d1
        cmp.l   %d1,%d0
        beq     .Lm_note
        moveq   #0xc,%d1                | program change, channel pressure: two bytes
        cmp.l   %d1,%d0
        beq     .Lm_two
        moveq   #0xd,%d1
        cmp.l   %d1,%d0
        beq     .Lm_two
        moveq   #0xf,%d1
        cmp.l   %d1,%d0
        beq     .Lm_out                 | system: not in a track's stream
        addq.l  #3,%d5
        bra     .Lm_msg
.Lm_two:
        addq.l  #2,%d5
        bra     .Lm_msg
.Lm_note:
        moveq   #0,%d1
        move.b  1(%a1,%d5.l),%d1        | the note
        moveq   #0,%d3
        move.b  2(%a1,%d5.l),%d3        | velocity; 0 or a 0x8n status: off
        moveq   #9,%d0
        move.l  %d2,%d4
        lsr.l   #4,%d4
        cmp.l   %d0,%d4
        beq     1f
        moveq   #0,%d3
1:      move.l  36(%sp),%d4             | (len again)
        bsr     .Lm_key                 | d2 = status, d1 = note, d3 = 0 off / on
        addq.l  #3,%d5
        bra     .Lm_msg
.Lm_out:
        movem.l (%sp),%d0-%d5/%a0-%a1
        lea     32(%sp),%sp
        lea     -20(%sp),%sp            | the displaced instructions, then on
        movem.l %d2-%d5/%a2,(%sp)
        jmp     0x40010bd0

| .Lm_key: d2 = status (channel in the low nibble), d1 = note, d3 = 0 off, else on.  For every
| audio track whose machine takes notes and whose MIDI track sends on this channel.  Keeps d1-d5, a1.
.Lm_key:
        lea     -24(%sp),%sp
        movem.l %d1-%d5/%a1,(%sp)
        bsr     mt_curpart
        tst.l   %d1
        beq     .Lk_x
        move.l  (%sp),%d1
        lsl.l   #8,%d1                  | the key, Q8 semitones
        move.l  %d1,%d5
        and.l   #15,%d2
        addq.l  #1,%d2                  | CHAN as the Part stores it
        moveq   #0,%d4                  | the track
.Lk_t:
        moveq   #0x24,%d0
        muls.l  %d4,%d0
        move.l  %a0,%a1
        adda.l  #MIDI_CHAN,%a1
        moveq   #0,%d1
        move.b  (%a1,%d0.l),%d1
        cmp.l   %d2,%d1
        bne     .Lk_n
        move.l  %d4,%d0
        bsr     mt_sig                  | d0 = 1 + the machine on audio track d4 (keeps a0)
        beq     .Lk_n
        lsl.l   #4,%d0
        lea     mt_voices-16,%a1
        move.l  8(%a1,%d0.l),%d1        | its notes: how many keys it holds
        beq     .Lk_n
        bsr     .Lk_one
.Lk_n:
        addq.l  #1,%d4
        moveq   #8,%d0
        cmp.l   %d0,%d4
        blt     .Lk_t
.Lk_x:
        movem.l (%sp),%d1-%d5/%a1
        lea     24(%sp),%sp
        rts
| .Lk_one: d4 = audio track, d1 = its key count, d5 = the key (Q8), d3 = on.  Clobbers d0, d1, a1.
.Lk_one:
        move.l  %d2,-(%sp)
        move.l  %d4,%d0
        lsl.l   #4,%d0
        lea     mt_keys,%a1
        add.l   %d0,%a1                 | the track's keys
        moveq   #0,%d2                  | held before
        move.l  %d1,%d0
1:      tst.l   (%a1)+
        beq     2f
        addq.l  #1,%d2
2:      subq.l  #1,%d0
        bne     1b
        lea     -4(%a1),%a1             | (back to the start below)
        move.l  %d1,%d0
        lsl.l   #2,%d0
        suba.l  %d0,%a1
        lea     4(%a1),%a1
        tst.l   %d3
        beq     .Lk_off
        move.l  %d1,%d0                 | on: the first free key (a full chord ignores it)
3:      tst.l   (%a1)
        beq     4f
        addq.l  #4,%a1
        subq.l  #1,%d0
        bne     3b
        bra     .Lk_done
4:      move.l  %d5,(%a1)
        tst.l   %d2
        bne     .Lk_done
        moveq   #0x1d,%d0               | the first key down: START
        bra     .Lk_post
.Lk_off:
        move.l  %d1,%d0                 | off: the key holding this note
5:      cmp.l   (%a1),%d5
        beq     6f
        addq.l  #4,%a1
        subq.l  #1,%d0
        bne     5b
        bra     .Lk_done
6:      clr.l   (%a1)
        subq.l  #1,%d2
        bne     .Lk_done
        moveq   #0x40,%d0               | the last key up: release
.Lk_post:
        lea     VCMD,%a1
        move.l  %d0,(%a1,%d4.l*4)
.Lk_done:
        move.l  (%sp)+,%d2
        rts
