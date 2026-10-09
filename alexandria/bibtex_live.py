"""Keep a `.bib` file in step with the library, for LaTeX.

Point this at the `refs.bib` your paper cites and Alexandria rewrites
it whenever the library changes — import a paper, add a ghost from
Discover, fix an author's name in the Edit dialog, and the `.bib` on
the next `pdflatex` run already has it. The alternative is
Export BibTeX… before every build, remembered every time.

Three decisions worth stating, because each could have gone the other
way:

**The whole library, rewritten — not the new entry, appended.** An
append-only stream is what "stream it as papers arrive" sounds like,
and it is wrong here. A `.bib` is a lookup table, not a log: an
appended entry whose key collides with one already in the file is a
silently wrong citation, and a correction made in the Edit dialog
would never reach a line already written. Rewriting from the index
means the file always says what the library says, which is the only
rule that stays true after an edit, a delete, or a key clash.

**Unchanged text is not written.** Rebuilding the whole file on every
change would touch the mtime every time, and `latexmk -pvc` watches
mtimes — a file rewritten identically would re-run LaTeX, forever.
The rendered text is compared with what is on disk first, and an
identical result is a no-op.

**A header line marks the file as ours.** It tells the user what
rewrote their file, and lets the Preferences dialog notice when it is
about to adopt a `.bib` that somebody wrote by hand — which this
would otherwise silently destroy on the next import.

Nothing here is wired to a signal: `index.CHANGE_SERIAL` is bumped by
every `upsert`/`remove`, and the browser window polls it. See
`browse.BrowserWindow._bib_live_tick`.
"""

import os

from . import bibtex_export, index, prefs


# First line of every file written here. Matched as a prefix, so the
# wording after it can change without un-adopting everyone's file.
MARKER = "% Written by Alexandria"

_HEADER = (
    MARKER + " — rewritten automatically whenever the library\n"
    "% changes. Edits made here will be lost; edit the paper in\n"
    "% Alexandria instead, or turn this off in Preferences.\n\n"
)


def get_path():
    """The configured live `.bib`, or '' when the feature is off."""
    return prefs.get_bibtex_live_path()


def set_path(path):
    """Turn the feature on for `path` (or off, when falsy)."""
    prefs.set_bibtex_live_path(path)


def is_foreign(path):
    """True when `path` holds content Alexandria did not write.

    A file that doesn't exist, can't be read, or is empty is not
    foreign — there is nothing there to lose. Asked by the
    Preferences dialog before adopting a file, so that overwriting
    a hand-maintained bibliography takes a yes."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            head = f.read(len(MARKER))
    except OSError:
        return False
    if not head.strip():
        return False
    return not head.startswith(MARKER)


# `index.search` takes a LIMIT rather than offering "no limit", so
# name the number instead of leaving a bare 10**9 in the call.
_ALL = 1000000000


def render(conn):
    """The full text the live file should hold, as
    `(text, written, skipped)`.

    Separate from `sync` so a test can check what would be written
    without a filesystem, and so the caller can compare before
    deciding to write."""
    # Every paper, not the 500 `index.search` stops at by default:
    # this file is the bibliography, and a library that outgrew the
    # default would start losing citations with no sign that it had.
    rows = index.search(conn, None, limit=_ALL)
    text, written, skipped = bibtex_export.rows_to_text(rows)
    return _HEADER + text, written, skipped


def sync(conn, path=None):
    """Rewrite the live `.bib` if it needs it.

    Returns None when the feature is off, and otherwise
    `(path, written, skipped, changed)` — `changed` False meaning the
    file on disk already said exactly this and was left alone.

    Raises OSError if the file cannot be written; the caller decides
    how loudly to say so."""
    path = path or get_path()
    if not path:
        return None

    text, written, skipped = render(conn)

    try:
        with open(path, "r", encoding="utf-8") as f:
            if f.read() == text:
                return path, written, skipped, False
    except OSError:
        pass  # missing or unreadable — write it

    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    # Atomic: LaTeX may be reading this file at the moment we rewrite
    # it, and half a `.bib` is a build failure with a confusing error.
    # The temp file is a sibling so the rename stays within one
    # filesystem, and is hidden so a `*.bib` glob in the same folder
    # doesn't pick it up in the instant it exists.
    tmp = os.path.join(parent or ".",
                       "." + os.path.basename(path) + ".alexandria-tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return path, written, skipped, True
