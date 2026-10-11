"""Consent to overwrite the live `.bib` is asked about the file, not
about the setting.

`is_foreign` guards the Preferences dialog: choosing a `.bib` that
somebody wrote by hand takes a yes first. But the setting outlives the
file it was made about. Months later the same path can hold a
bibliography someone typed, a different project's references restored
by `git checkout`, or a file replaced wholesale — and the next import
would overwrite it without asking, because the question had been
asked and answered about something that is no longer there.

So `sync` asks again before every write, and `allow_foreign` is the
one exception: at the instant a hand-written file is adopted it is
still foreign, and that first write is the one the user agreed to.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest

from alexandria import bibtex_live, index, sidecar


_EMSLEY = {"title": "Features and development of Coot",
           "authors": ["Paul Emsley", "Kevin Cowtan"],
           "year": 2004, "journal": "Acta Cryst D",
           "doi": "10.1107/s0907444904019158"}


@pytest.fixture
def library(tmp_path):
    """One paper, indexed."""
    pdf = str(tmp_path / "coot.pdf")
    with open(pdf, "wb") as f:
        f.write(b"%PDF-1.4\n")
    sc = sidecar.sidecar_path_for(pdf)
    sidecar.write(sc, _EMSLEY)
    conn = index.open_db(str(tmp_path / "lib.db"))
    index.upsert(conn, pdf, sc, None, _EMSLEY, os.path.getmtime(sc))
    return conn


_BY_HAND = "@article{mine2019, title = {Typed by hand} }\n"


def test_a_file_gone_foreign_is_not_overwritten(library, tmp_path):
    out = str(tmp_path / "refs.bib")
    with open(out, "w", encoding="utf-8") as f:
        f.write(_BY_HAND)

    with pytest.raises(bibtex_live.Foreign):
        bibtex_live.sync(library, out)

    assert open(out, encoding="utf-8").read() == _BY_HAND, (
        "the hand-written bibliography is still there")


def test_the_refusal_says_what_to_do_about_it(library, tmp_path):
    """It reaches the user as a toast, so it has to read as a
    sentence and name the file."""
    out = str(tmp_path / "refs.bib")
    with open(out, "w", encoding="utf-8") as f:
        f.write(_BY_HAND)

    with pytest.raises(bibtex_live.Foreign) as caught:
        bibtex_live.sync(library, out)

    message = str(caught.value)
    assert message.startswith("refs.bib")
    assert "Preferences" in message
    assert "Errno" not in message, "a bare OSError renders as [Errno n]"


def test_a_refusal_is_a_kind_of_oserror(library, tmp_path):
    """Callers already handle the file being unwritable; this is the
    same kind of news and must not slip past them."""
    out = str(tmp_path / "refs.bib")
    with open(out, "w", encoding="utf-8") as f:
        f.write(_BY_HAND)

    with pytest.raises(OSError):
        bibtex_live.sync(library, out)


def test_consent_lets_the_first_write_through(library, tmp_path):
    """What Preferences does after the Overwrite button: the file is
    foreign at that moment, and replacing it is the point."""
    out = str(tmp_path / "refs.bib")
    with open(out, "w", encoding="utf-8") as f:
        f.write(_BY_HAND)

    path, written, skipped, changed = bibtex_live.sync(
        library, out, allow_foreign=True)

    assert (written, skipped, changed) == (1, 0, True)
    text = open(out, encoding="utf-8").read()
    assert text.startswith(bibtex_live.MARKER)
    assert "Typed by hand" not in text


def test_after_that_no_permission_is_needed(library, tmp_path):
    """Our own header is the standing consent, so the import after
    the adoption does not ask again."""
    out = str(tmp_path / "refs.bib")
    with open(out, "w", encoding="utf-8") as f:
        f.write(_BY_HAND)
    bibtex_live.sync(library, out, allow_foreign=True)

    # A second paper, and an ordinary sync with no consent passed.
    pdf = str(tmp_path / "af2.pdf")
    with open(pdf, "wb") as f:
        f.write(b"%PDF-1.4\n")
    sc = sidecar.sidecar_path_for(pdf)
    rec = {"title": "Highly accurate protein structure prediction",
           "authors": ["John Jumper"], "year": 2021,
           "journal": "Nature"}
    sidecar.write(sc, rec)
    index.upsert(library, pdf, sc, None, rec, os.path.getmtime(sc))

    path, written, skipped, changed = bibtex_live.sync(library, out)

    assert (written, changed) == (2, True)


def test_a_file_that_is_not_there_is_written_without_asking(
        library, tmp_path):
    """Naming a `.bib` that does not exist yet is the usual case, and
    there is nothing to lose."""
    out = str(tmp_path / "new" / "refs.bib")

    path, written, skipped, changed = bibtex_live.sync(library, out)

    assert changed is True
    assert open(out, encoding="utf-8").read().startswith(
        bibtex_live.MARKER)
