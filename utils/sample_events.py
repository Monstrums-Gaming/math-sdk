"""Emit a small, human-readable events sample from a build's final book file.

Prod builds write ``books_<mode>.jsonl.zst`` (zstd-compressed, unreadable) and dev builds write
the full run uncompressed — neither is a convenient sample for a frontend/game dev who just
wants to see the per-round event stream. ``write_sample_events`` slices a coverage-first sample
(one round per distinct ``criteria`` so rare outcomes like ``wincap`` always appear, then filled
sequentially up to the limit) and writes it as readable JSON.

Reads whichever final book file the build produced (``.jsonl.zst`` / ``.json`` / ``.jsonl``) and
reuses ``utils.format_books_json.format_json_with_compact_names`` for the readable formatting.
"""

import io
import json
import os

import zstandard as zstd

from utils.format_books_json import format_json_with_compact_names


def read_books(path: str) -> list:
    """Load a final book file into a list of book dicts, regardless of on-disk format."""
    if path.endswith(".zst"):
        books = []
        decompressor = zstd.ZstdDecompressor()
        with open(path, "rb") as f:
            with decompressor.stream_reader(f) as reader:
                for line in io.TextIOWrapper(reader, encoding="utf-8"):
                    if line.strip():
                        books.append(json.loads(line))
        return books

    with open(path, "r", encoding="utf-8") as f:
        if path.endswith(".jsonl"):
            return [json.loads(line) for line in f if line.strip()]
        return json.load(f)  # a plain ``.json`` array of books


def coverage_sample(books: list, limit: int) -> list:
    """Pick a coverage-first subset of ``books``, in original order.

    Guarantees one round for each distinct ``criteria`` (so every prize/event shape appears —
    including rare ones like ``wincap`` whose first occurrence may be deep in the run), then
    fills with the earliest remaining rounds up to ``limit``. Output preserves the original
    round order. If there are more distinct criteria than ``limit``, keeps the earliest.
    """
    if limit <= 0:
        return []
    if len(books) <= limit:
        return list(books)

    selected: set[int] = set()
    seen_criteria: set = set()
    for i, book in enumerate(books):
        criteria = book.get("criteria")
        if criteria not in seen_criteria:
            seen_criteria.add(criteria)
            selected.add(i)

    if len(selected) > limit:
        # More distinct criteria than the sample limit — keep the earliest `limit` of them.
        selected = set(sorted(selected)[:limit])
    else:
        # Fill with the earliest rounds not already picked, until we reach the limit.
        i = 0
        while len(selected) < limit and i < len(books):
            selected.add(i)
            i += 1

    return [books[i] for i in sorted(selected)]


def write_sample_events(final_book_path: str, out_path: str, limit: int = 100) -> int:
    """Read the final book file, coverage-sample it, and write readable JSON to ``out_path``.

    Returns the number of rounds written.
    """
    books = read_books(final_book_path)
    selected = coverage_sample(books, limit)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(format_json_with_compact_names(selected))
    return len(selected)
