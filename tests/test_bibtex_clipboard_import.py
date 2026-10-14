"""Importing BibTeX straight from the clipboard.

A publisher's "cite this" button and Google Scholar both hand over
BibTeX as *text*, and the old path made the user save it to a file
first. `import_bib_text` takes the string, so the paste is the
import.

The string is the only new thing: everything downstream of the parse
is the `.bib` path, so these tests check the string reaches it
intact, that the file path still behaves, and that the "is this even
BibTeX?" gate the clipboard handler puts in front of it answers
correctly — including for a filename, which `bibtex.parse` would
otherwise read off disk.

No network: fetch_metrics is monkeypatched.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from alexandria import bibtex_import, index, sidecar

ONE_ENTRY = """@article{emsley2004features,
  title   = {Features and development of Coot},
  author  = {Emsley, Paul and Cowtan, Kevin},
  journal = {Acta Crystallographica Section D},
  year    = {2004},
  doi     = {10.1107/S0907444904019158}
}
"""

TWO_ENTRIES = ONE_ENTRY + """
@article{jumper2021highly,
  title   = {Highly accurate protein structure prediction with AlphaFold},
  author  = {Jumper, John},
  journal = {Nature},
  year    = {2021}
}
"""


def _library(tmp_path, monkeypatch):
    """A fresh library with enrichment stubbed out."""
    monkeypatch.setattr(bibtex_import.metrics, "fetch_metrics",
                        lambda doi: (None,) * 12)
    root = str(tmp_path)
    conn = index.open_db(os.path.join(root, "db.sqlite3"))
    return conn, root


# ---- the paste itself -------------------------------------------------

def test_a_pasted_entry_becomes_a_ghost(tmp_path, monkeypatch):
    conn, root = _library(tmp_path, monkeypatch)

    counts = bibtex_import.import_bib_text(conn, ONE_ENTRY, root)

    assert counts["ghost"] == 1
    assert counts["error"] == 0
    rec = sidecar.read(
        sidecar.ghost_sidecar_path(root, "emsley2004features"))
    assert rec["title"] == "Features and development of Coot"
    assert rec["authors"] == ["Paul Emsley", "Kevin Cowtan"]
    assert rec["year"] == 2004


def test_every_pasted_entry_arrives(tmp_path, monkeypatch):
    conn, root = _library(tmp_path, monkeypatch)

    counts = bibtex_import.import_bib_text(conn, TWO_ENTRIES, root)

    assert counts["ghost"] == 2
    assert conn.execute(
        "SELECT COUNT(*) FROM papers WHERE pdf_path LIKE 'bibtex:%'"
    ).fetchone()[0] == 2


def test_progress_is_reported_per_entry(tmp_path, monkeypatch):
    conn, root = _library(tmp_path, monkeypatch)
    seen = []

    bibtex_import.import_bib_text(
        conn, TWO_ENTRIES, root,
        on_progress=lambda i, n, key, status: seen.append((i, n, key)))

    assert seen == [(1, 2, "emsley2004features"),
                    (2, 2, "jumper2021highly")]


def test_pasting_the_same_entry_twice_is_a_duplicate(
        tmp_path, monkeypatch):
    conn, root = _library(tmp_path, monkeypatch)

    bibtex_import.import_bib_text(conn, ONE_ENTRY, root)
    counts = bibtex_import.import_bib_text(conn, ONE_ENTRY, root)

    assert counts["duplicate"] == 1
    assert counts["ghost"] == 0


def test_nothing_to_import_is_not_an_error(tmp_path, monkeypatch):
    """A string the parser finds no entries in imports nothing and
    says so with zeroes — the window turns that into "No BibTeX
    entries found" rather than reporting a failure."""
    conn, root = _library(tmp_path, monkeypatch)

    counts = bibtex_import.import_bib_text(conn, "not bibtex at all", root)

    assert counts == {"imported": 0, "ghost": 0, "duplicate": 0,
                      "error": 0, "renamed": []}


# ---- the file path still works ---------------------------------------

def test_import_bib_still_reads_a_file(tmp_path, monkeypatch):
    conn, root = _library(tmp_path, monkeypatch)
    path = os.path.join(root, "refs.bib")
    with open(path, "w", encoding="utf-8") as f:
        f.write(TWO_ENTRIES)

    counts = bibtex_import.import_bib(conn, path, root)

    assert counts["ghost"] == 2


# ---- the gate in front of the clipboard ------------------------------

def test_bibtex_is_recognised():
    assert bibtex_import.looks_like_bibtex(ONE_ENTRY)
    assert bibtex_import.looks_like_bibtex("@misc{k, title={x}}")
    assert bibtex_import.looks_like_bibtex("@Book (k, title={x})")
    # Whatever else was copied along with it doesn't disqualify it.
    assert bibtex_import.looks_like_bibtex(
        "Cite this paper:\n" + ONE_ENTRY)


def test_other_clipboard_contents_are_not_bibtex():
    assert not bibtex_import.looks_like_bibtex("")
    assert not bibtex_import.looks_like_bibtex(None)
    assert not bibtex_import.looks_like_bibtex("   \n ")
    assert not bibtex_import.looks_like_bibtex(
        "10.1107/S0907444904019158")
    assert not bibtex_import.looks_like_bibtex("you@example.com")


def test_a_copied_filename_is_not_bibtex(tmp_path):
    """The gate's other job: `bibtex.parse` reads a lone filename off
    disk, so a path on the clipboard must not pass as BibTeX."""
    path = str(tmp_path / "refs.bib")
    with open(path, "w", encoding="utf-8") as f:
        f.write(ONE_ENTRY)

    assert not bibtex_import.looks_like_bibtex(path)


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
