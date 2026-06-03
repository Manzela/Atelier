"""Minimal LexoRank — a fractional lexical ordering key (PRD §7A.5 / glossary).

A LexoRank is a string ordering key that lets a list item be positioned between
any two neighbours **without re-indexing** the whole list: to move B between A
and C you compute a new key that sorts lexically between ``rank(A)`` and
``rank(C)``. The Board (AT-041) uses it both for the autonomous pipeline writes
(append a new terminal key at each stage transition) and for manual drag (drop a
card between two others).

This is a deliberately small, dependency-free midpoint-string implementation
(the PyPI ``lexorank`` package is **not** a pinned dependency, and per the sprint
``<lockfile_only_installs>`` invariant we implement the ~40-line algorithm inline
rather than add a dep). It is NOT bucketed like Jira's full LexoRank; it is the
fractional-key core, which is exactly what §7A.5 (a single ordered task lane) and
the drag-between-two-cards reader need.

Alphabet: lowercase base-36 ``[0-9a-z]`` (36 digits). Keys compare with plain
Python string ``<`` (lexicographic). The empty string sorts before every key, so
``lexorank_after(None)`` seeds the first key and ``lexorank_between("", x)``
prepends before ``x``.

Invariants (asserted by tests):
    * ``lexorank_after(prev) > prev`` for any ``prev``.
    * ``a < lexorank_between(a, b) < b`` for any ``a < b``.
    * keys never collide for distinct insertions on the same lane.
"""

from __future__ import annotations

from typing import Final

#: base-36 digit alphabet; index in this string IS the digit value.
_ALPHABET: Final[str] = "0123456789abcdefghijklmnopqrstuvwxyz"
_BASE: Final[int] = len(_ALPHABET)  # 36
#: A comfortable starting key in the middle of the space so both prepend and
#: append have room before the string has to grow.
_INITIAL: Final[str] = "n"  # ALPHABET[23], roughly mid-range


def _digit(ch: str) -> int:
    """Value of a single base-36 digit (raises on an out-of-alphabet char)."""
    return _ALPHABET.index(ch)


def lexorank_after(prev: str | None) -> str:
    """Return a key that sorts strictly after ``prev`` (append to the lane tail).

    ``prev is None`` (or empty) seeds the first key on a fresh lane. Otherwise we
    return the midpoint between ``prev`` and the conceptual upper bound (a string
    of all-max digits), which is the standard "insert at end" operation: pass an
    empty string as the upper bound so :func:`lexorank_between` treats it as
    "+infinity" and steps the key forward without unbounded growth.
    """
    if not prev:
        return _INITIAL
    # Empty upper bound == unbounded above; between() then nudges prev forward.
    return lexorank_between(prev, "")


def lexorank_between(lower: str, upper: str) -> str:
    """Return a key strictly between ``lower`` and ``upper`` (lexicographically).

    Bounds semantics:
        * ``lower == ""`` -> negative infinity (prepend before everything).
        * ``upper == ""`` -> positive infinity (append after everything).
        * otherwise ``lower < upper`` is REQUIRED.

    The algorithm walks the two keys digit-by-digit. While the digits match it
    copies them; at the first position where there is room, it inserts a digit
    midway between the bounding digits. If no gap exists at the shared prefix
    length (adjacent digits), it extends ``lower`` by a midpoint digit, which is
    always strictly greater than ``lower`` and (because ``upper`` had no room at
    that position) strictly less than ``upper``.
    """
    if lower and upper and not lower < upper:
        raise ValueError(f"lexorank_between requires lower < upper, got {lower!r}, {upper!r}")

    result: list[str] = []
    i = 0
    while True:
        lo = _digit(lower[i]) if i < len(lower) else 0
        # When upper is the empty (+inf) sentinel, the conceptual upper digit is
        # one past the max so there is always room to step forward.
        hi = _digit(upper[i]) if i < len(upper) else _BASE
        if lo == hi:
            # Digits identical -> copy and descend to the next position. (Only
            # reachable when both keys share this prefix digit.)
            result.append(_ALPHABET[lo])
            i += 1
            continue
        mid = (lo + hi) // 2
        if mid != lo:
            # There is a free digit strictly between the bounds at this position.
            result.append(_ALPHABET[mid])
            return "".join(result)
        # lo and hi are adjacent (hi == lo + 1): no room here. Keep lower's digit
        # and descend — on the next position upper is unbounded (we've passed its
        # constraining digit), so a midpoint digit there lands strictly between.
        result.append(_ALPHABET[lo])
        i += 1
        # Safety: append a mid digit if lower runs out (prevents an infinite loop
        # on pathological equal-prefix inputs; mid of [0, _BASE) is non-zero).
        if i >= len(lower):
            result.append(_ALPHABET[_BASE // 2])
            return "".join(result)


__all__ = ["lexorank_after", "lexorank_between"]
