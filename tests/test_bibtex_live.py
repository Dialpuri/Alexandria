"""The `.bib` that keeps itself in step with the library.

What a LaTeX author wants from this is narrow and unforgiving: the
file must be complete, must be readable at every instant (LaTeX may
be mid-read when a paper imports), and must not look modified when it
isn't — `latexmk -pvc` watches mtimes and would rebuild forever.

The tests below are each one of those promises.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from alexandria import bibtex_live, index, sidecar


def _paper(tmp_path, name, record):
    """Put a paper in the library: a PDF, its sidecar, an index row."""
    pdf = str(tmp_path / (name + ".pdf"))
    with open(pdf, "wb") as f:
        f.write(b"%PDF-1.4\n")
    sc = sidecar.sidecar_path_for(pdf)
    sidecar.write(sc, record)
    return pdf, sc


def _library(tmp_path, papers):
    db = str(tmp_path / "lib.db")
    conn = index.open_db(db)
    for name, record in papers:
        pdf, sc = _paper(tmp_path, name, record)
        index.upsert(conn, pdf, sc, None, record, os.path.getmtime(sc))
    return conn


_EMSLEY = {"title": "Features and development of Coot",
           "authors": ["Paul Emsley", "Kevin Cowtan"],
           "year": 2004, "journal": "Acta Cryst D",
           "doi": "10.1107/s0907444904019158"}
_JUMPER = {"title": "Highly accurate protein structure prediction",
           "authors": ["John Jumper"], "year": 2021,
           "journal": "Nature"}


# ---- what gets written ----------------------------------------------

def test_every_paper_reaches_the_file(tmp_path):
    conn = _library(tmp_path, [("coot", _EMSLEY), ("af2", _JUMPER)])
    out = str(tmp_path / "refs.bib")

    path, written, skipped, changed = bibtex_live.sync(conn, out)

    assert (path, written, skipped, changed) == (out, 2, 0, True)
    text = open(out, encoding="utf-8").read()
    assert "emsley2004features" in text
    assert "jumper2021highly" in text


def test_the_file_says_who_wrote_it(tmp_path):
    """So a user who opens it knows why their edits keep vanishing."""
    conn = _library(tmp_path, [("coot", _EMSLEY)])
    out = str(tmp_path / "refs.bib")
    bibtex_live.sync(conn, out)

    assert open(out, encoding="utf-8").read().startswith(
        bibtex_live.MARKER)


def test_a_library_past_the_search_limit_is_not_truncated(tmp_path):
    """`index.search` stops at 500 rows unless told otherwise, and a
    bibliography silently missing its 501st entry is the worst kind of
    bug — the citation just reads [?] and nobody knows why."""
    papers = [("p{}".format(n),
               {"title": "Paper number {}".format(n),
                "authors": ["Anne Author"], "year": 2000 + (n % 20)})
              for n in range(520)]
    conn = _library(tmp_path, papers)
    out = str(tmp_path / "refs.bib")

    _path, written, _skipped, _changed = bibtex_live.sync(conn, out)

    assert written == 520


def test_a_paper_with_no_sidecar_is_skipped_not_guessed(tmp_path):
    conn = _library(tmp_path, [("coot", _EMSLEY), ("af2", _JUMPER)])
    os.remove(sidecar.sidecar_path_for(str(tmp_path / "af2.pdf")))
    out = str(tmp_path / "refs.bib")

    _path, written, skipped, _changed = bibtex_live.sync(conn, out)

    assert (written, skipped) == (1, 1)


# ---- when it writes, and when it doesn't -----------------------------

def test_an_unchanged_library_does_not_touch_the_file(tmp_path):
    """Otherwise `latexmk -pvc` rebuilds on every sync, forever."""
    conn = _library(tmp_path, [("coot", _EMSLEY)])
    out = str(tmp_path / "refs.bib")
    bibtex_live.sync(conn, out)
    before = os.stat(out).st_mtime_ns

    _path, _written, _skipped, changed = bibtex_live.sync(conn, out)

    assert changed is False
    assert os.stat(out).st_mtime_ns == before


def test_a_new_paper_rewrites_the_whole_file(tmp_path):
    """A rewrite, not an append — see the module docstring for why."""
    conn = _library(tmp_path, [("coot", _EMSLEY)])
    out = str(tmp_path / "refs.bib")
    bibtex_live.sync(conn, out)

    pdf, sc = _paper(tmp_path, "af2", _JUMPER)
    index.upsert(conn, pdf, sc, None, _JUMPER, os.path.getmtime(sc))
    _path, written, _skipped, changed = bibtex_live.sync(conn, out)

    assert changed is True
    assert written == 2
    text = open(out, encoding="utf-8").read()
    assert text.count("@") >= 2
    assert text.count(bibtex_live.MARKER) == 1, "header written twice"


def test_an_edit_corrects_the_entry_already_in_the_file(tmp_path):
    """The case an append-only stream cannot serve: the paper is
    already written out, and the fix has to reach it."""
    conn = _library(tmp_path, [("coot", _EMSLEY)])
    out = str(tmp_path / "refs.bib")
    bibtex_live.sync(conn, out)
    assert "Coot" in open(out, encoding="utf-8").read()

    pdf = str(tmp_path / "coot.pdf")
    sc = sidecar.sidecar_path_for(pdf)
    fixed = dict(_EMSLEY, title="Coot: model-building tools")
    sidecar.write(sc, fixed)
    index.upsert(conn, pdf, sc, None, fixed, os.path.getmtime(sc))
    bibtex_live.sync(conn, out)

    text = open(out, encoding="utf-8").read()
    assert "model-building tools" in text
    assert "Features and development" not in text


def test_nothing_is_written_when_no_file_is_configured(tmp_path,
                                                       monkeypatch):
    """`get_path` is patched rather than passing '' as the path:
    `sync` falls back to the configured file when not given one, so a
    developer who uses the feature themselves would otherwise have
    their own .bib overwritten by this test's fixture library. It
    happened."""
    monkeypatch.setattr(bibtex_live, "get_path", lambda: "")
    conn = _library(tmp_path, [("coot", _EMSLEY)])
    assert bibtex_live.sync(conn) is None


def test_a_missing_parent_folder_is_created(tmp_path):
    conn = _library(tmp_path, [("coot", _EMSLEY)])
    out = str(tmp_path / "thesis" / "chapters" / "refs.bib")

    bibtex_live.sync(conn, out)

    assert os.path.isfile(out)


def test_nothing_is_left_beside_the_file(tmp_path):
    """The write is atomic via a temp sibling; it must not survive,
    and must not be picked up by a `*.bib` glob while it lives."""
    conn = _library(tmp_path, [("coot", _EMSLEY)])
    out = str(tmp_path / "refs.bib")
    bibtex_live.sync(conn, out)

    strays = [n for n in os.listdir(str(tmp_path))
              if "alexandria-tmp" in n]
    assert strays == []


# ---- adopting a file somebody else wrote ------------------------------

def test_a_hand_written_bib_is_recognised_as_foreign(tmp_path):
    out = str(tmp_path / "mine.bib")
    with open(out, "w", encoding="utf-8") as f:
        f.write("@article{smith2020,\n  title = {Mine},\n}\n")

    assert bibtex_live.is_foreign(out) is True


def test_our_own_file_is_not_foreign(tmp_path):
    conn = _library(tmp_path, [("coot", _EMSLEY)])
    out = str(tmp_path / "refs.bib")
    bibtex_live.sync(conn, out)

    assert bibtex_live.is_foreign(out) is False


def test_a_file_that_is_not_there_yet_is_not_foreign(tmp_path):
    """Naming a .bib that doesn't exist is the ordinary case, and
    must not raise a destructive-overwrite warning."""
    assert bibtex_live.is_foreign(str(tmp_path / "nope.bib")) is False
    empty = str(tmp_path / "empty.bib")
    open(empty, "w").close()
    assert bibtex_live.is_foreign(empty) is False


# ---- the trigger -----------------------------------------------------

def test_adding_a_paper_moves_the_change_serial(tmp_path):
    """What the browser window polls. If `upsert` stopped bumping it,
    the .bib would quietly stop updating with nothing to see."""
    conn = _library(tmp_path, [("coot", _EMSLEY)])
    before = index.CHANGE_SERIAL

    pdf, sc = _paper(tmp_path, "af2", _JUMPER)
    index.upsert(conn, pdf, sc, None, _JUMPER, os.path.getmtime(sc))

    assert index.CHANGE_SERIAL != before


def test_removing_a_paper_moves_the_change_serial(tmp_path):
    conn = _library(tmp_path, [("coot", _EMSLEY)])
    before = index.CHANGE_SERIAL

    index.remove(conn, str(tmp_path / "coot.pdf"))

    assert index.CHANGE_SERIAL != before
