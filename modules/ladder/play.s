| LADDER on the machine table (modules/machines): the table's frame call,
|   void ladder_play(struct state *st, const uint8_t pv[12], const int32_t keys[1], int32_t out[32])
| is ladder_frame with the held key as its note and its mono output copied to R.  The table zeroes
| a track's state when it joins the machine; a zero state is not the voice's start (ST_TGT is
| NONE before the first note), so the long after the voice's state marks it made.
        .text
        .global ladder_play
        .set    ST_TGT, 28
        .set    ST_MADE, 52             | past the voice's 13 longs
        .set    NONE, 0x80000000
ladder_play:
        move.l  4(%sp),%a0
        tst.l   ST_MADE(%a0)
        bne.s   1f
        move.l  #NONE,%d0
        move.l  %d0,ST_TGT(%a0)
        moveq   #1,%d0
        move.l  %d0,ST_MADE(%a0)
1:      move.l  16(%sp),-(%sp)          | out
        move.l  16(%sp),%a0             | keys
        move.l  (%a0),-(%sp)            | note8 = the held key
        move.l  16(%sp),-(%sp)          | pv
        move.l  16(%sp),-(%sp)          | st
        jsr     ladder_frame
        lea     16(%sp),%sp
        move.l  16(%sp),%a0
        lea     64(%a0),%a1
        moveq   #16,%d0
2:      move.l  (%a0)+,(%a1)+
        subq.l  #1,%d0
        bne.s   2b
        rts
