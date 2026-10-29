"""The machine table's flags a machine's remix.inc carries (modules/machines).

MT_CLIENT is 1 when the remix carries the table: the machine is then one of
its rows (MT_ROW) and hands the tracks not its own to MT_NEXT; alone, 0 and
the machine's own bytes. Called from a machine's Linked.include at build
time, not when manifests load.
"""
import functools
import pathlib
import runpy

ROOT = pathlib.Path(__file__).resolve().parents[2]


@functools.cache
def _table():
    return runpy.run_path(str(ROOT / "modules/machines/manifest.py"))


def inc(key, modules) -> str:
    """remix.inc lines for machine `key` in a selection of module keys."""
    return _table()["flags_inc"](key, modules)
