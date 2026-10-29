"""MACHINES -- the machine table: one owner for every stock site a machine row needs.

A track machine is a sixth (seventh, ...) row of the track's machine list. Before
this table each machine took the sites itself -- ANALOG BD's seams, copied by
OCTA303 -- so two machines could share an image only through a hand-written
bridge (HOOKS's machine_rows, retired here). Now a machine declares
schema.Machine in its manifest and claims none of these sites; the build
generates the table's rows and dispatch from the declarations
(docs/contributing/MACHINES.md):

  * the list: the name formatter 0x400334d8, SRC SETUP's names (the lea at
    0x4003c928) and the main pages' name lookups 0x4003d718 / 0x4004c36a; the
    lists' row counts, SRC SETUP's name bound, the commit's persist bound and
    the five key handlers' cursor clamps (trap-machine-clamp), and the drawer's
    two row tests 0x40078678 / 0x400786c8 so the list scrolls;
  * a track's row: the opens 0x400585dc / 0x40078886, SRC SETUP's highlight
    0x4003c980 -- each asks mt_type, which reads a FLEX track signed with a
    machine's two bytes and 1 (Part' + 0x3c + 30 * track) as that machine's row;
  * the commits 0x4007981c, 0x4005a616, 0x4005a850: a machine's row signs the
    track (its defaults on a new track), any other row unsigns it;
  * SETUP's editor and drawer 0x4003a52e / 0x4003cd98 (a machine's SETUP bytes
    are FLEX's; a hidden knob is not edited there);
  * the Part validator 0x40002318 (FLEX's defaults over a machine track's
    twelve bytes for the stock check, then the machine's put back);
  * the page records: the resolver's PLAYBACK case 0x40031e74, the tick
    0x4005221e that publishes each machine's record for the UI track, and every
    reader of stock's record table 0x400d5f38 (PB_LEAS), pointed at the table's
    own: stock's has seven rows and its eighth word is the FX1 table's;
  * the FLEX renderer entry 0x400d6438: a machine's voice (`frame`) is
    rendered by the table; `render` machines chain;
  * the note input, the MIDI send primitive 0x40010bc8 (notes.s), when a
    machine takes notes.

Installed only when needed (SHARED_HOOKS.md 4.1): a remix with no machine gets
nothing. ANALOG BD and OCTA303 were proven on units with their own claims, so
either alone keeps them and its bytes; the table installs when a remix carries
two machines, or any machine with no claims of its own (POLY, LADDER, GRAINER).
Then each machine's claim on an owned site is overridden (schema.Override), and
its remix.inc says MT_CLIENT 1, its row and its MT_NEXT renderer (flags_inc).
"""

import os

from remix.schema import Category, Detour, Gate, Kind, Linked, Module, Override, Poke, Proof, SymbolRef

H = bytes.fromhex
_HERE = os.path.relpath(os.path.dirname(os.path.realpath(__file__)))
STOCK_RENDER = 0x40004008
FMT_PLAIN = 0x4003C178                  # stock fmt(buf, value) -> "%d"

# ---- the owned sites (site, stock bytes, symbol, kind, pad) ---------------------------
DETOURS = (
    (0x400334D8, H("2f02222f0008"), "mt_name", "jmp", None, "the machine list's names: a machine's row its name"),
    (0x4003C928, H("4bf9400a78c8"), "mt_src_names", "lea", None, "SRC SETUP's names: stock's five, then the machines'"),
    (0x4003D718, H("41f9400a78c8"), "mt_name_a", "jmp", None, "main page name lookup: a machine track's name"),
    (0x4004C36A, H("41f9400a78c8"), "mt_name_b", "jmp", None, "second main page name lookup"),
    (0x4003C980, H("71104fef0018"), "mt_setup_row", "jmp", None, "SRC SETUP highlights a machine track's row"),
    (0x400585DC, H("161079034879400bb704"), "mt_setup_open", "jmp", 10, "SRC SETUP opens on a machine track's row"),
    (0x4005221E, H("4ebaff1c4eb94007e940"), "mt_tick", "jmp", 10, "each machine's record for the UI track, by row"),
    (0x40078886, H("71102f004879460e7386"), "mt_chooser_open", "jmp", 10, "the machine list opens on a machine track's row"),
    (0x4007981C, H("77101084d081"), "mt_main_commit", "jmp", None, "the machine list's commit: a machine's row signs the track"),
    (0x4005A616, H("2239460d5c30"), "mt_src_commit", "jmp", None, "SRC SETUP's commit: the same"),
    (0x4005A850, H("2239460d5c30"), "mt_src_commit2", "jmp", None, "SRC SETUP's second commit path"),
    (0x4003A52E, H("2002e788d4829082"), "mt_setup_edit6", "jmp", 8, "SETUP's editor: a machine's bytes are FLEX's"),
    (0x4003CD98, H("2e06e78fdc869e86"), "mt_setup_draw6", "jmp", 8, "SETUP's drawer: the same"),
    (0x40002318, H("4fefffa048d77cfc"), "mt_validate", "jmp", 8, "the Part validator sees FLEX's defaults on a machine track"),
    (0x40031E74, H("710541f9400d5f386050"), "mt_resolve", "jmp", 10, "the page resolver: a machine track's record"),
    (0x40078678, H("7004b0826d24"), "mt_mc_name", "jmp", 6, "the list scrolls: row top + d2 on screen row d2"),
    (0x400786C8, H("7110b480662e7004b0826d28"), "mt_mc_box", "jmp", 12, "the list scrolls: the stored row's box"),
)
NOTE_SITE = (0x40010BC8, H("4fefffec48d7043c"), "mt_midi", "jmp", 8,
             "every MIDI message the unit sends: a MIDI track's notes play its audio track's machine")
KIND_FLEX = 0x400D6438                   # the kind table's FLEX renderer
# Every `lea 0x400d5f38,a0` but the resolver's (owned above): the SETUP editor, the SRC SETUP
# list (indexed by its cursor, a row), the main page, SRC SETUP's open. The operand words.
PB_LEAS = (0x4003A526, 0x4003C8CC, 0x4003D136, 0x400585EC)
PB_TABLE = 0x400D5F38
CLAMPS = (0x40078C22, 0x40078CB0, 0x40078D2E, 0x40078DEE, 0x40078E7C)


def _pokes(n):
    rows = 5 + n
    return (
        Poke(0x40079248, H("48780005"), bytes((0x48, 0x78, 0, rows)), "the machine list's rows"),
        Poke(0x400585FA, H("48780005"), bytes((0x48, 0x78, 0, rows)), "SRC SETUP's selector rows"),
        Poke(0x4003C950, H("7204"), bytes((0x72, rows - 1)), "SRC SETUP's name lookup admits every machine row"),
        Poke(0x40079904, H("7604"), bytes((0x76, rows - 1)), "the list's commit persists every machine row"),
    ) + tuple(
        # the list's five key handlers clamp the cursor to 0..5 after moving
        # (`moveq #5,%d1 ; cmp.l %d0,%d1 ; bge.s ; moveq #5,%d0`): trap-machine-clamp
        Poke(at + off, bytes((op, 5)), bytes((op, rows - 1)), "the list's cursor reaches the last machine")
        for at in CLAMPS for off, op in ((0, 0x72), (6, 0x70)))


def _owned_spans(n, notes):
    spans = [(s, max(len(e), p or 0, 6)) for s, e, _y, _k, p, _n in DETOURS]
    if notes:
        spans.append((NOTE_SITE[0], 8))
    spans += [(KIND_FLEX, 4)] + [(a, 4) for a in PB_LEAS] + [(p.addr, len(p.write)) for p in _pokes(n)]
    return spans


# ---- the declarations -----------------------------------------------------------------
def _known():
    from remix import registry
    return registry.modules()


def machines(modules):
    """[(module key, schema.Machine)] for a selection, in row order (5, 6, ...): by key,
    so a machine's row does not depend on how a remix lists its modules."""
    known = _known()
    return [(k, known[k].machine) for k in sorted(modules)
            if k in known and getattr(known[k], "machine", None) is not None]


def _standalone(key):
    """Does this machine carry claims of its own on the table's sites (proven alone)?"""
    m = _known()[key]
    return any(s <= d.site < s + n for d in m.detours for s, n in _owned_spans(0, False))


def needed(modules) -> bool:
    ms = machines(modules)
    return len(ms) >= 2 or any(not _standalone(k) for k, _m in ms)


def _row(modules, key):
    return 5 + [k for k, _m in machines(modules)].index(key)


def _next_render(ms, i):
    """The renderer after render machine i in the chain (stock's after the last)."""
    later = [m.render for _k, m in ms[i + 1:] if m.render]
    return later[0] if later else f"0x{STOCK_RENDER:08x}"


def flags_inc(key, modules) -> str:
    """remix.inc lines for a machine module `key`: MT_CLIENT 1 when the table is on, its row
    and the renderer its own hands other tracks to (MT_NEXT); MT_CLIENT 0 alone."""
    if not needed(modules):
        return ".set MT_CLIENT, 0\n"
    ms = machines(modules)
    i = [k for k, _m in ms].index(key)
    return f".set MT_CLIENT, 1\n.set MT_ROW, {5 + i}\n.set MT_NEXT, {_next_render(ms, i)}\n"


def _asciz(s, n):
    """s NUL-padded to n bytes as .byte (the page's fixed fields)."""
    b = s.encode() + b"\0" * (n - len(s))
    return ".byte " + ", ".join(str(x) for x in b)


def _fmt(k):
    v = FMT_PLAIN if k.fmt is None else k.fmt
    return f"0x{v:08x}" if isinstance(v, int) else v


def table_inc(modules, remix=None):
    """remix.inc for table.s: the rows, their dispatch and the records it builds."""
    ms = machines(modules)
    frames = [m for _k, m in ms if m.frame]
    renders = [m.render for _k, m in ms if m.render]
    out = [f".set MT_N, {len(ms)}", f".set MT_FRAMES, {int(bool(frames))}",
           f".set MT_NOTES, {int(any(m.notes for _k, m in ms))}",
           f".set MT_RENDER_NEXT, {renders[0] if renders else f'0x{STOCK_RENDER:08x}'}"]
    def mac(name, lines):
        out.extend([f".macro {name}", *lines, ".endm"])
    mac("mt_sig_words", [f"    .short 0x{ord(m.sig[0]) << 8 | ord(m.sig[1]):04x}   | {m.sig}: {m.name}" for _k, m in ms])
    mac("mt_title_longs", [f"    .long mt_t{i}" for i in range(len(ms))])
    mac("mt_strings", [f"mt_t{i}: .asciz \"{m.name}\"" for i, (_k, m) in enumerate(ms)])
    mac("mt_hidden_bytes", [f"    .byte 0x{sum(1 << j for j in range(6) if not m.knobs[6 + j].count):02x}"
                            for _k, m in ms])
    mac("mt_record_longs", [f"    .long {m.record or f'mt_rec{i}'}" for i, (_k, m) in enumerate(ms)])
    mac("mt_defaults", ["    .byte " + ", ".join(str(k.default) for k in m.knobs) for _k, m in ms])
    mac("mt_voice_longs", [f"    .long {m.frame or 0}, {m.state}, {m.notes}, mt_st{i}"
                           for i, (_k, m) in enumerate(ms)])
    mac("mt_voice_state", [f"mt_st{i}: .fill {m.state * 8 if m.frame else 4}, 1, 0"
                           for i, (_k, m) in enumerate(ms)])
    built = []
    for i, (_k, m) in enumerate(ms):
        if m.record:
            continue
        built += [f"mt_rec{i}:", f"    move.l #mt_buf{i},%d0", f"    lea mt_patch{i},%a1", "    bra mt_build",
                  "    .align 4", f"mt_patch{i}:"]
        fields = ((0x004, 5, f"mt_abbr{i}"), (0x009, 13, f"mt_title{i}"), (0x016, 72, f"mt_names{i}"),
                  (0x05E, 12, f"mt_defs{i}"), (0x06A, 48, "mt_zero48"), (0x09A, 48, f"mt_cnt{i}"),
                  (0x0CA, 48, f"mt_fmts{i}"), (0x0FA, 48, "mt_zero48"), (0x12A, 4, "mt_zero48"),
                  (0x142, 24, "mt_zero48"), (0x18A, 8, "mt_flags"))
        built += [f"    .short 0x{o:03x}, {n}\n    .long {src}" for o, n, src in fields]
        built += ["    .short -1, 0", "    .long 0",
                  f"mt_abbr{i}: {_asciz(m.short, 5)}", f"mt_title{i}: {_asciz(m.name, 13)}",
                  f"mt_names{i}: " + "\n    ".join(_asciz(k.name, 6) for k in m.knobs),
                  f"mt_defs{i}: .byte " + ", ".join(str(k.default) for k in m.knobs),
                  "    .align 4",
                  f"mt_cnt{i}: .long " + ", ".join(str(k.count) for k in m.knobs),
                  f"mt_fmts{i}: .long " + ", ".join(_fmt(k) for k in m.knobs),
                  f"mt_buf{i}: .fill 0x194, 1, 0"]      # the record, its made flag, padding
    if built:
        built += ["    .align 4", "mt_zero48: .fill 48, 1, 0",
                  "mt_flags: .long 0x00001111, 0x11311311"]   # SETUP's six plain, PLAYBACK's as FLEX's (OCTA303's)
    mac("mt_built", built)
    return "\n".join(out) + "\n"


def _units(modules):
    """The table's unit, and each `fmt` symbol and voice its machines name (defsyms none:
    they are linked units of the machines' own modules)."""
    return (Linked("machines", os.path.join(_HERE, "table.s"), dram=True, include=table_inc),)


def select(modules):
    """The table's claims for a selection: nothing without a machine that needs it."""
    if not needed(modules):
        return {"linked": (), "detours": (), "symbol_refs": (), "overrides": (), "pokes": ()}
    ms = machines(modules)
    notes = any(m.notes for _k, m in ms)
    detours = [Detour(s, e, "machines", y, n, kind=k, pad_to=p) for s, e, y, k, p, n in DETOURS]
    if notes:
        s, e, y, k, p, n = NOTE_SITE
        detours.append(Detour(s, e, "machines", y, n, kind=k, pad_to=p))
    refs = [SymbolRef(KIND_FLEX, STOCK_RENDER, "machines", "mt_render",
                      "FLEX renderer: the machine table's (a machine's voice, then each render machine's)")]
    refs += [SymbolRef(a, PB_TABLE, "machines", "mt_pages", "the PLAYBACK records by row: the table's")
             for a in PB_LEAS]
    pokes = _pokes(len(ms))
    spans = _owned_spans(len(ms), notes)
    known = _known()
    overrides = []
    for key, _m in ms:
        mod = known[key]
        claims = ([(d.site, max(len(d.expect), d.pad_to or 0, 6)) for d in mod.detours]
                  + [(r.addr, 4) for r in mod.symbol_refs] + [(p.addr, len(p.write)) for p in mod.pokes])
        overrides += [Override(a, key) for a, n in claims
                      if any(a < s + sn and s < a + n for s, sn in spans)]
    return {"linked": _units(modules), "detours": tuple(detours), "symbol_refs": tuple(refs),
            "overrides": tuple(overrides), "pokes": pokes}


MODULE = Module(
    name="machines",
    key="MACHINES",
    kind=Kind.CF_PATCH,
    category=Category.SETTINGS, author="Robin Baeckman", author_url="https://github.com/RobinBaeckman",
    proof=Proof.PORT, proof_note="verify_machines: the table under Unicorn and each machine's UI gate on one image",
    doc="Platform: the machine table. Every machine row's stock sites, owned once; machines join by declaring schema.Machine.",
    select=select,
    gates=(Gate("tools/verify/verify_machines.py", once=True, venv=True),),
)
