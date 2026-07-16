"""Emit a small, human-readable events sample from a build's final book file.

Prod builds write ``books_<mode>.jsonl.zst`` (zstd-compressed, unreadable) and dev builds write
the full run uncompressed — neither is a convenient sample for a frontend/game dev who just
wants to see the per-round event stream. ``write_sample_events`` slices a coverage-first sample
(one round per distinct ``criteria`` so rare outcomes like ``wincap`` always appear, then filled
sequentially up to the limit) and writes it as readable JSON.

Reads whichever final book file the build produced (``.jsonl.zst`` / ``.json`` / ``.jsonl``) and
reuses ``utils.format_books_json.format_json_with_compact_names`` for the readable formatting.

The selection streams the book file in a single pass, retaining only the ``limit`` sampled rounds
(plus one book per distinct ``criteria``) rather than the whole file — so peak memory is O(limit),
independent of ``num_sims``. A 1M-sim build samples in ~440 MB instead of ~3 GB.
"""

import io
import json
import os

import zstandard as zstd

from utils.format_books_json import format_json_with_compact_names


def iter_books(path: str):
    """Yield book dicts from a final book file one at a time, regardless of on-disk format.

    ``.jsonl.zst`` and ``.jsonl`` stream line-by-line (constant memory). A plain ``.json`` array
    (uncompressed dev builds only) is not line-delimited, so it still loads in full via ``json.load``.
    """
    if path.endswith(".zst"):
        decompressor = zstd.ZstdDecompressor()
        with open(path, "rb") as f:
            with decompressor.stream_reader(f) as reader:
                for line in io.TextIOWrapper(reader, encoding="utf-8"):
                    if line.strip():
                        yield json.loads(line)
    elif path.endswith(".jsonl"):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    yield json.loads(line)
    else:  # a plain ``.json`` array of books (dev, uncompressed) — no line framing to stream on
        with open(path, "r", encoding="utf-8") as f:
            for book in json.load(f):
                yield book


def _coverage_select(book_iter, limit: int) -> list:
    """Coverage-first subset of a book stream, in original order, holding only what it keeps.

    Guarantees one round for each distinct ``criteria`` (so every prize/event shape appears —
    including rare ones like ``wincap`` whose first occurrence may be deep in the run), then
    fills with the earliest remaining rounds up to ``limit``. Output preserves the original
    round order. If there are more distinct criteria than ``limit``, keeps the earliest.

    Streams ``book_iter`` once, retaining at most ``limit`` head rounds plus one round per distinct
    criteria — so memory is bounded by the sample size, not the run length. Equivalent to the old
    load-everything ``coverage_sample`` but without materializing the full book list.
    """
    if limit <= 0:
        return []

    head: list = []        # the first `limit` rounds (indices 0..limit-1) — fill candidates
    crit: dict = {}        # criteria -> (index, book), first occurrence only
    n = 0
    for book in book_iter:
        if n < limit:
            head.append(book)
        criteria = book.get("criteria")
        if criteria not in crit:
            crit[criteria] = (n, book)
        n += 1

    if n <= limit:
        return head  # kept every round; already in order

    crit_indices = sorted(idx for idx, _ in crit.values())
    if len(crit_indices) > limit:
        # More distinct criteria than the sample limit — keep the earliest `limit` of them.
        selected = set(crit_indices[:limit])
    else:
        selected = set(crit_indices)
        # Fill with the earliest rounds not already picked, until we reach the limit. Fill indices
        # are always < limit, so the round is available in `head`.
        i = 0
        while len(selected) < limit and i < n:
            selected.add(i)
            i += 1

    books_by_index = {i: book for i, book in enumerate(head)}  # covers indices 0..limit-1
    for idx, book in crit.values():
        books_by_index[idx] = book  # covers any deep first-occurrence index >= limit
    return [books_by_index[i] for i in sorted(selected)]


def coverage_sample(books: list, limit: int) -> list:
    """Coverage-first subset of an in-memory book list (see ``_coverage_select``)."""
    return _coverage_select(iter(books), limit)


def write_sample_events(final_book_path: str, out_path: str, limit: int = 100) -> int:
    """Stream the final book file, coverage-sample it, and write readable JSON to ``out_path``.

    Returns the number of rounds written. Peak memory is O(limit), not O(num_sims).
    """
    selected = _coverage_select(iter_books(final_book_path), limit)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(format_json_with_compact_names(selected))
    return len(selected)
